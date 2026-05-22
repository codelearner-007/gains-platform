import { NextRequest, NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { registerSchema } from '@/lib/schemas/auth.schema';
import { enforceSameOrigin } from '@/lib/utils/origin';
import { zodToApiError } from '@/lib/utils/api-errors';
import { z } from 'zod';
import { publicSettings } from '@/lib/core/public-settings';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { serverSettings } from '@/lib/core/server-settings';

export async function POST(request: NextRequest) {
  try {
    const originError = enforceSameOrigin(request);
    if (originError) return originError;

    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'auth_register',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_REGISTER,
    });
    if (limited) return limited;

    const body = await request.json();
    const validated = registerSchema.parse(body);

    const supabase = await createSSRClient();

    // Get origin with production-safe fallback
    const origin = request.headers.get('origin') || publicSettings.NEXT_PUBLIC_SITE_URL;

    // Log config error in production
    if (!request.headers.get('origin') && !publicSettings.NEXT_PUBLIC_SITE_URL) {
      console.error(
        'Registration without origin header and NEXT_PUBLIC_SITE_URL not set. ' +
        'Email verification links may not work correctly.'
      );
    }

    const { data, error } = await supabase.auth.signUp({
      email: validated.email,
      password: validated.password,
      options: {
        emailRedirectTo: `${origin}/auth/callback?next=/app`,
        data: {
          full_name: validated.full_name || '',
        },
      },
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    // Only return safe user metadata - tokens are set as httpOnly cookies by Supabase SSR
    return NextResponse.json({
      user: data.user
        ? {
            id: data.user.id,
            email: data.user.email,
            user_metadata: data.user.user_metadata,
            app_metadata: data.user.app_metadata,
          }
        : null,
      message: 'Please check your email to verify your account',
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(zodToApiError(error), { status: 400 });
    }
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
