import { NextRequest, NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { forgotPasswordSchema } from '@/lib/schemas/auth.schema';
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
      routeId: 'auth_forgot_password',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_FORGOT_PASSWORD,
    });
    if (limited) {
      return limited;
    }

    const body = await request.json();
    const validated = forgotPasswordSchema.parse(body);

    const supabase = await createSSRClient();
    const { error } = await supabase.auth.resetPasswordForEmail(validated.email, {
      redirectTo: `${serverSettings.NEXT_PUBLIC_SITE_URL}/auth/reset-password`,
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    return NextResponse.json({ message: 'Password reset email sent' });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(zodToApiError(error), { status: 400 });
    }
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
