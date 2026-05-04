import { NextRequest, NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { createServerAdminClient } from '@/lib/supabase/serverAdminClient';
import { enforceMFAForOperation } from '@/lib/utils/mfa-check';
import { enforceSameOrigin } from '@/lib/utils/origin';
import { strongPasswordSchema } from '@/lib/schemas/password.schema';
import { zodToApiError } from '@/lib/utils/api-errors';
import { z } from 'zod';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { serverSettings } from '@/lib/core/server-settings';
import { recordAuditLog } from '@/lib/utils/audit-log';

export const runtime = 'nodejs';

export async function POST(request: NextRequest) {
  try {
    const originError = enforceSameOrigin(request);
    if (originError) return originError;

    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'auth_change_password',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_CHANGE_PASSWORD,
    });
    if (limited) {
      return limited;
    }

    const supabase = await createSSRClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Change password is a sensitive operation - enforce MFA if user has it enabled
    const mfaError = await enforceMFAForOperation(supabase);
    if (mfaError) return mfaError;

    const body = await request.json();
    const { currentPassword, newPassword, confirmPassword } = body;

    if (!currentPassword || !newPassword || !confirmPassword) {
      return NextResponse.json(
        { error: 'All fields are required' },
        { status: 400 }
      );
    }

    if (newPassword !== confirmPassword) {
      return NextResponse.json(
        { error: 'New passwords do not match' },
        { status: 400 }
      );
    }

    strongPasswordSchema.parse(newPassword);

    if (currentPassword === newPassword) {
      return NextResponse.json(
        { error: 'New password must be different from current password' },
        { status: 400 }
      );
    }

    // Verify current password before allowing the change
    const adminClient = await createServerAdminClient();
    const { error: verifyError } = await adminClient.auth.signInWithPassword({
      email: user.email!,
      password: currentPassword,
    });

    if (verifyError) {
      return NextResponse.json(
        { error: 'Current password is incorrect' },
        { status: 401 }
      );
    }

    // Update to new password
    const { error } = await supabase.auth.updateUser({
      password: newPassword,
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    // Sign out all other sessions for security (keep current session)
    await supabase.auth.signOut({ scope: 'others' });

    await recordAuditLog(request, {
      actorUserId: user.id,
      module: 'auth',
      action: 'password_changed',
      resourceId: user.id,
    });

    return NextResponse.json({
      success: true,
      message: 'Password changed successfully',
    });
  } catch (error: unknown) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(zodToApiError(error), { status: 400 });
    }
    console.error('Error changing password:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
