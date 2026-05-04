import Redis from 'ioredis';
import { serverSettings } from '../core/server-settings';

let _client: Redis | null = null;

function redactRedisUrl(raw: string): string {
  try {
    const u = new URL(raw);
    if (u.password) u.password = '***';
    if (u.username) u.username = '***';
    return u.toString();
  } catch {
    return '[invalid-redis-url]';
  }
}

/**
 * Lazy singleton Redis client for Next.js server runtime (route handlers).
 * Returns null when FRONTEND_REDIS_URL is unset.
 */
export function getRedisClient(): Redis | null {
  const url = serverSettings.FRONTEND_REDIS_URL?.trim();
  if (!url) {
    return null;
  }

  if (!_client) {
    _client = new Redis(url, {
      maxRetriesPerRequest: 2,
      enableReadyCheck: true,
      lazyConnect: false,
    });
    _client.on('error', (err) => {
      console.error('[redis-client]', redactRedisUrl(url), err.message);
    });
  }

  return _client;
}

export function redactFrontendRedisUrlForLog(raw: string | undefined): string {
  if (!raw?.trim()) return '(unset)';
  return redactRedisUrl(raw);
}
