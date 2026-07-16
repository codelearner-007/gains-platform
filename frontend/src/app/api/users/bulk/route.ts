import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import type { SupabaseClient } from '@supabase/supabase-js';
import { authorizeAdminRequest } from '@/lib/utils/admin-auth';
import { revokeAllUserSessions } from '@/lib/supabase/serverAdminClient';
import { recordAuditLog } from '@/lib/utils/audit-log';
import { zodToApiError } from '@/lib/utils/api-errors';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { mapPool } from '@/lib/utils/concurrency';
import { serverSettings } from '@/lib/core/server-settings';
import { publicSettings } from '@/lib/core/public-settings';

export const runtime = 'nodejs';

/**
 * Bulk auth.users admin actions (invite-only platform).
 *
 * Scope (architecture rule): auth.users operations only — ban/unban/delete are
 * Supabase admin actions, resend-invite re-dispatches the invite email. No
 * application-table writes here.
 *
 * Safety (Risk R5 — bulk blast radius):
 * - hard cap of {@link MAX_TARGETS} ids/request;
 * - CSRF + permission gate (delete → users:delete_all, else users:update_all);
 * - per-target LIVE superadmin protection via getUserById (never pre-filtered
 *   client-side only) — superadmins are rejected, not modified;
 * - bounded concurrency; every success individually audited;
 * - 200 with per-target results even on partial failure (never all-or-nothing).
 */
const MAX_TARGETS = 50;
const CONCURRENCY = 5;
const DEFAULT_BAN_DURATION = '8760h'; // 1 year, matches the single-user route

const bulkSchema = z.object({
  action: z.enum(['ban', 'unban', 'delete', 'resend-invite']),
  user_ids: z.array(z.string().uuid()).min(1).max(MAX_TARGETS),
  ban_duration: z.string().trim().max(20).optional(),
});

type BulkAction = z.infer<typeof bulkSchema>['action'];

const PERMISSION_BY_ACTION: Record<BulkAction, string> = {
  ban: 'users:update_all',
  unban: 'users:update_all',
  'resend-invite': 'users:update_all',
  delete: 'users:delete_all',
};

const AUDIT_ACTION: Record<BulkAction, string> = {
  ban: 'user_banned',
  unban: 'user_unbanned',
  delete: 'user_deleted',
  'resend-invite': 'invitation_resent',
};

interface TargetResult {
  user_id: string;
  ok: boolean;
  error?: string;
}

async function applyAction(
  request: NextRequest,
  adminClient: SupabaseClient,
  actorUserId: string,
  action: BulkAction,
  userId: string,
  banDuration: string,
): Promise<TargetResult> {
  // LIVE superadmin protection — fetch the target fresh, never trust the client.
  const { data: target, error: lookupError } =
    await adminClient.auth.admin.getUserById(userId);
  if (lookupError) {
    return { user_id: userId, ok: false, error: 'Lookup failed. Try again.' };
  }
  if (!target?.user) {
    return { user_id: userId, ok: false, error: 'User not found.' };
  }
  if (target.user.app_metadata?.user_role === 'super_admin') {
    return { user_id: userId, ok: false, error: 'Superadmin cannot be modified.' };
  }

  let opError: string | null = null;
  const details: Record<string, string> = {};

  switch (action) {
    case 'ban': {
      const { error } = await adminClient.auth.admin.updateUserById(userId, {
        ban_duration: banDuration,
      });
      opError = error?.message ?? null;
      if (!opError) await revokeAllUserSessions(userId);
      details.duration = banDuration;
      break;
    }
    case 'unban': {
      const { error } = await adminClient.auth.admin.updateUserById(userId, {
        ban_duration: 'none',
      });
      opError = error?.message ?? null;
      break;
    }
    case 'delete': {
      const { error } = await adminClient.auth.admin.deleteUser(userId);
      opError = error?.message ?? null;
      break;
    }
    case 'resend-invite': {
      const email = target.user.email;
      if (!email) {
        return { user_id: userId, ok: false, error: 'User has no email.' };
      }
      const { error } = await adminClient.auth.admin.inviteUserByEmail(email, {
        redirectTo: `${publicSettings.NEXT_PUBLIC_SITE_URL}/auth/accept-invite`,
      });
      opError = error?.message ?? null;
      details.email = email;
      break;
    }
  }

  if (opError) {
    return { user_id: userId, ok: false, error: 'Action failed.' };
  }

  await recordAuditLog(request, {
    actorUserId,
    module: 'users',
    action: AUDIT_ACTION[action],
    resourceId: userId,
    details,
  });
  return { user_id: userId, ok: true };
}

export async function POST(request: NextRequest) {
  try {
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
    }

    const parsed = bulkSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(zodToApiError(parsed.error), { status: 400 });
    }
    const { action, user_ids, ban_duration } = parsed.data;

    // CSRF + auth + permission (action-scoped).
    const auth = await authorizeAdminRequest(request, PERMISSION_BY_ACTION[action]);
    if (auth instanceof NextResponse) return auth;

    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'users_bulk',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_REGISTER,
    });
    if (limited) return limited;

    // De-dup ids; never act on the caller themselves in a bulk op.
    const targets = Array.from(new Set(user_ids)).filter(
      (id) => id !== auth.actorUserId,
    );

    const results = await mapPool<string, TargetResult>(
      targets,
      CONCURRENCY,
      (userId) =>
        applyAction(
          request,
          auth.adminClient,
          auth.actorUserId,
          action,
          userId,
          ban_duration || DEFAULT_BAN_DURATION,
        ),
    );

    return NextResponse.json({ results }, { status: 200 });
  } catch (error) {
    console.error('Bulk user action error:', error);
    return NextResponse.json(
      { error: 'Bulk action failed.' },
      { status: 500 },
    );
  }
}
