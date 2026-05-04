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

    const { data: targetUserData } =
      await auth.adminClient.auth.admin.getUserById(auth.userId);

    if (!targetUserData?.user?.email) {
      return NextResponse.json({ error: 'User email not found' }, { status: 404 });
    }

    const { error } = await auth.adminClient.auth.admin.generateLink({
      type: 'magiclink',
      email: targetUserData.user.email,
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    await recordAuditLog(request, {
      actorUserId: auth.actorUserId,
      module: 'users',
      action: 'verification_resent',
      resourceId: auth.userId,
      details: { email: targetUserData.user.email },
    });

    return NextResponse.json({ message: 'Verification email sent successfully' });
  } catch (error) {
    console.error('Resend verification error:', error);
    return NextResponse.json(
      { error: 'Failed to resend verification email' },
      { status: 500 }
    );
  }
}
