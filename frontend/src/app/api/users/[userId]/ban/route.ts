import { NextRequest, NextResponse } from 'next/server';
import { revokeAllUserSessions } from '@/lib/supabase/serverAdminClient';
import { authorizeAdminAction } from '@/lib/utils/admin-auth';
import { recordAuditLog } from '@/lib/utils/audit-log';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ userId: string }> }
) {
  try {
    const { userId } = await params;
    const auth = await authorizeAdminAction(request, userId, 'users:update_all');
    if (auth instanceof NextResponse) return auth;

    const { duration = '8760h' } = await request.json();

    const { data, error } = await auth.adminClient.auth.admin.updateUserById(
      auth.userId,
      { ban_duration: duration }
    );

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    await revokeAllUserSessions(auth.userId);

    await recordAuditLog(request, {
      actorUserId: auth.actorUserId,
      module: 'users',
      action: 'user_banned',
      resourceId: auth.userId,
      details: { duration },
    });

    return NextResponse.json({ data, message: 'User banned successfully' });
  } catch (error) {
    console.error('Ban user error:', error);
    return NextResponse.json({ error: 'Failed to ban user' }, { status: 500 });
  }
}
