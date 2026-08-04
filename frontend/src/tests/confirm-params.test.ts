import { describe, expect, it } from 'vitest';
import {
  ALLOWED_CONFIRM_TYPES,
  isConfirmType,
  isValidTokenHashShape,
  parseConfirmPayload,
  resolveNext,
  serializeConfirmPayload,
} from '@/lib/auth/confirm-params';

// These helpers are the single source of truth shared by the /auth/confirm
// interstitial page and the /api/auth/confirm route, so the page can never
// render a link the route would reject. They validate SHAPE only and resolve
// safe redirect targets; nothing here consumes a token.

describe('isConfirmType', () => {
  it('accepts every Supabase email-confirm type in the allowlist', () => {
    for (const type of ALLOWED_CONFIRM_TYPES) {
      expect(isConfirmType(type)).toBe(true);
    }
    // Guard against silent drift of the allowlist.
    expect([...ALLOWED_CONFIRM_TYPES].sort()).toEqual(
      ['email', 'email_change', 'invite', 'magiclink', 'recovery'].sort(),
    );
  });

  it('rejects unknown, empty, and nullish types', () => {
    expect(isConfirmType('signup')).toBe(false);
    expect(isConfirmType('magic_link')).toBe(false); // Supabase uses "magiclink"
    expect(isConfirmType('')).toBe(false);
    expect(isConfirmType(null)).toBe(false);
    expect(isConfirmType(undefined)).toBe(false);
  });
});

describe('isValidTokenHashShape', () => {
  it('accepts the token_hash forms Supabase issues (hex, base64url, pkce_)', () => {
    expect(isValidTokenHashShape('ed60e15c010fd2f444b6eb4a')).toBe(true);
    expect(isValidTokenHashShape('pkce_a1B2c3-_d4E5')).toBe(true);
    expect(isValidTokenHashShape('a'.repeat(512))).toBe(true);
  });

  it('rejects empty, oversized, and non-URL-safe values', () => {
    expect(isValidTokenHashShape('')).toBe(false);
    expect(isValidTokenHashShape(null)).toBe(false);
    expect(isValidTokenHashShape(undefined)).toBe(false);
    expect(isValidTokenHashShape('a'.repeat(513))).toBe(false);
    expect(isValidTokenHashShape('has space')).toBe(false);
    expect(isValidTokenHashShape('<script>')).toBe(false);
    expect(isValidTokenHashShape('tok/../../etc')).toBe(false);
  });
});

describe('resolveNext', () => {
  it('keeps an allow-listed next unchanged', () => {
    expect(resolveNext('invite', '/auth/accept-invite')).toBe('/auth/accept-invite');
    expect(resolveNext('recovery', '/auth/reset-password')).toBe('/auth/reset-password');
    expect(resolveNext('magiclink', '/app')).toBe('/app');
    expect(resolveNext('magiclink', '/app/reports/standard-summary')).toBe(
      '/app/reports/standard-summary',
    );
    expect(resolveNext('magiclink', '/admin')).toBe('/admin');
    expect(resolveNext('magiclink', '/auth/2fa?returnTo=/app')).toBe('/auth/2fa?returnTo=/app');
  });

  it('coerces a missing next to the type default (never a dead link)', () => {
    expect(resolveNext('invite', null)).toBe('/auth/accept-invite');
    expect(resolveNext('invite', undefined)).toBe('/auth/accept-invite');
    expect(resolveNext('recovery', '')).toBe('/auth/reset-password');
    expect(resolveNext('magiclink', null)).toBe('/app');
    expect(resolveNext('email', null)).toBe('/app');
    expect(resolveNext('email_change', null)).toBe('/app');
  });

  it('coerces a non-allow-listed next to the type default', () => {
    expect(resolveNext('magiclink', '/settings')).toBe('/app');
    expect(resolveNext('magiclink', '/apps')).toBe('/app'); // prefix confusion: not /app
    expect(resolveNext('invite', '/appsuffix')).toBe('/auth/accept-invite');
  });

  it('blocks off-origin redirect payloads by coercing to the type default', () => {
    const attacks = [
      '//evil.com',
      '/\\evil.com',
      'https://evil.com',
      'http://evil.com',
      '%2F%2Fevil.com',
      '/app\r\nSet-Cookie:x=y',
      '/app\nlocation:evil',
      'javascript:alert(1)',
      ' /app',
    ];
    for (const next of attacks) {
      const resolved = resolveNext('magiclink', next);
      // Always an allow-listed internal path, never the attacker input.
      expect(resolved).toBe('/app');
      expect(resolved.startsWith('/')).toBe(true);
      expect(resolved.startsWith('//')).toBe(false);
    }
  });

  it('normalizes away .. traversal so it cannot escape the allow-list', () => {
    // Traversal reaching a NON-allow-listed path is coerced to the type default.
    expect(resolveNext('magiclink', '/app/../evil')).toBe('/app');
    expect(resolveNext('magiclink', '/app/../auth/login')).toBe('/app');
    expect(resolveNext('magiclink', '/app/%2e%2e/evil')).toBe('/app');
    expect(resolveNext('invite', '/app/../../secret')).toBe('/auth/accept-invite');
    // Traversal that lands on a genuinely allow-listed path is fine (normalized).
    expect(resolveNext('magiclink', '/app/../admin')).toBe('/admin');
  });
});

describe('confirm cookie payload', () => {
  it('round-trips a valid payload', () => {
    const payload = {
      token_hash: 'ed60e15c010fd2f444b6eb4a',
      type: 'invite' as const,
      next: '/auth/accept-invite',
    };
    expect(parseConfirmPayload(serializeConfirmPayload(payload))).toEqual(payload);
  });

  it('rejects a missing or non-JSON cookie', () => {
    expect(parseConfirmPayload(null)).toBeNull();
    expect(parseConfirmPayload(undefined)).toBeNull();
    expect(parseConfirmPayload('')).toBeNull();
    expect(parseConfirmPayload('not json')).toBeNull();
    expect(parseConfirmPayload('[1,2,3]')).toBeNull();
    expect(parseConfirmPayload('"a string"')).toBeNull();
  });

  it('rejects a tampered payload (bad token shape, bad type, or missing next)', () => {
    expect(
      parseConfirmPayload(JSON.stringify({ token_hash: 'has space', type: 'invite', next: '/app' })),
    ).toBeNull();
    expect(
      parseConfirmPayload(JSON.stringify({ token_hash: 'ok123', type: 'signup', next: '/app' })),
    ).toBeNull();
    expect(
      parseConfirmPayload(JSON.stringify({ token_hash: 'ok123', type: 'invite' })),
    ).toBeNull();
    expect(
      parseConfirmPayload(JSON.stringify({ token_hash: '<script>', type: 'invite', next: '/app' })),
    ).toBeNull();
  });
});
