import { NextRequest, NextResponse } from 'next/server';
import { enforceSameOrigin } from '@/lib/utils/origin';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { serverSettings } from '@/lib/core/server-settings';

/**
 * Public self-signup is DISABLED — GAINS is an invite-only platform.
 *
 * This route is intentionally hard-disabled: it NEVER creates an auth user.
 * Users are provisioned by the superadmin via the admin invite flow.
 * CSRF (same-origin) + rate limiting are kept as defense-in-depth so the
 * endpoint cannot be abused for probing, but it always returns 403.
 */
export async function POST(request: NextRequest) {
  const originError = enforceSameOrigin(request);
  if (originError) return originError;

  const limited = await enforceRateLimitResponse({
    request,
    routeId: 'auth_register',
    policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_REGISTER,
  });
  if (limited) return limited;

  return NextResponse.json(
    { error: 'Public signup is disabled. Accounts are provisioned by invitation only.' },
    { status: 403 },
  );
}
