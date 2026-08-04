import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { createSSRClient } from '@/lib/supabase/server';
import { enforceSameOrigin } from '@/lib/utils/origin';
import { publicSettings } from '@/lib/core/public-settings';
import {
  CONFIRM_COOKIE,
  isConfirmType,
  isValidTokenHashShape,
  parseConfirmPayload,
  resolveNext,
  serializeConfirmPayload,
} from '@/lib/auth/confirm-params';

/**
 * Email-confirm endpoint for the token_hash flow (invite, recovery, magic link,
 * email / email_change).
 *
 * The one-time token is consumed ONLY on POST, and only after a human submits
 * the /auth/confirm interstitial form. Two properties defeat email-scanner
 * prefetch:
 *   1. GET never calls verifyOtp. It moves the token out of the URL into a
 *      short-lived httpOnly cookie and redirects to a token-free interstitial.
 *      A scanner prefetch only sets a cookie in its own throwaway session and
 *      never submits the form, so the token survives for the real click.
 *   2. Because the token rides in the cookie (not the page URL), it never
 *      reaches the client page, and so never any analytics, history, or Referer.
 */

// The cookie is scoped to this route only, so the interstitial page never
// receives it and it is sent solely with the POST that consumes it.
const COOKIE_PATH = '/api/auth/confirm';
// Long enough to open the email and click through, short enough to limit the
// window; the token's own OTP expiry is the real lifetime.
const COOKIE_MAX_AGE_SECONDS = 600;

type CookieStore = Awaited<ReturnType<typeof cookies>>;

function clearConfirmCookie(store: CookieStore): void {
  store.set(CONFIRM_COOKIE, '', { path: COOKIE_PATH, maxAge: 0 });
}

// Every error exit: drop the handoff cookie and send the user to the
// interstitial's own error card (no token in the URL). /auth/login is not used
// for errors because it does not render an error message.
function failConfirm(request: Request, store: CookieStore, type: string | null): NextResponse {
  clearConfirmCookie(store);
  const suffix = type && isConfirmType(type) ? `&type=${type}` : '';
  return NextResponse.redirect(
    new URL(`/auth/confirm?status=invalid${suffix}`, request.url),
    { status: 303 },
  );
}

/**
 * GET: never consumes a token. Validate the link shape, stash the token in the
 * httpOnly cookie, and redirect to the token-free interstitial. Links in
 * already-delivered emails still point here, so they keep working and stay safe
 * against prefetch.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const tokenHash = url.searchParams.get('token_hash');
  const type = url.searchParams.get('type');
  const next = url.searchParams.get('next');
  const cookieStore = await cookies();

  if (!isValidTokenHashShape(tokenHash) || !isConfirmType(type)) {
    return failConfirm(request, cookieStore, type);
  }

  cookieStore.set(
    CONFIRM_COOKIE,
    serializeConfirmPayload({ token_hash: tokenHash, type, next: resolveNext(type, next) }),
    {
      httpOnly: true,
      sameSite: 'lax',
      secure: publicSettings.NODE_ENV === 'production',
      path: COOKIE_PATH,
      maxAge: COOKIE_MAX_AGE_SECONDS,
    },
  );

  // `type` is not sensitive; the page uses it only to label the button.
  return NextResponse.redirect(new URL(`/auth/confirm?type=${type}`, request.url), {
    status: 303,
  });
}

/**
 * POST: the human-gated verification. Reads the token from the cookie (never the
 * URL), consumes it via verifyOtp, clears the cookie, and forwards to `next`.
 *
 * enforceSameOrigin runs BEFORE verifyOtp, so a rejected request never spends
 * the token. Every redirect is 303 (See Other) so the browser follows with a GET
 * rather than re-POSTing.
 */
export async function POST(request: Request) {
  const originError = enforceSameOrigin(request);
  if (originError) return originError;

  // No app-layer rate limit here (unlike magic-link / callback) on purpose:
  // verifyOtp is throttled by Supabase server-side, the token_hash is a
  // high-entropy single-use value read only from the cookie (an attacker must
  // re-plant it via GET for each guess), and a JSON 429 on this top-level
  // navigation is worse UX than the error card. An IP-based limit would also
  // false-positive when a school onboards many invitees from one shared IP.
  const cookieStore = await cookies();
  const payload = parseConfirmPayload(cookieStore.get(CONFIRM_COOKIE)?.value);

  if (!payload) {
    return failConfirm(request, cookieStore, null);
  }

  const supabase = await createSSRClient();
  const { error } = await supabase.auth.verifyOtp({
    type: payload.type,
    token_hash: payload.token_hash,
  });
  if (error) {
    console.error('Email confirmation failed:', error);
    return failConfirm(request, cookieStore, payload.type);
  }

  // Token spent: drop the handoff cookie before establishing the destination.
  clearConfirmCookie(cookieStore);
  // Re-resolve `next` here (not just at GET): parseConfirmPayload only checks it
  // is a string, so this is the allow-list guard against a tampered cookie.
  const next = resolveNext(payload.type, payload.next);

  // Recovery + invite: verifyOtp issues a session so the user can set a
  // password. Route straight to the set-password page (no MFA gate here: a
  // freshly invited user has none, and password-set must happen before app
  // access).
  if (payload.type === 'recovery' || payload.type === 'invite') {
    return NextResponse.redirect(new URL(next, request.url), { status: 303 });
  }

  const { data: aal, error: aalError } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  if (aalError) {
    // Fail closed: clear the session we just established and force re-auth.
    console.error('Confirm route: AAL check failed', aalError);
    await supabase.auth.signOut().catch((e) => {
      console.error('Confirm route: signOut after AAL failure also failed', e);
    });
    return NextResponse.redirect(new URL('/auth/login', request.url), { status: 303 });
  }
  if (aal.nextLevel === 'aal2' && aal.nextLevel !== aal.currentLevel) {
    return NextResponse.redirect(new URL('/auth/2fa', request.url), { status: 303 });
  }

  return NextResponse.redirect(new URL(next, request.url), { status: 303 });
}
