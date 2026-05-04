import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { checkMFAStatus } from '@/lib/utils/mfa-check'
import { ADMIN_MODULES, canAccessAdminModule, canSeeAdminEntry } from '@/lib/rbac/access'
import type { PermissionString, RBACClaims } from '@/lib/types/rbac.types'
import { publicSettings } from '../core/public-settings'

const KNOWN_ADMIN_MODULE_KEYS = new Set(ADMIN_MODULES.map((m) => m.key))

export async function updateSession(request: NextRequest) {
    let supabaseResponse = NextResponse.next({
        request,
    })

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
                        supabaseResponse.cookies.set(name, value, options)
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
            // unexpected exceptions.
            const url = request.nextUrl.clone()
            url.pathname = '/auth/login'
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