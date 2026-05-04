import { NextResponse } from 'next/server';
import { getRedisClient } from '@/lib/utils/redis-client';
import { serverSettings } from '../core/server-settings';

/** Lua: INCR key; EXPIRE on first hit. Returns current count. */
const INCR_EXPIRE_SCRIPT = `
local c = redis.call('INCR', KEYS[1])
if c == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return c
`;

export type ParsedRateLimit = {
  max: number;
  windowSeconds: number;
};

/**
 * Parses strings like `3/minute`, `10/second`, `60/hour` (case-insensitive).
 */
export function parseRateLimitPolicy(raw: string | undefined): ParsedRateLimit | null {
  const s = raw?.trim();
  if (!s) return null;
  const m = /^(\d+)\s*\/\s*(second|minute|hour)s?$/i.exec(s);
  if (!m) return null;
  const max = Number.parseInt(m[1], 10);
  if (!Number.isFinite(max) || max < 1) return null;
  const unit = m[2].toLowerCase();
  const windowSeconds =
    unit === 'second' ? 1 : unit === 'minute' ? 60 : unit === 'hour' ? 3600 : 0;
  if (windowSeconds < 1) return null;
  return { max, windowSeconds };
}

function defaultPolicy(): ParsedRateLimit {
  return { max: 60, windowSeconds: 60 };
}

function sanitizeRouteSegment(routeId: string): string {
  return routeId.replace(/[^a-zA-Z0-9_-]/g, '_');
}

function sanitizeClientKey(clientKey: string): string {
  return clientKey.replace(/[^a-zA-Z0-9.:-]/g, '_');
}

export function getClientKeyFromRequest(request: Request): string {
  const forwarded = request.headers.get('x-forwarded-for');
  if (forwarded) {
    const first = forwarded.split(',')[0]?.trim();
    if (first) return first;
  }
  const realIp = request.headers.get('x-real-ip')?.trim();
  if (realIp) return realIp;
  const cf = request.headers.get('cf-connecting-ip')?.trim();
  if (cf) return cf;
  return 'local-dev';
}

export function truncateClientKeyForLog(clientKey: string): string {
  if (clientKey === 'local-dev') return clientKey;
  if (clientKey.includes('.')) {
    const parts = clientKey.split('.');
    if (parts.length === 4) {
      return `${parts[0]}.${parts[1]}.${parts[2]}.x`;
    }
  }
  return clientKey.length > 12 ? `${clientKey.slice(0, 12)}…` : clientKey;
}

function buildRedisKey(prefix: string, routeId: string, clientKey: string, windowStartSec: number): string {
  const p = prefix.trim() || 'starter_template';
  return `${p}:ratelimit:${sanitizeRouteSegment(routeId)}:${sanitizeClientKey(clientKey)}:${windowStartSec}`;
}

function isRateLimitEnabled(): boolean {
  return serverSettings.FRONTEND_RATE_LIMIT_ENABLED;
}

function isFailOpen(): boolean {
  return serverSettings.FRONTEND_RATE_LIMIT_FAIL_OPEN;
}

function getRedisPrefix(): string {
  return serverSettings.FRONTEND_REDIS_PREFIX?.trim() || 'starter_template';
}

export type RateLimitCheckResult =
  | { action: 'allow'; limit: number; remaining: number; resetUnix: number }
  | { action: 'bypass' }
  | {
      action: 'block';
      kind: 'rate_limit';
      limit: number;
      resetUnix: number;
      retryAfterSeconds: number;
    }
  | {
      action: 'block';
      kind: 'service_unavailable';
      limit: number;
      resetUnix: number;
      retryAfterSeconds: number;
    };

export type CheckRateLimitOptions = {
  request: Request;
  /** Short id, e.g. `auth_me` */
  routeId: string;
  /** e.g. `3/minute` from env */
  policyRaw: string | undefined;
};

/**
 * Fixed-window counter in Redis. When Redis is unavailable, behavior follows FRONTEND_RATE_LIMIT_FAIL_OPEN.
 */
