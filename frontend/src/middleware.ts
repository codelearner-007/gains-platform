import { NextResponse, type NextRequest } from 'next/server'
import { updateSession } from '@/lib/supabase/middleware'

// Schoology origins allowed to frame the launch/app surface. Kept narrow: only
// the district-facing app host and the *.schoology.com wildcard the LTI launch
// iframes come from. Never widened to the whole web.
const SCHOOLOGY_FRAME_ANCESTORS =
    "frame-ancestors 'self' https://*.schoology.com https://app.schoology.com"

/**
 * Is this request part of the LTI-framed surface (the tenant app, or the
 * bridge route that mints the session on the way in)? ONLY these paths may be
 * embedded by Schoology. Everything else — /admin, /auth, marketing — stays
 * un-framable (X-Frame-Options: DENY below).
 */
function isFramedSurface(pathname: string): boolean {
    return pathname.startsWith('/app') || pathname.startsWith('/api/lti/bridge')
}

/**
 * Apply frame/clickjacking headers to whatever response updateSession returns
 * (a redirect OR the passthrough). Two mutually-exclusive postures:
 *
 *  - Framed surface (/app, /api/lti/bridge): emit a `frame-ancestors` CSP
 *    scoped to Schoology and DROP X-Frame-Options (XFO and frame-ancestors
 *    conflict; a lingering XFO: DENY would framebust Schoology). This is the
 *    ONLY surface Schoology may embed.
 *  - Everywhere else (/admin, /auth, everything): X-Frame-Options: DENY, the
 *    site-wide framebust default. The app set no framing headers before this
 *    change, so this HARDENS /admin against clickjacking rather than relaxing
 *    anything.
 */
function applyFrameHeaders(response: NextResponse, pathname: string): NextResponse {
    if (isFramedSurface(pathname)) {
        response.headers.set('Content-Security-Policy', SCHOOLOGY_FRAME_ANCESTORS)
        response.headers.delete('X-Frame-Options')
    } else {
        response.headers.set('X-Frame-Options', 'DENY')
        response.headers.delete('Content-Security-Policy')
    }
    return response
}

export async function middleware(request: NextRequest) {
    const response = await updateSession(request)
    return applyFrameHeaders(response, request.nextUrl.pathname)
}

export const config = {
    matcher: [
        '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
    ],
}
