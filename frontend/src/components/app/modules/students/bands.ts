/**
 * Per-student report design tokens.
 *
 * An editorial palette (deep navy ink, brass accent, warm porcelain) layered
 * over the platform's traffic-light performance bands (from lib/reports/colors)
 * so the report reads as a considered document, not a default dashboard, while
 * staying colour-consistent with every other report. Band → colour lives here
 * once; the server hands the UI a ``band`` string so no thresholds are dupliated.
 */
import {
  PERF_BAND_HIGH,
  PERF_BAND_LOW,
  PERF_BAND_MID,
  PERF_GREEN,
  PERF_PINK,
  PERF_YELLOW,
  type PerfBand,
} from '@/lib/reports/colors';
import type { PerfBandName } from '@/lib/reports/types';

/** Editorial brand tokens (WCAG-AA on porcelain/paper). */
export const BRAND = {
  navy: '#0F1D3D', // display ink / rules
  navySoft: '#28406B', // secondary ink
  brass: '#9A6114', // accent text (AA on porcelain)
  brassBright: '#C8891F', // accent fills / markers
  porcelain: '#F7F5EF', // warm page ground
  paper: '#FFFFFF',
  ink: '#1B2333',
  muted: '#6A7180',
  faint: '#9AA1AD',
  hair: '#E6E2D8', // hairline borders
  hairSoft: '#F0EDE4',
} as const;

const NEUTRAL_BAND: PerfBand = { bg: '#EEF0F3', accent: '#CBD2DC', fg: '#5A6472' };

/** Solid traffic-light fill for a band (chart fills, chips, heatmap cells). */
export function bandFill(band: PerfBandName): string {
  switch (band) {
    case 'green':
      return PERF_GREEN;
    case 'yellow':
      return PERF_YELLOW;
    case 'pink':
      return PERF_PINK;
    default:
      return NEUTRAL_BAND.accent;
  }
}

/** Tonal {bg, accent, fg} for a band — soft tint + AA-safe text. */
export function bandTone(band: PerfBandName): PerfBand {
  switch (band) {
    case 'green':
      return PERF_BAND_HIGH;
    case 'yellow':
      return PERF_BAND_MID;
    case 'pink':
      return PERF_BAND_LOW;
    default:
      return NEUTRAL_BAND;
  }
}

/** Human label for a band (for aria / legends). */
export function bandLabel(band: PerfBandName): string {
  switch (band) {
    case 'green':
      return 'At or above target';
    case 'yellow':
      return 'Approaching target';
    case 'pink':
      return 'Needs attention';
    default:
      return 'No data';
  }
}

export const BAND_COLORS = {
  green: PERF_GREEN,
  yellow: PERF_YELLOW,
  pink: PERF_PINK,
} as const;

/** Format a 0–100 percentage for display; em-dash when null. */
export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${v.toFixed(digits)}%`;
}

/**
 * A standard's external link is shown only when it points at a real CPALMS
 * web page (…/PreviewStandard/Preview/{id}). Legacy `dim_standard` rows carried
 * the raw IMS/CASE JSON API URL (…/ims/case/…json) — a machine endpoint, not a
 * page — so we reject those (and any non-http value) and render plain text
 * instead. Returns the safe href, or null.
 */
export function standardHref(url: string | null | undefined): string | null {
  if (!url) return null;
  const u = url.trim();
  if (!/^https?:\/\//i.test(u)) return null;
  if (/\/ims\/case\//i.test(u) || /\.json(\?|#|$)/i.test(u)) return null;
  return u;
}
