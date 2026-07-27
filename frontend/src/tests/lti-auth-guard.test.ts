import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';

// Every Next.js account-MUTATION auth route must reject Schoology-embedded (LTI)
// users — the frontend twin of the backend `forbid_lti_user`. Regression guard:
// an adversarial review found these were the unguarded half of the
// account-mutation boundary. Concretely, an LTI user (whose account has no
// password) could POST /api/auth/reset-password to SET one → a standalone
// password login that escapes the lock-down; or self-enroll MFA → bounce their
// own next Schoology launch to /auth/2fa (self-DoS). These are source-level
// assertions (no RTL/jsdom harness here) that the guard stays wired.
const dir = dirname(fileURLToPath(import.meta.url));
const apiAuth = join(dir, '..', 'app', 'api', 'auth');
const read = (p: string) => readFileSync(join(apiAuth, p), 'utf8');

const GUARDED_ROUTES = [
  'reset-password/route.ts',
  'change-password/route.ts',
  'mfa/enroll/route.ts',
  'mfa/verify/route.ts',
  'mfa/challenge/route.ts',
  'mfa/unenroll/route.ts',
];

describe('LTI users are rejected on account-mutation auth routes', () => {
  for (const route of GUARDED_ROUTES) {
    it(`${route} wires forbidLtiUser()`, () => {
      const src = read(route);
      expect(src).toContain("from '@/lib/server/lti-guard'");
      expect(src).toMatch(/const ltiError = await forbidLtiUser\(\)/);
      expect(src).toMatch(/if \(ltiError\) return ltiError/);
    });
  }
});
