// Permission string format (module:action)
export type PermissionString = `${string}:${string}`;

// Custom claims shape injected by the Supabase auth hook into the JWT payload
export interface RBACClaims {
  permissions?: string[];
  hierarchy_level?: number;
  user_role?: string;
}
