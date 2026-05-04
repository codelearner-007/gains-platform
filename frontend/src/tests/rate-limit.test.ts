import { describe, expect, it } from 'vitest';
import { getClientKeyFromRequest, parseRateLimitPolicy, truncateClientKeyForLog } from '../lib/utils/rate-limit';

describe('parseRateLimitPolicy', () => {
  it('parses per-minute limits', () => {
    expect(parseRateLimitPolicy('3/minute')).toEqual({ max: 3, windowSeconds: 60 });
    expect(parseRateLimitPolicy('3/minutes')).toEqual({ max: 3, windowSeconds: 60 });
  });

  it('parses per-second and per-hour', () => {
    expect(parseRateLimitPolicy('10/second')).toEqual({ max: 10, windowSeconds: 1 });
    expect(parseRateLimitPolicy('5/hour')).toEqual({ max: 5, windowSeconds: 3600 });
  });

  it('returns null for invalid input', () => {
    expect(parseRateLimitPolicy(undefined)).toBeNull();
    expect(parseRateLimitPolicy('')).toBeNull();
    expect(parseRateLimitPolicy('nope')).toBeNull();
    expect(parseRateLimitPolicy('0/minute')).toBeNull();
  });
});

describe('getClientKeyFromRequest', () => {
  it('uses x-forwarded-for first IP', () => {
    const r = new Request('http://localhost', {
      headers: { 'x-forwarded-for': '203.0.113.1, 10.0.0.1' },
    });
    expect(getClientKeyFromRequest(r)).toBe('203.0.113.1');
  });

  it('falls back to x-real-ip and cf-connecting-ip', () => {
    expect(
      getClientKeyFromRequest(
        new Request('http://localhost', { headers: { 'x-real-ip': ' 1.2.3.4 ' } }),
      ),
    ).toBe('1.2.3.4');
    expect(
      getClientKeyFromRequest(
        new Request('http://localhost', { headers: { 'cf-connecting-ip': '5.6.7.8' } }),
      ),
    ).toBe('5.6.7.8');
  });

  it('uses local-dev when no headers', () => {
    expect(getClientKeyFromRequest(new Request('http://localhost'))).toBe('local-dev');
  });
});

describe('truncateClientKeyForLog', () => {
  it('masks IPv4 last octet', () => {
    expect(truncateClientKeyForLog('203.0.113.44')).toBe('203.0.113.x');
  });
});
