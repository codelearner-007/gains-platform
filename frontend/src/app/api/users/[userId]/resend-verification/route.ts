import { NextRequest, NextResponse } from 'next/server';
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
      console.error('Resend invitation: getUserById failed:', lookupError);
      return NextResponse.json(
        { error: 'Unable to look up user. Please try again.' },
        { status: 502 }
      );
    }

    if (!targetUserData?.user?.email) {
      return NextResponse.json({ error: 'User email not found' }, { status: 404 });
    }

    // Re-send the INVITATION (not a passwordless magic link). This action is only
    // offered for invited-but-not-yet-accepted users (!email_confirmed_at), so the
    // correct behaviour is to resend the invite, whose link routes through
    // /auth/accept-invite and forces the user to set a password. A magic link would
    // instead log them straight into /app with no password set, bypassing onboarding.
    // `inviteUserByEmail` is used (NOT `generateLink`): generateLink only returns a
    // link and never dispatches an email, so it silently sends nothing —
    // inviteUserByEmail actually sends via SMTP and re-invites an existing pending user.
    const { error } = await auth.adminClient.auth.admin.inviteUserByEmail(
      targetUserData.user.email,
      { redirectTo: `${publicSettings.NEXT_PUBLIC_SITE_URL}/auth/accept-invite` },
    );

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    await recordAuditLog(request, {
      actorUserId: auth.actorUserId,
      module: 'users',
      action: 'invitation_resent',
      resourceId: auth.userId,
      details: { email: targetUserData.user.email },
    });

    return NextResponse.json({ message: 'Invitation resent successfully' });
  } catch (error) {
    console.error('Resend invitation error:', error);
    return NextResponse.json(
      { error: 'Failed to resend invitation' },
      { status: 500 }
    );
  }
}
