import { NextRequest, NextResponse } from 'next/server';
import { revokeAllUserSessions } from '@/lib/supabase/serverAdminClient';
import { authorizeAdminAction } from '@/lib/utils/admin-auth';
import { recordAuditLog } from '@/lib/utils/audit-log';

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ userId: string }> }
) {
  try {
    const { userId } = await params;
    const auth = await authorizeAdminAction(request, userId, 'users:delete_all');
    if (auth instanceof NextResponse) return auth;

    // Capture target email for the audit log before deletion.
    const { data: targetData } = await auth.adminClient.auth.admin.getUserById(auth.userId);
    const targetEmail = targetData?.user?.email ?? null;

    await revokeAllUserSessions(auth.userId);
    const { error } = await auth.adminClient.auth.admin.deleteUser(auth.userId);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    await recordAuditLog(request, {
      actorUserId: auth.actorUserId,
      module: 'users',
      action: 'user_deleted',
      resourceId: auth.userId,
      details: targetEmail ? { email: targetEmail } : null,
    });

    return NextResponse.json({ message: 'User deleted successfully' });
  } catch (error) {
    console.error('Delete user error:', error);
    return NextResponse.json({ error: 'Failed to delete user' }, { status: 500 });
  }
}
