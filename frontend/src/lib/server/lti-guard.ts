import { NextResponse } from 'next/server';
import { getIsLtiUser } from '@/lib/server/me';

/**
 * API-route guard: reject Schoology-embedded (LTI) users on account-mutation
 * endpoints (password change, MFA enroll/unenroll). The frontend twin of the
 * backend `forbid_lti_user`.
 *
 * LTI users get a locked, analytics-only experience. These `/api/auth/*` routes
 * carry no per-user-type check of their own, so a crafted same-origin call from
 * an LTI session could otherwise mutate account/MFA state — and an LTI user who
 * self-enrolls MFA would lock themselves out of the iframe launch (the bridge
 * AAL gate bounces them to /auth/2fa, which has no flow inside Schoology). This
 * closes that boundary at the edge, matching the FastAPI guard.
 *
 * Returns a 403 NextResponse to short-circuit, or null to proceed. An absent or
 * unreadable claim → null (treated as a normal account) — the safe default for
 * the lock-down. Reads are never guarded; this is mutations only.
 */
export async function forbidLtiUser(): Promise<NextResponse | null> {
  if (await getIsLtiUser()) {
    return NextResponse.json(
      { error: 'This action is not available for Schoology-integrated accounts' },
      { status: 403 },
    );
  }
  return null;
}
