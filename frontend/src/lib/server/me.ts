/**
 * Server-side utility to fetch current user with app_metadata
 *
 * Used for server-side route gating in admin pages
 */

import { cookies } from 'next/headers';
import { createSSRClient } from '@/lib/supabase/server';
import { GAINS_FRAMED_COOKIE } from '@/lib/lti/constants';
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
      hierarchy_rank: customClaims.hierarchy_rank,
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
 * Server-side: is the current session a Schoology-embedded (LTI) user?
 *
 * Reads the signed `is_lti_user` JWT claim directly (no MFA/user round-trip) so
 * the `/app` shell can be rendered locked-down on first paint (no flash of the
 * full nav), and also backs the account-mutation API guard (`forbidLtiUser`).
 * Fails to `false` (treat as a normal account) on any error: a real LTI user
 * always carries the claim, so the only false-negative is a transient read
 * hiccup on a request that already needs a valid session to do anything.
 */
export async function getIsLtiUser(): Promise<boolean> {
  try {
    const supabase = await createSSRClient();
    const { data, error } = await supabase.auth.getClaims();
    if (error) return false;
    return (data?.claims as RBACClaims | undefined)?.is_lti_user === true;
  } catch {
    return false;
  }
}

/**
 * Server-side: is the current request rendered inside the Schoology iframe?
 *
 * Keyed on the `gains-framed` cookie — set ONLY by the LTI bridge (httpOnly,
 * partitioned to schoology.com) and the authoritative "in-frame" signal. Drives
 * the CHROME-LESS shell (no sidebar/header/logo) and suppresses cookie consent.
 * UX signal ONLY — account/security lock-down stays keyed on the `is_lti_user`
 * claim (see `getIsLtiUser` / `forbidLtiUser`). Fails to `false` (standard
 * chrome) on any error — the safe default.
 */
export async function getIsFramed(): Promise<boolean> {
  try {
    const cookieStore = await cookies();
    return cookieStore.has(GAINS_FRAMED_COOKIE);
  } catch {
    return false;
  }
}

/**
 * Get user claims for RBAC checks
 */
export function getUserClaims(user: CurrentUser | null) {
  return {
    permissions: user?.app_metadata?.permissions ?? [],
    hierarchy_rank: user?.app_metadata?.hierarchy_rank,
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
