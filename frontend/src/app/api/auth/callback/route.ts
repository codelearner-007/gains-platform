import { NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { enforceSameOrigin } from '@/lib/utils/origin';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { serverSettings } from '@/lib/core/server-settings';

const ALLOWED_NEXT_PREFIXES = ['/app', '/admin', '/auth/2fa', '/auth/reset-password'];

function isAllowedNext(next: string | null): boolean {
  if (!next) return false;
  if (!next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return false;
  return ALLOWED_NEXT_PREFIXES.some(
    (prefix) => next === prefix || next.startsWith(`${prefix}/`) || next.startsWith(`${prefix}?`),
  );
}

/**
 * OAuth callback (PKCE).
 *
 * The browser is redirected here from a Supabase OAuth provider with
 * `?code=...`. We exchange the code for a session (which sets httpOnly
 * cookies via @supabase/ssr) and then route to a safe `next` destination.
 *
 * Security:
 * - `next` is allowlisted (no open redirect).
 * - MFA fail-closed: when AAL fetch errors, sign out before redirecting to
 *   login (no orphaned session cookies). signOut failures are logged.
 * - Exchange errors surface via a stable error code, not a free-form message.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const nextParam = url.searchParams.get('next');
  const next = isAllowedNext(nextParam) ? nextParam! : '/app';

  if (!code) {
    return NextResponse.redirect(new URL('/auth/login?error=missing_code', request.url));
  }

  const supabase = await createSSRClient();
  const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
  if (exchangeError) {
    console.error('OAuth code exchange failed', exchangeError);
    return NextResponse.redirect(new URL('/auth/login?error=oauth_exchange_failed', request.url));
  }

  const { data: aal, error: aalError } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  if (aalError) {
    console.error('OAuth callback: AAL check failed', aalError);
    await supabase.auth.signOut().catch((e) => {
      console.error('OAuth callback: signOut after AAL failure also failed', e);
    });
    return NextResponse.redirect(new URL('/auth/login?error=mfa_check_failed', request.url));
  }
  if (aal.nextLevel === 'aal2' && aal.nextLevel !== aal.currentLevel) {
    return NextResponse.redirect(new URL('/auth/2fa', request.url));
  }

  return NextResponse.redirect(new URL(next, request.url));
}

/**
 * POST variant — used by client-side flows (e.g. password reset code from
 * email link) that need to exchange a code without a full-page redirect.
 *
 * Same security guarantees as GET: rate-limited, MFA fails closed, partial
 * session is cleared, exchange errors surface as a stable error code.
 */
export async function POST(request: Request) {
  try {
    const originError = enforceSameOrigin(request);
    if (originError) return originError;

    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'auth_callback_exchange',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_LOGIN,
    });
    if (limited) return limited;

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
    }

    const code =
      body && typeof body === 'object' && 'code' in body
        ? (body as { code: unknown }).code
        : undefined;
    if (!code || typeof code !== 'string') {
      return NextResponse.json({ error: 'Code is required' }, { status: 400 });
    }

    const supabase = await createSSRClient();
    const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
    if (exchangeError) {
      return NextResponse.json({ error: 'Invalid or expired code' }, { status: 400 });
    }

    const { data: aal, error: aalError } =
      await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    if (aalError) {
      console.error('OAuth callback (POST): AAL check failed', aalError);
      await supabase.auth.signOut().catch((e) => {
        console.error('OAuth callback (POST): signOut after AAL failure also failed', e);
      });
      return NextResponse.json({ error: 'mfa_check_failed' }, { status: 401 });
    }
    if (aal.nextLevel === 'aal2' && aal.nextLevel !== aal.currentLevel) {
      return NextResponse.json(
        { requiresMfa: true, redirect: '/auth/2fa' },
        { status: 200 },
      );
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('OAuth callback POST: unexpected error', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
