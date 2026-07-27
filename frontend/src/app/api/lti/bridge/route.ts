import { NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { createServerAdminClient } from '@/lib/supabase/serverAdminClient';
import { publicSettings } from '@/lib/core/public-settings';

// Where to land the browser after a verified launch mints a session. The
// backend redirects here (/api/lti/bridge?ticket=...) instead of straight to a
// report so that a real Supabase session cookie is set on the app's own origin
// before the app shell renders.
const LTI_REDIRECT_BASE = process.env.LTI_REDIRECT_BASE || '/app';

function invalidLaunch(request: Request) {
  return NextResponse.redirect(
    new URL('/auth/login?error=invalid_launch', request.url),
  );
}

/**
 * LTI session bridge (GET). Turns a verified-launch handoff ticket into a real
 * Supabase session cookie, then redirects to the tenant-scoped report.
 *
 *   1. Read ?ticket (absent → invalid_launch).
 *   2. Exchange it at the backend's machine-auth /lti/consume-ticket
 *      (X-LTI-Bridge-Secret). Non-200 → invalid_launch. Yields {user_id, email,
 *      school_id}.
 *   3. admin.generateLink(magiclink, email) → token_hash; SSR verifyOtp sets the
 *      session cookies on this response.
 *   4. Fail-closed MFA/AAL gate (verbatim from /api/auth/confirm). LTI users are
 *      aal1 / 0-factors → they pass; a stepped-up user is sent to /auth/2fa.
 *   5. Redirect to LTI_REDIRECT_BASE?school_id=<school_id> (param omitted when
 *      the ticket carried no school).
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const ticket = url.searchParams.get('ticket');
  if (!ticket) return invalidLaunch(request);

  const secret = process.env.LTI_BRIDGE_SECRET;
  if (!secret) {
    console.error('LTI bridge: LTI_BRIDGE_SECRET is not configured');
    return invalidLaunch(request);
  }

  // 2. Exchange the ticket for the provisioned identity (machine-auth to FastAPI).
  let identity: { user_id: string; email: string; school_id: string | null };
  try {
    const res = await fetch(
      `${publicSettings.NEXT_PUBLIC_API_URL}/api/v1/lti/consume-ticket`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-LTI-Bridge-Secret': secret,
        },
        body: JSON.stringify({ ticket }),
        cache: 'no-store',
      },
    );
    if (!res.ok) {
      console.error('LTI bridge: consume-ticket rejected', res.status);
      return invalidLaunch(request);
    }
    identity = await res.json();
  } catch (e) {
    console.error('LTI bridge: consume-ticket request failed', e);
    return invalidLaunch(request);
  }

  const { email, school_id } = identity;
  if (!email) {
    console.error('LTI bridge: consumed ticket carried no email');
    return invalidLaunch(request);
  }

  // 3. Mint a magic-link token for the exact provisioned email, then verify it
  // through the SSR client so the session cookies land on this response.
  const admin = await createServerAdminClient();
  const { data: linkData, error: linkError } = await admin.auth.admin.generateLink({
    type: 'magiclink',
    email,
  });
  const tokenHash = linkData?.properties?.hashed_token;
  if (linkError || !tokenHash) {
    console.error('LTI bridge: generateLink failed', linkError?.message);
    return invalidLaunch(request);
  }

  // The session cookies this route mints must survive inside a *.schoology.com
  // iframe → SameSite=None; Secure. But SameSite=None REQUIRES Secure REQUIRES
  // HTTPS, which local http dev does not have — so gate it: production only.
  // In dev we fall back to the shared Lax default (the mock harness runs
  // same-origin, so Lax is fine and cookie-setting still works). This override
  // is scoped to THIS route's client only; password login / OAuth keep Lax.
  const isProd = process.env.NODE_ENV === 'production';
  const bridgeCookieOptions = isProd
    ? ({ sameSite: 'none' as const, secure: true })
    : undefined;

  // Partitioned (CHIPS) so the SameSite=None session cookie survives inside the
  // Schoology iframe under modern Chrome's third-party-cookie blocking.
  const supabase = await createSSRClient(bridgeCookieOptions, {
    partitioned: isProd,
  });
  const { error: otpError } = await supabase.auth.verifyOtp({
    type: 'magiclink',
    token_hash: tokenHash,
  });
  if (otpError) {
    console.error('LTI bridge: verifyOtp failed', otpError.message);
    return invalidLaunch(request);
  }

  // 4. Fail-closed MFA/AAL gate — identical handling to /api/auth/confirm.
  const { data: aal, error: aalError } =
    await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  if (aalError) {
    console.error('LTI bridge: AAL check failed', aalError);
    await supabase.auth.signOut().catch((e) => {
      console.error('LTI bridge: signOut after AAL failure also failed', e);
    });
    return NextResponse.redirect(
      new URL('/auth/login?error=mfa_check_failed', request.url),
    );
  }
  if (aal.nextLevel === 'aal2' && aal.nextLevel !== aal.currentLevel) {
    return NextResponse.redirect(new URL('/auth/2fa', request.url));
  }

  // 5. Land on the tenant-scoped report. school_id travels only when the ticket
  // resolved a tenant (deployment binding).
  const dest = new URL(LTI_REDIRECT_BASE, request.url);
  if (school_id) dest.searchParams.set('school_id', school_id);
  return NextResponse.redirect(dest);
}
