import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { createSSRClient } from '@/lib/supabase/server';
import { enforceSameOrigin } from '@/lib/utils/origin';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { serverSettings } from '@/lib/core/server-settings';
import { zodToApiError } from '@/lib/utils/api-errors';
import { publicSettings } from '@/lib/core/public-settings';

const requestSchema = z.object({
  email: z.string().email('Enter a valid email address').max(254),
});

/**
 * POST /api/auth/magic-link
 *
 * Sends a one-time login link to the user's email. Mirrors the password
 * reset flow's protections:
 * - Same-origin enforced (CSRF).
 * - Reuses the auth-login rate limit policy.
 * - Always returns the same generic success message — never reveals whether
 *   the email is registered (avoids account enumeration).
 *
 * The email link points at our `/api/auth/confirm` route, which verifies
 * the token, runs MFA-aware checks, and signs the user in.
 */
export async function POST(request: NextRequest) {
  try {
    const originError = enforceSameOrigin(request);
    if (originError) return originError;

    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'auth_magic_link',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_LOGIN,
    });
    if (limited) return limited;

    const body = await request.json().catch(() => ({}));
    const { email } = requestSchema.parse(body);

    // emailRedirectTo MUST be derived from server-side trusted config, not the
    // request Origin header. Origin can vary between preview deploys and is
    // attacker-controllable from misconfigured proxies.
    const baseUrl = publicSettings.NEXT_PUBLIC_SITE_URL;
    const supabase = await createSSRClient();

    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${baseUrl}/api/auth/confirm?type=magiclink&next=/app`,
      },
    });

    if (error) {
      // Log server-side, but always return the same generic message.
      console.error('Magic-link send failed', error);
    }

    return NextResponse.json({
      message:
        'If that email is registered, a sign-in link has been sent. Check your inbox.',
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(zodToApiError(error), { status: 400 });
    }
    console.error('Magic-link route error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
