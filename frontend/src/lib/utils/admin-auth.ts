import { NextResponse, type NextRequest } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { createServerAdminClient } from '@/lib/supabase/serverAdminClient';
import { enforceSameOrigin } from '@/lib/utils/origin';
import type { SupabaseClient } from '@supabase/supabase-js';

interface AdminAuthSuccess {
  adminClient: SupabaseClient;
  /** The target user the admin is acting on. */
  userId: string;
  /** The admin (caller) user id — useful for audit logs. */
  actorUserId: string;
}

/**
 * Shared authorization for admin user-management routes.
 *
 * Performs, in order:
 * 1. CSRF origin check (`enforceSameOrigin`)
 * 2. Session authentication
 * 3. JWT-claims permission check
 * 4. Live superadmin protection (fetches target user from auth.admin)
 *
 * Returns a `NextResponse` error if any check fails, or an `AdminAuthSuccess`
 * object containing the admin Supabase client and the validated target userId.
 */
export async function authorizeAdminAction(
  request: NextRequest,
  targetUserId: string,
  requiredPermission: string
): Promise<NextResponse | AdminAuthSuccess> {
  // 1. CSRF check
  const originError = enforceSameOrigin(request);
  if (originError) return originError;

  // 2. Authenticate caller
  const supabase = await createSSRClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  // 3. Permission check via JWT claims (not stale app_metadata)
  const { data: claimsData } = await supabase.auth.getClaims();
  const permissions =
    ((claimsData?.claims as Record<string, unknown>)?.permissions as string[]) || [];
  if (!permissions.includes(requiredPermission)) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  // 4. Superadmin protection - fetch LIVE data for the target user
  const adminClient = await createServerAdminClient();
  const { data: targetUserData, error: targetUserError } =
    await adminClient.auth.admin.getUserById(targetUserId);

  if (targetUserError || !targetUserData.user) {
    return NextResponse.json({ error: 'User not found' }, { status: 404 });
  }

  const targetUserRole = targetUserData.user.app_metadata?.user_role;
  if (targetUserRole === 'super_admin') {
    return NextResponse.json(
      { error: 'Superadmin users cannot be modified' },
      { status: 403 }
    );
  }

  return { adminClient, userId: targetUserId, actorUserId: user.id };
}
