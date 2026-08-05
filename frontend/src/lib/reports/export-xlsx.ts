// Client helper for the server-side XLSX export (Phase B / B2+B3).
//
// The workbook is built on the backend (openpyxl) so this module only:
//   1. composes the same-origin `export.xlsx` route URL for a report kind, and
//   2. fetches it with credentials and triggers a browser download.
//
// The route reuses the SAME `ReportService.build_*` + `reports:read` + RLS
// scoping as the JSON endpoint, so the workbook can never diverge from screen.

import type { ReportKind } from './export-csv';
import type {
  AssessmentFilters,
  ForwardViewFilters,
  StandardSummaryFilters,
  StrandSummaryFilters,
} from './types';

/**
 * Summary / YTD filter shape. The concrete report-filter interfaces lack an
 * index signature so they aren't structurally a `Record`; we union them in
 * explicitly. A plain string map is also accepted for ad-hoc callers.
 */
export type XlsxFilters =
  | AssessmentFilters
  | StandardSummaryFilters
  | StrandSummaryFilters
  | ForwardViewFilters
  | Record<string, string | null | undefined>;

/** Identifiers + scope needed to address a report's `export.xlsx` route. */
export interface XlsxUrlOptions {
  itemId?: string;
  questionId?: string;
  schoolId?: string;
  /** Summary / YTD filter query params (session/category/subject/grade/…). */
  filters?: XlsxFilters;
}

const REPORT_PATH: Record<ReportKind, string> = {
  qra: 'question-response-analysis',
  'qra-paginated': 'question-response-analysis-paginated',
  'qra-by-teacher': 'question-response-analysis-by-teacher',
  'qra-by-standard-teacher': 'question-response-analysis-by-standard-and-teacher',
  qsr: 'question-summary-paginated',
  ytd: 'year-to-date-performance',
  'standard-summary': 'standard-summary',
  'strand-summary': 'strand-summary',
  'forward-view': 'forward-view',
  sdd: 'standards-deep-dive',
  iad: 'incorrect-answer-details',
};

/** Report kinds addressed by `{item_id}` in the path. */
const ITEM_SCOPED = new Set<ReportKind>([
  'qra',
  'qra-paginated',
  'qra-by-teacher',
  'qra-by-standard-teacher',
  'qsr',
  'sdd',
  'iad',
]);

function queryString(params: XlsxFilters): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== '',
  ) as [string, string][];
  if (entries.length === 0) return '';
  const sp = new URLSearchParams(entries);
  return `?${sp.toString()}`;
}

/**
 * Build the same-origin `export.xlsx` route for a report kind, or `null` when
 * a required identifier (e.g. an item-scoped report's `itemId`) is missing.
 */
export function buildXlsxUrl(
  kind: ReportKind,
  opts: XlsxUrlOptions = {},
): string | null {
  const path = REPORT_PATH[kind];
  const base = '/api/v1/reports';

  if (kind === 'iad') {
    if (!opts.itemId || !opts.questionId) return null;
    return (
      `${base}/${path}/${encodeURIComponent(opts.itemId)}/` +
      `${encodeURIComponent(opts.questionId)}/export.xlsx` +
      queryString({ school_id: opts.schoolId })
    );
  }

  if (ITEM_SCOPED.has(kind)) {
    if (!opts.itemId) return null;
    return (
      `${base}/${path}/${encodeURIComponent(opts.itemId)}/export.xlsx` +
      queryString({ school_id: opts.schoolId })
    );
  }

  // Filter-scoped reports (standard-summary, strand-summary, ytd).
  return (
    `${base}/${path}/export.xlsx` +
    queryString({ school_id: opts.schoolId, ...(opts.filters ?? {}) })
  );
}

/** Parse the server `filename="..."` out of a Content-Disposition header. */
function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const match = /filename\*?=(?:UTF-8'')?"?([^"\r\n;]+)"?/i.exec(header);
  return match ? decodeURIComponent(match[1]).trim() : null;
}

/**
 * Fetch the report's `export.xlsx` (same-origin, credentials included) and
 * trigger a browser download. Honors the server's attachment filename, falling
 * back to `fallbackName`. Throws on a non-OK response so the caller can toast.
 */
export async function downloadXlsx(
  url: string,
  fallbackName: string,
): Promise<void> {
  const res = await fetch(url, { credentials: 'include' });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(
      `Export failed (${res.status})${body ? `: ${body.slice(0, 200)}` : ''}`,
    );
  }
  const blob = await res.blob();
  if (typeof document === 'undefined' || typeof URL === 'undefined') return;
  const name =
    filenameFromDisposition(res.headers.get('content-disposition')) ||
    fallbackName;
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = name;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}
