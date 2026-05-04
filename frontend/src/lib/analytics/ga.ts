import { publicSettings } from '@/lib/core/public-settings';
import type { AnalyticsEventName, AnalyticsEventParamsMap } from '@/lib/analytics/events';

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
    dataLayer?: unknown[];
  }
}

type QueuedEvent = {
  name: AnalyticsEventName;
  params: Record<string, unknown>;
};

const MAX_QUEUE = 50;
let queue: QueuedEvent[] = [];
let flushScheduled = false;
let currentUserId: string | null = null;
let flushAttempts = 0;

function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

function getGtag(): Window['gtag'] | null {
  if (!isBrowser()) return null;
  return typeof window.gtag === 'function' ? window.gtag : null;
}

function withDevDebugMode(params: Record<string, unknown>): Record<string, unknown> {
  if (!isBrowser()) return params;
  if (publicSettings.NODE_ENV !== 'development') return params;
  return { ...params, debug_mode: true };
}

function sanitizeParams(params: Record<string, unknown>): Record<string, unknown> {
  const deny = new Set([
    'email',
    'user_email',
    'name',
    'full_name',
    'first_name',
    'last_name',
    'phone',
    'token',
    'access_token',
    'refresh_token',
    'password',
    'secret',
    'value',
    'content',
    'notes',
    'message',
    'error_message',
    'stack',
  ]);

  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) {
    if (deny.has(k)) continue;
    out[k] = v;
  }
  return out;
}

function applyUserIdIfPossible(gtag: NonNullable<Window['gtag']>) {
  const gaId = publicSettings.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  if (!gaId) return;
  gtag('config', gaId, { user_id: currentUserId ?? undefined });
}

function flushQueue() {
  const gtag = getGtag();
  if (!gtag) return;
  applyUserIdIfPossible(gtag);
  const toSend = queue;
  queue = [];
  for (const item of toSend) {
    gtag('event', item.name, item.params);
  }
}

function scheduleFlush() {
  if (!isBrowser()) return;
  if (flushScheduled) return;
  flushScheduled = true;
  const tick = () => {
    const gtag = getGtag();
    if (gtag) {
      flushAttempts = 0;
      flushScheduled = false;
      flushQueue();
      return;
    }

    flushAttempts += 1;
    if (flushAttempts >= 10) {
      flushScheduled = false;
      flushAttempts = 0;
      return;
    }

    const delayMs = Math.min(2000, 50 * Math.pow(2, flushAttempts));
    window.setTimeout(tick, delayMs);
  };

  window.setTimeout(tick, 0);
}

export function setAnalyticsUserId(appUserId: string | null) {
  currentUserId = appUserId;
  const gtag = getGtag();
  if (gtag) applyUserIdIfPossible(gtag);
}

export function trackEvent<N extends AnalyticsEventName>(
  name: N,
  params: AnalyticsEventParamsMap[N]
) {
  const gaId = publicSettings.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  if (!gaId) return;
  if (!isBrowser()) return;

  const gtag = getGtag();
  const safeParams = withDevDebugMode(sanitizeParams(params as unknown as Record<string, unknown>));

  if (!gtag) {
    queue = [...queue.slice(-(MAX_QUEUE - 1)), { name, params: safeParams }];
    scheduleFlush();
    return;
  }

  applyUserIdIfPossible(gtag);
  gtag('event', name, safeParams);
}
