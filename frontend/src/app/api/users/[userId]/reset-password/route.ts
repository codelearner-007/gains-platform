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

    const { data: targetUserData } =
      await auth.adminClient.auth.admin.getUserById(auth.userId);

    if (!targetUserData?.user?.email) {
      return NextResponse.json({ error: 'User email not found' }, { status: 404 });
    }

    const { error } = await auth.adminClient.auth.admin.generateLink({
      type: 'recovery',
      email: targetUserData.user.email,
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    await revokeAllUserSessions(auth.userId);

    await recordAuditLog(request, {
      actorUserId: auth.actorUserId,
      module: 'users',
      action: 'password_reset_sent',
      resourceId: auth.userId,
      details: { email: targetUserData.user.email },
    });

    return NextResponse.json({ message: 'Password reset email sent successfully' });
  } catch (error) {
    console.error('Reset password error:', error);
    return NextResponse.json(
      { error: 'Failed to send password reset email' },
      { status: 500 }
    );
  }
}
