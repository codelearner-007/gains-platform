/**
 * Users provisioning service — invite + per-school membership.
 *
 * Routing (per architecture rules):
 *  - Invite hits the Next.js auth surface (`/api/users/invite`) because it is a
 *    Supabase `auth.users` admin action.
 *  - Role assignment + membership grant/revoke hit FastAPI (`/api/v1/...`) via
 *    the Next.js rewrite (relative path, same-origin, session cookie forwarded).
 *    These are application-table DB writes and MUST live in FastAPI.
 */

import { apiClient } from './api-client';
import { assignRoleToUser } from './rbac.service';

export interface InviteUserRequest {
  email: string;
  full_name?: string;
  /** Optional platform role to assign immediately after invite. */
  role_id?: string;
  /** Optional school memberships to grant immediately after invite. */
  school_ids?: string[];
}

export interface InviteUserResult {
  userId: string;
  email: string;
}

export type SchoolRole = 'admin' | 'teacher' | 'student' | 'member';

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

/**
 * Invite a user (invite-only platform). Sends the Supabase invite email, then
 * — if requested — assigns a platform role and grants school memberships via
 * FastAPI. Role/school failures are surfaced but do not undo the invite.
 */
export async function inviteUser(data: InviteUserRequest): Promise<InviteUserResult> {
  const result = await apiClient.post<InviteUserResult>('/users/invite', {
    email: data.email,
    full_name: data.full_name,
  });

  if (result.userId) {
    if (data.role_id) {
      await assignRoleToUser(result.userId, data.role_id);
    }
    if (data.school_ids?.length) {
      // First granted school becomes primary.
      for (let i = 0; i < data.school_ids.length; i++) {
        await grantUserSchool(result.userId, {
          school_id: data.school_ids[i],
          school_role: 'member',
          is_primary: i === 0,
        });
      }
    }
  }

  return result;
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
