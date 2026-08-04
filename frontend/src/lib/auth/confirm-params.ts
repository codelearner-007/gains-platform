/**
 * Shared, logic-only helpers for the email-confirm flow.
 *
 * Imported by BOTH the interstitial page (app/auth/confirm/page.tsx) and the
 * confirm route (app/api/auth/confirm/route.ts) so the page can never render a
 * link the route would then reject. Nothing here consumes a token: token
 * validation of authenticity is verifyOtp's job, and only on an explicit human
 * submit. These helpers only check shape and resolve safe redirect targets.
 */

export const ALLOWED_CONFIRM_TYPES = [
  'invite',
  'magiclink',
  'recovery',
  'email_change',
  'email',
] as const;

export type ConfirmType = (typeof ALLOWED_CONFIRM_TYPES)[number];

export function isConfirmType(value: string | null | undefined): value is ConfirmType {
  return !!value && (ALLOWED_CONFIRM_TYPES as readonly string[]).includes(value);
}

/**
 * Where each confirm type forwards the user once the token is verified. Also the
 * fallback whenever an incoming `next` is missing or not allow-listed, so a
 * mangled `next` degrades to a sensible destination instead of a dead link.
 */
const DEFAULT_NEXT_BY_TYPE: Record<ConfirmType, string> = {
  invite: '/auth/accept-invite',
  recovery: '/auth/reset-password',
  magiclink: '/app',
  email_change: '/app',
  email: '/app',
};

/**
 * Exact internal path prefixes a confirmed session may be forwarded to. Kept in
 * one place so the page and the route cannot disagree about what is allowed.
 */
const ALLOWED_NEXT_PREFIXES = [
  '/app',
  '/admin',
  '/auth/reset-password',
  '/auth/accept-invite',
  '/auth/2fa',
];

/**
 * Normalize a caller-supplied `next` to a safe, allow-listed internal path, or
 * null if it is not allowed.
 *
 * Normalizing through the URL parser collapses any `.` / `..` segments and
 * percent-encoding FIRST, so a value like `/app/../evil` cannot slip past the
 * prefix check by looking allow-listed while resolving elsewhere. The dummy
 * origin guarantees the result is always same-origin; the query string is
 * preserved but the prefix match is on the pathname alone.
 */
function normalizeAllowedNext(next: string | null | undefined): string | null {
  if (!next) return null;
  if (!next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return null;
  let url: URL;
  try {
    url = new URL(next, 'http://internal.invalid');
  } catch {
    return null;
  }
  const path = url.pathname;
  const allowed = ALLOWED_NEXT_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
  return allowed ? path + url.search : null;
}

/**
 * Resolve a safe forward target: the normalized, allow-listed `next` when it is
 * permitted, otherwise the type's default. Never returns an off-origin, escaped,
 * or unexpected path, so it doubles as the open-redirect guard.
 */
export function resolveNext(type: ConfirmType, next: string | null | undefined): string {
  return normalizeAllowedNext(next) ?? DEFAULT_NEXT_BY_TYPE[type];
}

/**
 * Supabase token_hash values are compact, URL-safe tokens (hex, base64url, or a
 * `pkce_`-prefixed form). Bound the length and charset so a mangled or hostile
 * link fails fast and nothing odd is reflected into the page's hidden field.
 * This is a SHAPE gate only: it never proves the token is valid. Only verifyOtp
 * can, and only on the explicit human submit.
 */
const TOKEN_HASH_PATTERN = /^[A-Za-z0-9_-]{1,512}$/;

export function isValidTokenHashShape(value: string | null | undefined): value is string {
  return !!value && TOKEN_HASH_PATTERN.test(value);
}

/**
 * The one-time token is handed from the email link to the human-submitted POST
 * through this short-lived, httpOnly cookie rather than a page URL, so it never
 * reaches the client page (and thus never any analytics, browser history, or
 * Referer). The GET route sets it; the POST route reads and clears it.
 */
export const CONFIRM_COOKIE = 'gains-confirm';

export type ConfirmPayload = {
  token_hash: string;
  type: ConfirmType;
  next: string;
};

export function serializeConfirmPayload(payload: ConfirmPayload): string {
  return JSON.stringify(payload);
}

/**
 * Parse and fully re-validate the confirm cookie. Returns null for anything
 * malformed, so the POST route treats a tampered or absent cookie exactly like
 * an expired link (never trusting its contents without re-checking shape).
 */
export function parseConfirmPayload(raw: string | null | undefined): ConfirmPayload | null {
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object') return null;
  const record = parsed as Record<string, unknown>;
  const tokenHash = typeof record.token_hash === 'string' ? record.token_hash : null;
  const type = typeof record.type === 'string' ? record.type : null;
  const next = record.next;
  if (!isValidTokenHashShape(tokenHash) || !isConfirmType(type) || typeof next !== 'string') {
    return null;
  }
  return { token_hash: tokenHash, type, next };
}
