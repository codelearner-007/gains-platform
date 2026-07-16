/**
 * Users provisioning service — invite (single or bulk) + per-school membership.
 *
 * Routing (per architecture rules):
 *  - Invite + bulk user actions hit the Next.js auth surface (`/api/users/*`)
 *    because they are Supabase `auth.users` admin actions.
 *  - Role assignment + membership grants hit FastAPI (`/api/v1/users/...`) via
 *    the Next.js rewrite. These are application-table DB writes.
 *
 * The multi-email invite is a two-step, no-N+1 flow: one Next call sends all the
 * invites in parallel and returns per-email results; one FastAPI
 * `bulk/provision` call then assigns the role + school memberships for every
 * successfully-invited user in a single transaction. Both steps report
 * per-target success/failure, so nothing fails silently.
 */

import { apiClient } from './api-client';

export type SchoolRole = 'admin' | 'teacher' | 'student' | 'member';

// ─── Invite ──────────────────────────────────────────────────────────────────

export interface InviteUsersRequest {
  emails: string[];
  full_name?: string;
  /** Optional platform role to assign to every invited user. */
  role_id?: string;
  /** Optional school memberships to grant to every invited user. */
  school_ids?: string[];
  school_role?: SchoolRole;
}

export type InviteEmailStatus = 'invited' | 'already_exists' | 'failed';

export interface InviteEmailResult {
  email: string;
  status: InviteEmailStatus;
  userId?: string | null;
  /** Whether role/school provisioning succeeded (only when requested). */
  provisioned?: boolean;
  provisionError?: string;
  error?: string;
}

interface ProvisionResult {
  user_id: string;
  ok: boolean;
  error?: string;
}

/**
 * Invite one or more users. Sends the Supabase invite emails (in parallel), then
 * — if a role/schools were chosen — provisions all invited users in one FastAPI
 * call. Returns a per-email result list (invite status + provisioning status).
 */
export async function inviteUsers(
  data: InviteUsersRequest,
): Promise<InviteEmailResult[]> {
  const { results } = await apiClient.post<{ results: InviteEmailResult[] }>(
    '/users/invite',
    { emails: data.emails, full_name: data.full_name },
  );

  const needsProvision = !!data.role_id || (data.school_ids?.length ?? 0) > 0;
  const invited = results.filter((r) => r.status === 'invited' && r.userId);

  if (needsProvision && invited.length > 0) {
    const assignments = invited.map((r) => ({
      user_id: r.userId as string,
      role_id: data.role_id || undefined,
      school_ids: data.school_ids?.length ? data.school_ids : undefined,
      school_role: data.school_role ?? 'member',
    }));
    try {
      const prov = await apiClient.post<{ results: ProvisionResult[] }>(
        '/v1/users/bulk/provision',
        { assignments },
      );
      const byId = new Map(prov.results.map((p) => [p.user_id, p]));
      for (const r of results) {
        if (r.userId && byId.has(r.userId)) {
          const p = byId.get(r.userId)!;
          r.provisioned = p.ok;
          if (!p.ok) r.provisionError = p.error;
        }
      }
    } catch {
      for (const r of invited) {
        r.provisioned = false;
        r.provisionError = 'Role/school assignment failed.';
      }
    }
  }

  return results;
}

// ─── Bulk user actions (auth.users) ──────────────────────────────────────────

export type BulkUserAction = 'ban' | 'unban' | 'delete' | 'resend-invite';

export interface BulkActionResult {
  user_id: string;
  ok: boolean;
  error?: string;
}

export async function bulkUserAction(
  action: BulkUserAction,
  userIds: string[],
  banDuration?: string,
): Promise<BulkActionResult[]> {
  const { results } = await apiClient.post<{ results: BulkActionResult[] }>(
    '/users/bulk',
    { action, user_ids: userIds, ban_duration: banDuration },
  );
  return results;
}

// ─── Per-school membership ───────────────────────────────────────────────────

export interface UserSchoolMembership {
  id: string;
  user_id: string;
  school_id: string;
  school_role: SchoolRole;
  is_primary: boolean;
  school_name: string;
  school_short_name: string;
  school_is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface GrantSchoolRequest {
  school_id: string;
  school_role?: SchoolRole;
  is_primary?: boolean;
}

/** List a user's school memberships (FastAPI, gated `users:read_all`). */
export async function listUserSchools(
  userId: string,
): Promise<UserSchoolMembership[]> {
  return apiClient.get<UserSchoolMembership[]>(`/v1/users/${userId}/schools`);
}

/** Grant a user access to a school (FastAPI, gated `users:assign_roles`). */
export async function grantUserSchool(
  userId: string,
  data: GrantSchoolRequest,
): Promise<UserSchoolMembership> {
  return apiClient.post<UserSchoolMembership>(`/v1/users/${userId}/schools`, {
    school_id: data.school_id,
    school_role: data.school_role ?? 'member',
    is_primary: data.is_primary ?? false,
  });
}

/** Revoke a user's access to a school (FastAPI, gated `users:assign_roles`). */
export async function revokeUserSchool(
  userId: string,
  schoolId: string,
): Promise<void> {
  return apiClient.delete<void>(`/v1/users/${userId}/schools/${schoolId}`);
}
