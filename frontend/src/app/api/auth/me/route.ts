import { NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { checkMFAStatus } from '@/lib/utils/mfa-check';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import type { RBACClaims } from '@/lib/types/rbac.types';
import { serverSettings } from '@/lib/core/server-settings';

/** ioredis requires Node.js runtime (not Edge). */
export const runtime = 'nodejs';

export async function GET(request: Request) {
  try {
    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'auth_me',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_ME,
    });
    if (limited) {
      return limited;
    }

    const supabase = await createSSRClient();
    const { data: { user }, error } = await supabase.auth.getUser();

    if (error || !user) {
      return NextResponse.json({ user: null });
    }

    // Check MFA status using utility
    // If the user has verified MFA factors but this session is only AAL1,
    // require MFA verification before treating them as fully authenticated.
    const { currentLevel, requiresMFA } = await checkMFAStatus(supabase);

    const { data: claimsData, error: claimsError } = await supabase.auth.getClaims();
    if (claimsError) {
      console.error('Failed to get JWT claims:', claimsError);
    }

    const customClaims = (claimsData?.claims ?? {}) as RBACClaims;

    // Merge custom JWT claims into app_metadata for consistent access
    const appMetadata = {
      ...user.app_metadata,
      permissions: customClaims.permissions || [],
      hierarchy_level: customClaims.hierarchy_level,
      user_role: customClaims.user_role,
    };

    return NextResponse.json({
      user: {
        id: user.id,
        email: user.email,
        user_metadata: user.user_metadata,
        app_metadata: appMetadata,
        created_at: user.created_at,
      },
      requiresMFA,
      currentAAL: currentLevel,
    });
  } catch (error) {
    console.error('Error fetching current user:', error);
    return NextResponse.json({ user: null }, { status: 500 });
  }
}
