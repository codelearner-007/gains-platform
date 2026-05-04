import { Database } from './database.types';

// Database types
export type Role = Database['public']['Tables']['roles']['Row'];
export type Permission = Database['public']['Tables']['permissions']['Row'];
export type UserRole = Database['public']['Tables']['user_roles']['Row'];
export type RolePermission = Database['public']['Tables']['role_permissions']['Row'];

// Permission string format (module:action)
export type PermissionString = `${string}:${string}`;

// Custom claims shape injected by the Supabase auth hook into the JWT payload
export interface RBACClaims {
  permissions?: string[];
  hierarchy_level?: number;
  user_role?: string;
}

// User with RBAC data (from JWT)
export interface UserWithRBAC {
  id: string;
  email: string;
  user_role: string;
  permissions: PermissionString[];
  hierarchy_level: number;
}
