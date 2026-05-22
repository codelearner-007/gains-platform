import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';

import { createSSRClient } from '@/lib/supabase/server';
import { resendVerificationSchema } from '@/lib/schemas/auth.schema';
import { enforceSameOrigin } from '@/lib/utils/origin';
import { zodToApiError } from '@/lib/utils/api-errors';
import { publicSettings } from '@/lib/core/public-settings';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { serverSettings } from '@/lib/core/server-settings';

export async function POST(request: NextRequest) {
  try {
    const originError = enforceSameOrigin(request);
    if (originError) return originError;

    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'auth_resend_verification',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_REGISTER,
    });
    if (limited) return limited;

    const body = await request.json();
    const { email } = resendVerificationSchema.parse(body);

    const supabase = await createSSRClient();
    const origin =
      request.headers.get('origin') || publicSettings.NEXT_PUBLIC_SITE_URL;

    const { error } = await supabase.auth.resend({
      type: 'signup',
      email,
      options: {
        emailRedirectTo: `${origin}/app`,
      },
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    return NextResponse.json({
      message: 'Verification email resent. Please check your inbox.',
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(zodToApiError(error), { status: 400 });
    }
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    );
  }
}
