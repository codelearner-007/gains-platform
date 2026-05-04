import { NextResponse } from 'next/server';
import { publicSettings } from '../core/public-settings';

function normalizeOrigin(value: string): string {
  try {
    return new URL(value).origin;
  } catch {
    return '';
  }
}

function getAllowedOriginsFromEnv(): string[] {
  const candidates = [
    publicSettings.NEXT_PUBLIC_SITE_URL,
    process.env.NEXTAUTH_URL,
    process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : undefined,
  ].filter(Boolean) as string[];

  return candidates.map(normalizeOrigin).filter(Boolean);
}

/**
 * CSRF defense for cookie-authenticated mutation routes.
 *
 * Production: rejects any request whose Origin doesn't match an explicit
 * allowed origin (NEXT_PUBLIC_SITE_URL / NEXTAUTH_URL / VERCEL_URL). The
 * Host header is NOT trusted as a fallback — it can be attacker-controlled
 * via misconfigured reverse proxies.
 *
 * Development: missing Origin (non-browser tooling) is allowed; Host header
 * is accepted as a fallback for localhost/LAN testing.
 */
export function enforceSameOrigin(request: Request): NextResponse | null {
  const method = request.method.toUpperCase();
  const isMutating = method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS';
  if (!isMutating) return null;

  const origin = request.headers.get('origin');
  const isProduction = publicSettings.NODE_ENV === 'production';

  if (!origin) {
    // Non-browser clients often omit Origin. Reject in production, allow in dev.
    if (isProduction) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }
    return null;
  }

  const requestOrigin = normalizeOrigin(origin);
  if (!requestOrigin) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const allowedOrigins = new Set(getAllowedOriginsFromEnv());

  // Dev-only convenience: trust Host header for local/LAN testing.
  if (!isProduction) {
    const host = request.headers.get('host');
    if (host) {
      allowedOrigins.add(`http://${host}`);
      allowedOrigins.add(`https://${host}`);
    }
  }

  if (!allowedOrigins.has(requestOrigin)) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  return null;
}
