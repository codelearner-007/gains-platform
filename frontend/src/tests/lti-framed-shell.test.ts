import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';

// The /app shell strips its chrome for Schoology-embedded launches. Regression
// guard: the strip must key on FRAMED CONTEXT (the `gains-framed` cookie, set
// only by the LTI bridge) — NOT on the per-user `is_lti_user` claim. Gating on
// the user claim stripped the shell for LTI-flagged users EVERYWHERE, including
// the standalone platform (the bug). Security (account-mutation lock-down) stays
// keyed on `is_lti_user` and is untouched. These are source-level assertions (no
// RTL/jsdom harness here); the visual "no sidebar / no banner" is the manual
// browser gate.
const dir = dirname(fileURLToPath(import.meta.url)); // src/tests
const src = (p: string) => readFileSync(join(dir, '..', p), 'utf8');

describe('framed shell is gated on context (gains-framed), not the user claim', () => {
  it('me.ts exposes getIsFramed reading the gains-framed cookie', () => {
    const me = src('lib/server/me.ts');
    expect(me).toMatch(/export async function getIsFramed\(\)/);
    // Reads the marker via the shared constant (one cross-module contract), not
    // a re-typed literal — see lib/lti/constants.ts.
    expect(me).toContain('cookieStore.has(GAINS_FRAMED_COOKIE)');
    expect(me).toMatch(/import \{ GAINS_FRAMED_COOKIE \} from '@\/lib\/lti\/constants'/);
  });

  it('the gains-framed writer + both readers share one constant', () => {
    expect(src('lib/lti/constants.ts')).toMatch(
      /export const GAINS_FRAMED_COOKIE = 'gains-framed'/,
    );
    // writer (bridge) + transport reader (middleware) both use the symbol
    expect(src('app/api/lti/bridge/route.ts')).toContain(
      'res.cookies.set(GAINS_FRAMED_COOKIE',
    );
    expect(src('lib/supabase/middleware.ts')).toContain(
      'request.cookies.has(GAINS_FRAMED_COOKIE)',
    );
  });

  it('ProtectedShellLayout branches on framed context, not the user claim', () => {
    const shell = src('components/common/ProtectedShellLayout.tsx');
    expect(shell).toContain('getIsFramed');
    expect(shell).not.toContain('getIsLtiUser'); // UX no longer keys on the user claim
    expect(shell).toMatch(/const framed = await getIsFramed\(\)/);
    // framed => chrome-less <main>; not-framed => full <AppLayout>
    expect(shell).toMatch(/framed \?[\s\S]*<main/);
    expect(shell).toMatch(/<AppLayout>\{children\}<\/AppLayout>/);
  });

  it('AppLayout has no LTI/framed flag — always the full shell', () => {
    const app = src('components/common/AppLayout.tsx');
    expect(app).not.toMatch(/isLtiUser/); // prop + all bare-shell branches gone
    expect(app).toContain('<SchoolSwitcher />'); // unconditional
    expect(app).toContain("name: 'Settings'"); // Settings nav always present
  });

  it('root layout suppresses the cookie banner only when framed', () => {
    const root = src('app/layout.tsx');
    expect(root).toContain('getIsFramed');
    expect(root).toMatch(/const framed = await getIsFramed\(\)/);
    expect(root).toMatch(/\{!framed && <CookieConsent \/>\}/);
  });
});

describe('security invariance: is_lti_user account lock-down is untouched', () => {
  // A standalone LTI-flagged user now gets the FULL shell (UX), yet an
  // account-mutation call still 403s — because security keys on is_lti_user,
  // which the shell change did not touch.
  it('getIsLtiUser still exists and still backs the account-mutation guard', () => {
    expect(src('lib/server/me.ts')).toMatch(/export async function getIsLtiUser\(\)/);
    const guard = src('lib/server/lti-guard.ts');
    expect(guard).toContain('getIsLtiUser');
    expect(guard).toMatch(/status:\s*403/);
  });

  // The runtime 403 on all 6 /api/auth/* mutation routes is covered by
  // lti-auth-guard.test.ts — not duplicated here.
});
