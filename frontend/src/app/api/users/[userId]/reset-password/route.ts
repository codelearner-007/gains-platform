import { NextRequest, NextResponse } from 'next/server';
import { revokeAllUserSessions } from '@/lib/supabase/serverAdminClient';
import { authorizeAdminAction } from '@/lib/utils/admin-auth';
import { recordAuditLog } from '@/lib/utils/audit-log';
import { publicSettings } from '@/lib/core/public-settings';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ userId: string }> }
) {
  try {
    const { userId } = await params;
    const auth = await authorizeAdminAction(request, userId, 'users:update_all');
    if (auth instanceof NextResponse) return auth;

    const { data: targetUserData, error: lookupError } =
      await auth.adminClient.auth.admin.getUserById(auth.userId);

    // Distinguish a failed lookup from a genuinely missing user. If getUserById
    // itself errors (transient Supabase/network fault), surface it as an upstream
    // error instead of masking it as a misleading 404 "user not found".
    if (lookupError) {
      console.error('Reset password: getUserById failed:', lookupError);
      return NextResponse.json(
        { error: 'Unable to look up user. Please try again.' },
        { status: 502 }
      );
    }

    if (!targetUserData?.user?.email) {
      return NextResponse.json({ error: 'User email not found' }, { status: 404 });
    }

    // Send a password-reset email. `resetPasswordForEmail` actually DISPATCHES the
    // recovery email via SMTP; `admin.generateLink` only returns a link without
    // sending, so it silently delivered nothing.
    const { error } = await auth.adminClient.auth.resetPasswordForEmail(
      targetUserData.user.email,
      { redirectTo: `${publicSettings.NEXT_PUBLIC_SITE_URL}/auth/reset-password` },
    );

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
