import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { authorizeAdminRequest } from '@/lib/utils/admin-auth';
import { recordAuditLog } from '@/lib/utils/audit-log';
import { zodToApiError } from '@/lib/utils/api-errors';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { serverSettings } from '@/lib/core/server-settings';
import { publicSettings } from '@/lib/core/public-settings';

export const runtime = 'nodejs';

/**
 * Superadmin user invite (invite-only platform — there is no public signup).
 *
 * Scope (architecture rule): this Next.js route only performs the Supabase
 * `auth.users` admin invite. It does NOT write application tables — role
 * assignment (`/api/v1/users/{id}/roles`) and per-school membership grants
 * (`/api/v1/users/{id}/schools`) are FastAPI writes the client chains after
 * this returns the new user's id.
 *
 * Security:
 * - CSRF (`enforceSameOrigin`) + rate limit (via `authorizeAdminRequest`).
 * - Gated on `users:update_all` (existing permission — no catalog churn).
 * - NEVER returns access/refresh tokens (the invite email carries the
 *   one-time recovery link; the user sets their own password).
 * - Inputs sanitized; errors are generic (no permission-list leak).
 */
const inviteSchema = z.object({
  email: z.string().trim().toLowerCase().email('Invalid email address'),
  full_name: z.string().trim().min(1).max(120).optional(),
});

export async function POST(request: NextRequest) {
  try {
    // CSRF + auth + permission (users:update_all). No live-superadmin step:
    // there is no existing target user to protect when inviting a new one.
    const auth = await authorizeAdminRequest(request, 'users:update_all');
    if (auth instanceof NextResponse) return auth;

    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'users_invite',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_REGISTER,
    });
    if (limited) return limited;

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
    }

    const parsed = inviteSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(zodToApiError(parsed.error), { status: 400 });
    }
    const { email, full_name } = parsed.data;

    // Send the Supabase invite email. The user clicks the link, lands on
    // /auth/accept-invite (via /api/auth/confirm), and sets a password.
    const redirectTo = `${publicSettings.NEXT_PUBLIC_SITE_URL}/auth/accept-invite`;
    const { data, error } = await auth.adminClient.auth.admin.inviteUserByEmail(
      email,
      {
        data: full_name ? { full_name } : undefined,
        redirectTo,
      },
    );

    if (error) {
      // Generic, non-leaking message. Common case: user already exists.
      const status = /already|registered|exists/i.test(error.message) ? 409 : 400;
      const message =
        status === 409
          ? 'A user with this email already exists.'
          : 'Failed to send invitation.';
      return NextResponse.json({ error: message }, { status });
    }

    const invitedUserId = data.user?.id ?? null;

    await recordAuditLog(request, {
      actorUserId: auth.actorUserId,
      module: 'users',
      action: 'user_invited',
      resourceId: invitedUserId,
      details: { email, full_name: full_name ?? null },
    });

    // Return ONLY the new user's identity so the client can chain role/school
    // assignment via FastAPI. No tokens, ever.
    return NextResponse.json(
      { userId: invitedUserId, email },
      { status: 201 },
    );
  } catch (error) {
    console.error('User invite error:', error);
    return NextResponse.json(
      { error: 'Failed to send invitation.' },
      { status: 500 },
    );
  }
}
