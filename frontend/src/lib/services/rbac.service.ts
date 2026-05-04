/**
 * RBAC Service - API client for role and permission management
 *
 * Calls FastAPI backend via Next.js rewrites (/api/v1)
 * Uses frontend API routes only for auth operations (ban, delete, etc.)
 */

import { apiClient } from './api-client';

// Response types matching FastAPI backend
export interface RoleResponse {
  id: string;
  name: string;
  description: string | null;
  hierarchy_level: number;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface PermissionResponse {
  id: string;
  module: string;
  action: string;
  name: string; // Computed: "module:action"
  description: string | null;
  created_at: string;
}

export interface PermissionsGroupedByModule {
  module: string;
  permissions: PermissionResponse[];
}

export interface RoleWithPermissions extends RoleResponse {
  permissions: PermissionResponse[];
}

/**
 * List all roles
 */
export async function listRoles(): Promise<RoleResponse[]> {
  return apiClient.get<RoleResponse[]>('/v1/roles');
}

/**
 * Get role with permissions
 */
export async function getRoleWithPermissions(roleId: string): Promise<RoleWithPermissions> {
  return apiClient.get<RoleWithPermissions>(`/v1/roles/${roleId}`);
}

/**
 * Get role permissions
 */
export async function getRolePermissions(roleId: string): Promise<PermissionResponse[]> {
  return apiClient.get<PermissionResponse[]>(`/v1/roles/${roleId}/permissions`);
}

/**
 * Update role permissions (bulk replace)
 */
export async function updateRolePermissions(
  roleId: string,
  permissionIds: string[]
): Promise<PermissionResponse[]> {
  return apiClient.put<PermissionResponse[]>(`/v1/roles/${roleId}/permissions`, {
    permission_ids: permissionIds,
  });
}

/**
 * List all permissions grouped by module
 */
export async function listPermissionsGrouped(): Promise<PermissionsGroupedByModule[]> {
  return apiClient.get<PermissionsGroupedByModule[]>('/v1/permissions');
}

/**
 * Create a new role
 */
export async function createRole(data: {
  name: string;
  description?: string;
  hierarchy_level?: number;
}): Promise<RoleResponse> {
  return apiClient.post<RoleResponse>('/v1/roles', data);
}

/**
 * Update a role
 */
export async function updateRole(
  roleId: string,
  data: {
    name?: string;
    description?: string;
    hierarchy_level?: number;
  }
): Promise<RoleResponse> {
  return apiClient.patch<RoleResponse>(`/v1/roles/${roleId}`, data);
}

/**
 * Delete a role
 */
export async function deleteRole(roleId: string): Promise<void> {
  return apiClient.delete<void>(`/v1/roles/${roleId}`);
}

// ============================================================================
// User Management
// ============================================================================

export interface UserRoleResponse {
  id: string;
  user_id: string;
  role_id: string;
  role: RoleResponse;
  created_at: string;
}

export interface UserWithRoles {
  id: string;
  email: string;
  created_at: string;
  updated_at: string;
  last_sign_in_at?: string | null;
  email_confirmed_at?: string | null;
  banned_until?: string | null;
  is_banned: boolean;
  roles: UserRoleResponse[];
}

export interface UserStats {
  total_users: number;
  active_users: number;
  banned_users: number;
  verified_users: number;
  new_users_30d: number;
}

export interface UserFilters {
  page: number;
  page_size: number;
  role?: string;
  email_verified?: boolean;
  status?: 'active' | 'banned';
  search?: string;
}

export interface PaginatedUsersResponse {
  items: UserWithRoles[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/**
 * Get user statistics
 */
export async function getUserStats(): Promise<UserStats> {
  return apiClient.get<UserStats>('/v1/users/stats');
}

/**
 * List users with roles embedded (single request, no N+1).
 */
export async function listUsersWithRoles(
  filters: UserFilters
): Promise<PaginatedUsersResponse> {
  const queryString = new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => [k, String(v)])
  ).toString();

  return apiClient.get<PaginatedUsersResponse>(`/v1/users/with-roles?${queryString}`);
}

/**
 * Get user's assigned roles
 */
export async function getUserRoles(userId: string): Promise<UserRoleResponse[]> {
  return apiClient.get<UserRoleResponse[]>(`/v1/users/${userId}/roles`);
}

/**
 * Assign a role to a user
 */
export async function assignRoleToUser(
  userId: string,
  roleId: string
): Promise<UserRoleResponse> {
  return apiClient.post<UserRoleResponse>(`/v1/users/${userId}/roles`, { role_id: roleId });
}

/**
 * Remove a role from a user
 */
export async function removeRoleFromUser(
  userId: string,
  roleId: string
): Promise<void> {
  return apiClient.delete<void>(`/v1/users/${userId}/roles/${roleId}`);
}

/**
 * Ban a user (uses frontend API with Supabase admin client)
 */
export async function banUser(userId: string, duration: string = '8760h'): Promise<void> {
  await apiClient.post<void>(`/users/${userId}/ban`, { duration });
}

/**
 * Unban a user (uses frontend API with Supabase admin client)
 */
export async function unbanUser(userId: string): Promise<void> {
  await apiClient.post<void>(`/users/${userId}/unban`);
}

/**
 * Delete a user permanently (uses frontend API with Supabase admin client)
 */
export async function deleteUser(userId: string): Promise<void> {
  await apiClient.delete<void>(`/users/${userId}/delete`);
}

/**
 * Resend verification email to user (uses frontend API with Supabase admin client)
 */
export async function resendVerificationEmail(userId: string): Promise<void> {
  await apiClient.post<void>(`/users/${userId}/resend-verification`);
}

/**
 * Send password reset email to user (uses frontend API with Supabase admin client)
 */
export async function sendPasswordResetEmail(userId: string): Promise<void> {
  await apiClient.post<void>(`/users/${userId}/reset-password`);
}
