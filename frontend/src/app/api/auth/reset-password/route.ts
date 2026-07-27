import { NextRequest, NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { resetPasswordSchema } from '@/lib/schemas/auth.schema';
import { enforceMFAForOperation } from '@/lib/utils/mfa-check';
import { enforceSameOrigin } from '@/lib/utils/origin';
import { forbidLtiUser } from '@/lib/server/lti-guard';
import { zodToApiError } from '@/lib/utils/api-errors';
import { z } from 'zod';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { serverSettings } from '@/lib/core/server-settings';

export const runtime = 'nodejs';

export async function POST(request: NextRequest) {
  try {
    const originError = enforceSameOrigin(request);
    if (originError) return originError;

    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'auth_reset_password',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_RESET_PASSWORD,
    });
    if (limited) {
      return limited;
    }

    const body = await request.json();
    const validated = resetPasswordSchema.parse(body);

    const supabase = await createSSRClient();

    // Get current user to check MFA status
    // Note: reset-password can be called in two contexts:
    // 1. Authenticated user with reset token (session exists) → enforce MFA
    // 2. Unauthenticated user with email reset token (no session) → skip MFA check
    const { data: { user } } = await supabase.auth.getUser();

    if (user) {
      // A Schoology-embedded (LTI) account has no password; setting one here
      // would mint a standalone password login and escape the lock-down. Reject.
      const ltiError = await forbidLtiUser();
      if (ltiError) return ltiError;

      // User is authenticated - enforce MFA if they have it enabled
      const mfaError = await enforceMFAForOperation(supabase);
      if (mfaError) return mfaError;
    }

    const { error } = await supabase.auth.updateUser({
      password: validated.password,
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    return NextResponse.json({ message: 'Password updated successfully' });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(zodToApiError(error), { status: 400 });
    }
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
