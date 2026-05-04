import { NextRequest, NextResponse } from 'next/server';
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

    const { data, error } = await auth.adminClient.auth.admin.updateUserById(
      auth.userId,
      { ban_duration: 'none' }
    );

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    await recordAuditLog(request, {
      actorUserId: auth.actorUserId,
      module: 'users',
      action: 'user_unbanned',
      resourceId: auth.userId,
    });

    return NextResponse.json({ data, message: 'User unbanned successfully' });
  } catch (error) {
    console.error('Unban user error:', error);
    return NextResponse.json({ error: 'Failed to unban user' }, { status: 500 });
  }
}
