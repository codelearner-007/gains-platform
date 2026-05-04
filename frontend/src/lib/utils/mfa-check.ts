import type { SupabaseClient } from '@supabase/supabase-js';

export interface MFACheckResult {
  hasVerifiedMFA: boolean;
  currentLevel: 'aal1' | 'aal2';
  requiresMFA: boolean;
}

/**
 * Check if user has verified MFA factors and current AAL level.
 *
 * Fails CLOSED: on any error, treat the user as if they have MFA enabled
 * but haven't satisfied AAL2 yet. Callers (`enforceMFAForOperation`) will
 * then block the request, which is the secure default.
 */
export async function checkMFAStatus(
  supabase: SupabaseClient
): Promise<MFACheckResult> {
  try {
    const [{ data: aal }, { data: factors }] = await Promise.all([
      supabase.auth.mfa.getAuthenticatorAssuranceLevel(),
      supabase.auth.mfa.listFactors(),
    ]);

    const currentLevel = (aal?.currentLevel === 'aal2' ? 'aal2' : 'aal1') as 'aal1' | 'aal2';

    const hasVerifiedMFA =
      factors?.totp?.some((f) => f.status === 'verified') ||
      factors?.phone?.some((f) => f.status === 'verified') ||
      false;

    const requiresMFA = hasVerifiedMFA && currentLevel === 'aal1';

    return { hasVerifiedMFA, currentLevel, requiresMFA };
  } catch (error) {
    console.error('MFA check error (failing closed):', error);
    // Fail closed: assume MFA enrolled and not satisfied so callers block.
    return { hasVerifiedMFA: true, currentLevel: 'aal1', requiresMFA: true };
  }
}

/**
 * Enforce MFA verification for operations requiring AAL2.
 * Returns a 403 response when MFA is required but not verified.
 */
export async function enforceMFAForOperation(
  supabase: SupabaseClient
): Promise<Response | null> {
  const { hasVerifiedMFA, currentLevel } = await checkMFAStatus(supabase);

  if (hasVerifiedMFA && currentLevel !== 'aal2') {
    return Response.json(
      { error: 'MFA verification required', requiresMFA: true },
      { status: 403 }
    );
  }

  return null;
}
