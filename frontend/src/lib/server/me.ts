/**
 * Server-side utility to fetch current user with app_metadata
 *
 * Used for server-side route gating in admin pages
 */

import { createSSRClient } from '@/lib/supabase/server';
import { checkMFAStatus } from '@/lib/utils/mfa-check';
import type { AppMetadata, UserMetadata } from '@/lib/types/auth.types';
import type { PermissionString, RBACClaims } from '@/lib/types/rbac.types';

export interface CurrentUser {
  id: string;
  email: string;
  created_at?: string;
  user_metadata?: UserMetadata;
  app_metadata?: AppMetadata;
  requiresMFA?: boolean;
  currentAAL?: string;
}

/**
 * Get current user from Supabase session (server-side only)
 *
 * This is used for server-side route gating to prevent:
 * - UI flicker (showing admin content before permissions are known)
 * - Deep link access (direct URL access to admin pages)
 *
 * @returns User object with app_metadata or null if not authenticated
 */
export async function getMe(): Promise<CurrentUser | null> {
  try {
    const supabase = await createSSRClient();
    const { data: { user }, error } = await supabase.auth.getUser();

    if (error || !user) return null;

    // Check MFA status
    const { currentLevel, requiresMFA } = await checkMFAStatus(supabase);

    const { data: claimsData, error: claimsError } = await supabase.auth.getClaims();
    if (claimsError) {
      console.error('Failed to get JWT claims:', claimsError);
    }

    const customClaims = (claimsData?.claims ?? {}) as RBACClaims;

    // Merge custom JWT claims into app_metadata for consistent access
    const appMetadata = normalizeAppMetadata({
      ...user.app_metadata,
      permissions: (customClaims.permissions || []) as PermissionString[],
      hierarchy_level: customClaims.hierarchy_level,
      user_role: customClaims.user_role,
    });

    return {
      id: user.id,
      email: user.email || '',
      app_metadata: appMetadata,
      user_metadata: user.user_metadata as UserMetadata | undefined,
      created_at: user.created_at,
      requiresMFA,
      currentAAL: currentLevel,
    };
  } catch {
    return null;
  }
}

/**
 * Get user permissions from app_metadata
 */
export function getUserPermissions(user: CurrentUser | null): PermissionString[] {
  return user?.app_metadata?.permissions ?? [];
}

/**
 * Get user claims for RBAC checks
 */
export function getUserClaims(user: CurrentUser | null) {
  return {
    permissions: user?.app_metadata?.permissions ?? [],
    hierarchy_level: user?.app_metadata?.hierarchy_level,
    user_role: user?.app_metadata?.user_role,
  };
}

function normalizeAppMetadata(appMetadata: AppMetadata | undefined): AppMetadata | undefined {
  if (!appMetadata) return undefined;

  const permissions = (appMetadata.permissions ?? []).filter(isPermissionString);
  return {
    ...appMetadata,
    permissions,
  };
}

function isPermissionString(value: unknown): value is PermissionString {
  if (typeof value !== 'string') return false;
  const colonIndex = value.indexOf(':');
  return colonIndex > 0 && colonIndex < value.length - 1;
}
