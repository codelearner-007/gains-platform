import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { checkMFAStatus } from '@/lib/utils/mfa-check'
import { ADMIN_MODULES, canAccessAdminModule, canSeeAdminEntry, isLtiAllowedPath } from '@/lib/rbac/access'
import type { PermissionString, RBACClaims } from '@/lib/types/rbac.types'
import { publicSettings } from '../core/public-settings'

const KNOWN_ADMIN_MODULE_KEYS = new Set(ADMIN_MODULES.map((m) => m.key))

export async function updateSession(request: NextRequest) {
    let supabaseResponse = NextResponse.next({
        request,
    })

    // A framed (Schoology iframe / LTI) session carries the `gains-framed` marker
    // set by the bridge. On EVERY /app request this middleware re-issues the
    // session cookie; without preserving Partitioned; SameSite=None; Secure here,
    // the first pass downgrades the bridge's partitioned cookie to the default
    // Lax/unpartitioned form and the third-party iframe drops it (blank app).
    // Scoped by the marker so standalone password/OAuth sessions stay Lax +
    // unpartitioned (their correct same-origin CSRF posture).
    const framed =
        process.env.NODE_ENV === 'production' &&
        request.cookies.has('gains-framed')

    const supabase = createServerClient(
        publicSettings.NEXT_PUBLIC_SUPABASE_URL,
        publicSettings.NEXT_PUBLIC_SUPABASE_ANON_KEY,
        {
            cookies: {
                getAll() {
                    return request.cookies.getAll()
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
                    supabaseResponse = NextResponse.next({
                        request,
                    })
                    cookiesToSet.forEach(({ name, value, options }) =>
                        supabaseResponse.cookies.set(
                            name,
                            value,
                            framed
                                ? { ...options, sameSite: 'none', secure: true, partitioned: true }
                                : options,
                        )
                    )
                },
            },
        }
    )

    // Do not run code between createServerClient and
    // supabase.auth.getUser(). A simple mistake could make it very hard to debug
    // issues with users being randomly logged out.

    // IMPORTANT: DO NOT REMOVE auth.getUser()

    const {data: user} = await supabase.auth.getUser()

    const pathname = request.nextUrl.pathname
    const isProtectedArea =
        pathname.startsWith('/app') ||
        pathname.startsWith('/admin')

    if ((!user || !user.user) && isProtectedArea) {
        const url = request.nextUrl.clone()
        url.pathname = '/auth/login'
        url.searchParams.set('returnTo', pathname)
        return NextResponse.redirect(url)
    }

    // Already signed in? The auth *entry* pages (login / register / forgot /
    // verify) make no sense — send the user to the app. Deliberately excludes
    // /auth/2fa, /auth/reset-password, and /auth/accept-invite, which a
    // signed-in (or mid-flow) user legitimately needs.
    const AUTH_ENTRY_PREFIXES = ['/auth/login', '/auth/forgot-password']
    if (
        user && user.user &&
        !request.nextUrl.searchParams.has('sessionError') &&
        AUTH_ENTRY_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))
    ) {
        const url = request.nextUrl.clone()
        const returnTo = request.nextUrl.searchParams.get('returnTo')
        url.pathname = returnTo && returnTo.startsWith('/') && !returnTo.startsWith('//') ? returnTo : '/app'
        url.search = ''
        return NextResponse.redirect(url)
    }

    // MFA enforcement for authenticated users accessing protected routes
    if (user && user.user && isProtectedArea) {
        try {
            const { hasVerifiedMFA, currentLevel } = await checkMFAStatus(supabase)

            // If user has MFA but hasn't verified it this session (AAL1), redirect to MFA page
            if (hasVerifiedMFA && currentLevel !== 'aal2') {
                const url = request.nextUrl.clone()
                url.pathname = '/auth/2fa'
                url.searchParams.set('returnTo', pathname)
                return NextResponse.redirect(url)
            }
        } catch (error) {
            console.error('MFA middleware error:', {
                error: error instanceof Error ? error.message : 'Unknown error',
                pathname: request.nextUrl.pathname,
                userId: user?.user?.id,
                timestamp: new Date().toISOString(),
            });
            // Fail CLOSED: redirect to login when MFA status cannot be determined.
            // This prevents bypassing MFA enforcement via network errors or
            // unexpected exceptions. The `sessionError` marker stops the signed-in
            // auth-entry bounce above from sending this still-authenticated user
            // back to /app, which would create a redirect loop.
            const url = request.nextUrl.clone()
            url.pathname = '/auth/login'
            url.searchParams.set('sessionError', '1')
            return NextResponse.redirect(url)
        }
    }

    // LTI (Schoology-embedded) users get a locked, analytics-only experience:
    // the dashboard and the reports it drills into — nothing else. Enforced here
    // at the edge (not merely hidden in the UI), so a typed URL to
    // /app/user-settings etc. is bounced back to the dashboard. isLtiAllowedPath
    // is an allowlist, so any future /app route is locked-out by default.
    if (user && user.user && pathname.startsWith('/app')) {
        const { data: claimsData, error: claimsError } = await supabase.auth.getClaims()
        if (claimsError) {
            console.error('Failed to get JWT claims in middleware (LTI gating):', claimsError)
        }
        const jwtClaims = (claimsData?.claims ?? {}) as RBACClaims
        // Absent/unreadable claim → treat as a normal account (full experience).
        // The account-mutation API endpoints (forbid_lti_user) are the backstop
        // that enforces the boundary for a real LTI user regardless.
        if (jwtClaims.is_lti_user === true && !isLtiAllowedPath(pathname)) {
            const url = request.nextUrl.clone()
            url.pathname = '/app'
            url.search = ''
            return NextResponse.redirect(url)
        }
    }

    // Centralized admin authorization (route gating)
    if (user && user.user && pathname.startsWith('/admin')) {
        // Extract JWT claims (verified) from the current access token.
        // This works in Edge runtime and verifies the JWT against the project's JWKS.
        const { data: claimsData, error: claimsError } = await supabase.auth.getClaims()
        if (claimsError) {
            console.error('Failed to get JWT claims in middleware:', claimsError)
        }

        const jwtClaims = (claimsData?.claims ?? {}) as RBACClaims
        const permissions = normalizePermissions(jwtClaims.permissions)
        const claims = { permissions }

        // Require "admin entry" permission for any /admin route (including /admin itself)
        if (!canSeeAdminEntry(claims)) {
            const url = request.nextUrl.clone()
            url.pathname = '/forbidden'
            url.searchParams.set('returnTo', '/app')
            url.searchParams.set('returnLabel', 'Back to App')
            url.searchParams.set('message', 'You do not have permission to access the admin area.')
            return NextResponse.redirect(url)
        }

        // Module-level gating for known modules: /admin/<moduleKey>
        const segments = pathname.split('/').filter(Boolean)
        const moduleKey = segments[1]
        if (moduleKey && KNOWN_ADMIN_MODULE_KEYS.has(moduleKey)) {
            if (!canAccessAdminModule(claims, moduleKey)) {
                const url = request.nextUrl.clone()
                url.pathname = '/forbidden'
                url.searchParams.set('returnTo', '/admin')
                url.searchParams.set('returnLabel', 'Back to Admin')
                url.searchParams.set('message', 'You do not have permission to access this admin module.')
                return NextResponse.redirect(url)
            }
        }
    }

    // IMPORTANT: You *must* return the supabaseResponse object as it is.
    // If you're creating a new response object with NextResponse.next() make sure to:
    // 1. Pass the request in it, like so:
    //    const myNewResponse = NextResponse.next({ request })
    // 2. Copy over the cookies, like so:
    //    myNewResponse.cookies.setAll(supabaseResponse.cookies.getAll())
    // 3. Change the myNewResponse object to fit your needs, but avoid changing
    //    the cookies!
    // 4. Finally:
    //    return myNewResponse
    // If this is not done, you may be causing the browser and server to go out
    // of sync and terminate the user's session prematurely!

    return supabaseResponse
}

function normalizePermissions(value: unknown): PermissionString[] {
    if (!Array.isArray(value)) return []
    return value.filter((p): p is PermissionString => typeof p === 'string' && p.includes(':'))
}