export async function checkRateLimit(options: CheckRateLimitOptions): Promise<RateLimitCheckResult> {
  if (!isRateLimitEnabled()) {
    return { action: 'bypass' };
  }

  let policy = parseRateLimitPolicy(options.policyRaw);
  if (!policy) {
    if (options.policyRaw?.trim()) {
      console.warn('[rate-limit] invalid policy, falling back to 60/minute', options.policyRaw);
    }
    policy = defaultPolicy();
  }

  const nowSec = Math.floor(Date.now() / 1000);
  const windowStart = Math.floor(nowSec / policy.windowSeconds) * policy.windowSeconds;
  const resetUnix = windowStart + policy.windowSeconds;
  const retryAfterFallback = Math.max(1, resetUnix - nowSec);

  const redis = getRedisClient();
  if (!redis) {
    // No Redis configured at all: rate limiting is intentionally disabled.
    // FRONTEND_RATE_LIMIT_ENABLED + FRONTEND_REDIS_URL together drive policy.
    return { action: 'bypass' };
  }

  const clientKey = getClientKeyFromRequest(options.request);
  const key = buildRedisKey(getRedisPrefix(), options.routeId, clientKey, windowStart);

  try {
    const count = (await redis.eval(
      INCR_EXPIRE_SCRIPT,
      1,
      key,
      String(policy.windowSeconds),
    )) as number;

    if (count > policy.max) {
      return {
        action: 'block',
        kind: 'rate_limit',
        limit: policy.max,
        resetUnix,
        retryAfterSeconds: Math.max(1, resetUnix - nowSec),
      };
    }

    const remaining = Math.max(0, policy.max - count);
    return { action: 'allow', limit: policy.max, remaining, resetUnix };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (isFailOpen()) {
      console.error('[rate-limit] redis error; fail-open', { route: options.routeId, error: msg });
      return { action: 'bypass' };
    }
    console.error('[rate-limit] redis error; fail-closed', { route: options.routeId, error: msg });
    return {
      action: 'block',
      kind: 'service_unavailable',
      limit: policy.max,
      resetUnix,
      retryAfterSeconds: retryAfterFallback,
    };
  }
}

function rateLimitHeaders(
  result: Extract<RateLimitCheckResult, { action: 'allow' } | { action: 'block' }>,
): Record<string, string> {
  const reset = String(result.resetUnix);
  if (result.action === 'allow') {
    return {
      'X-RateLimit-Limit': String(result.limit),
      'X-RateLimit-Remaining': String(result.remaining),
      'X-RateLimit-Reset': reset,
    };
  }
  if (result.kind === 'rate_limit') {
    return {
      'X-RateLimit-Limit': String(result.limit),
      'X-RateLimit-Remaining': '0',
      'X-RateLimit-Reset': reset,
      'Retry-After': String(result.retryAfterSeconds),
    };
  }
  return {
    'X-RateLimit-Limit': String(result.limit),
    'X-RateLimit-Remaining': '0',
    'X-RateLimit-Reset': reset,
    'Retry-After': String(result.retryAfterSeconds),
  };
}

/**
 * Returns a NextResponse to short-circuit the handler, or null to continue.
 */
export async function enforceRateLimitResponse(
  options: CheckRateLimitOptions,
): Promise<NextResponse | null> {
  const result = await checkRateLimit(options);
  const clientLog = truncateClientKeyForLog(getClientKeyFromRequest(options.request));

  if (result.action === 'bypass' || result.action === 'allow') {
    return null;
  }

  if (result.kind === 'service_unavailable') {
    console.warn('[rate-limit] blocked (fail-closed / no redis)', {
      route: options.routeId,
      client: clientLog,
    });
    return NextResponse.json(
      { error: 'Service temporarily unavailable' },
      { status: 503, headers: rateLimitHeaders(result) },
    );
  }

  console.warn(
    JSON.stringify({
      event: 'rate_limit',
      decision: 'blocked',
      route: options.routeId,
      client: clientLog,
    }),
  );
  return NextResponse.json(
    { error: 'Too many requests' },
    { status: 429, headers: rateLimitHeaders(result) },
  );
}
