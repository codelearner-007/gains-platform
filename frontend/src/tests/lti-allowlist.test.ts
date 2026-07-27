import { describe, expect, it } from 'vitest';
import { isLtiAllowedPath, isLtiUser } from '@/lib/rbac/access';

// Schoology-embedded (LTI) users are locked to an analytics-only experience:
// the dashboard and the reports it drills into. The middleware route wall calls
// isLtiAllowedPath with request.nextUrl.pathname (no query string) to enforce
// this. It is an ALLOWLIST — anything not explicitly permitted is blocked, so
// future /app routes are locked-out by default (fail closed).
describe('isLtiAllowedPath', () => {
  it('allows the dashboard (with and without trailing slash)', () => {
    expect(isLtiAllowedPath('/app')).toBe(true);
    expect(isLtiAllowedPath('/app/')).toBe(true);
  });

  it('allows every report route', () => {
    expect(isLtiAllowedPath('/app/reports/standard-summary')).toBe(true);
    expect(isLtiAllowedPath('/app/reports/strand-summary')).toBe(true);
    expect(isLtiAllowedPath('/app/reports/year-to-date-performance')).toBe(true);
    expect(isLtiAllowedPath('/app/reports/question-response-analysis')).toBe(true);
  });

  it('allows per-student reports', () => {
    expect(isLtiAllowedPath('/app/students/019eb11c-abc/report')).toBe(true);
  });

  it('blocks settings / account', () => {
    expect(isLtiAllowedPath('/app/user-settings')).toBe(false);
  });

  it('fails closed for unknown / future /app routes', () => {
    expect(isLtiAllowedPath('/app/billing')).toBe(false);
    expect(isLtiAllowedPath('/app/anything-added-later')).toBe(false);
  });

  it('does not allow paths that merely share a prefix with an allowed one', () => {
    // must be under /app/reports/ or /app/students/, not just start like them
    expect(isLtiAllowedPath('/app/reports-internal')).toBe(false);
    expect(isLtiAllowedPath('/app/studentsomething')).toBe(false);
  });
});

describe('isLtiUser', () => {
  it('is true only when the signed claim is exactly true', () => {
    expect(isLtiUser({ is_lti_user: true })).toBe(true);
  });

  it('is false for normal users, missing claim, null, or undefined', () => {
    expect(isLtiUser({ is_lti_user: false })).toBe(false);
    expect(isLtiUser({})).toBe(false);
    expect(isLtiUser(null)).toBe(false);
    expect(isLtiUser(undefined)).toBe(false);
  });
});
