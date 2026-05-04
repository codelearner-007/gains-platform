import { NextRequest, NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { loginSchema } from '@/lib/schemas/auth.schema';
import { checkMFAStatus } from '@/lib/utils/mfa-check';
import { enforceSameOrigin } from '@/lib/utils/origin';
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
      routeId: 'auth_login',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_LOGIN,
    });
    if (limited) {
      return limited;
    }

    const body = await request.json();
    const validated = loginSchema.parse(body);

    const supabase = await createSSRClient();
    const { data, error } = await supabase.auth.signInWithPassword({
      email: validated.email,
      password: validated.password,
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 401 });
    }

    // Check AAL level and MFA status using utility
    const { currentLevel, requiresMFA } = await checkMFAStatus(supabase);

    // Only return safe user metadata - tokens are already set as httpOnly cookies
    // by the Supabase SSR client. Exposing them in the response body would allow
    // exfiltration via XSS.
    return NextResponse.json({
      user: data.user
        ? {
            id: data.user.id,
            email: data.user.email,
            user_metadata: data.user.user_metadata,
            app_metadata: data.user.app_metadata,
          }
        : null,
      requiresMFA,
      currentAAL: currentLevel,
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(zodToApiError(error), { status: 400 });
    }
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
