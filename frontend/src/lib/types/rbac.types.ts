// Permission string format (module:action)
export type PermissionString = `${string}:${string}`;

// Custom claims shape injected by the Supabase auth hook into the JWT payload
export interface RBACClaims {
  permissions?: string[];
  hierarchy_rank?: number;
  user_role?: string;
  // True for Schoology-embedded (LTI-provisioned) accounts. Derived in the auth
  // hook from the durable lti_user_identity row, not the email string.
  is_lti_user?: boolean;
}
