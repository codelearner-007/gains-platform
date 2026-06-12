import {
  FileBarChart,
  Layers,
  Grid3x3,
  FileText,
  Users,
  UsersRound,
  ListChecks,
  LineChart,
  GraduationCap,
  Network,
  type LucideIcon,
} from 'lucide-react';

/**
 * Single source of truth for every GAINS report type.
 *
 * Every surface that names, links to, or switches between reports — the
 * AssessmentBrowser launch menu, the in-report ReportTypeSwitcher, page
 * headers, breadcrumbs, and the per-route browser <title> metadata — reads
 * from THIS registry so the names and routes can never drift apart.
 *
 * Canonical names are taken verbatim from the legacy PowerBI report pages
 * (`data/_pbix_extract/20_pages.md`); do not paraphrase them.
 */

export type ReportSlug =
  // Assessment family
  | 'question-response-analysis'
  | 'standards-deep-dive'
  | 'question-summary-paginated'
  | 'question-response-analysis-paginated'
  | 'question-response-analysis-by-teacher'
  | 'question-response-analysis-by-standard-and-teacher'
  | 'incorrect-answer-details'
  // Program family
  | 'year-to-date-performance'
  | 'standard-summary'
  | 'strand-summary';

export type ReportGroup = 'assessment' | 'program';

/**
 * How a report behaves, used to group entries inside the "More reports"
 * overflow menu:
 *   • interactive — on-screen, filterable PowerBI-style pages
 *   • paginated   — print/PDF-shaped SSRS-style pages
 *   • drilldown   — per-question drill-through (only reachable with a question)
 */
export type ReportKind = 'interactive' | 'paginated' | 'drilldown';

export interface ReportType {
  slug: ReportSlug;
  /** Full legacy name — used for headers, tab titles, breadcrumbs, menus. */
  canonicalName: string;
  /** Clear, non-cryptic label for tight inline tabs (e.g. "By Teacher"). */
  shortName: string;
  icon: LucideIcon;
  group: ReportGroup;
  kind: ReportKind;
  /**
   * Lower number = more prominent. The switcher shows the top-priority
   * siblings inline and tucks the rest behind a "More reports" menu.
   */
  priority: number;
}

/**
 * Ordered registry. Order here drives menu order; `priority` drives the
 * inline-vs-overflow split within the switcher.
 */
export const REPORT_TYPES: readonly ReportType[] = [
  // ── Assessment family ───────────────────────────────────────────────
  {
    slug: 'question-response-analysis',
    canonicalName: 'Question Response Analysis Interactive',
    shortName: 'Question Response',
    icon: FileBarChart,
    group: 'assessment',
    kind: 'interactive',
    priority: 1,
  },
  {
    slug: 'standards-deep-dive',
    canonicalName: 'Standards Deep Dive interactive',
    shortName: 'Standards Deep Dive',
    icon: Layers,
    group: 'assessment',
    kind: 'interactive',
    priority: 2,
  },
  {
    slug: 'question-summary-paginated',
    canonicalName: 'Question Summary Report',
    shortName: 'Question Summary',
    icon: Grid3x3,
    group: 'assessment',
    kind: 'paginated',
    priority: 3,
  },
  {
    slug: 'question-response-analysis-paginated',
    canonicalName: 'Question Response Analysis',
    shortName: 'QRA (Print)',
    icon: FileText,
    group: 'assessment',
    kind: 'paginated',
    priority: 4,
  },
  {
    slug: 'question-response-analysis-by-teacher',
    canonicalName: 'Question Response Analysis - By Teacher',
    shortName: 'By Teacher',
    icon: Users,
    group: 'assessment',
    kind: 'paginated',
    priority: 5,
  },
  {
    slug: 'question-response-analysis-by-standard-and-teacher',
    canonicalName: 'Question Response Analysis - By Standard and Teacher',
    shortName: 'By Standard and Teacher',
    icon: UsersRound,
    group: 'assessment',
    kind: 'paginated',
    priority: 6,
  },
  {
    slug: 'incorrect-answer-details',
    canonicalName: 'Incorrect Answer Details',
    shortName: 'Incorrect Answers',
    icon: ListChecks,
    group: 'assessment',
    kind: 'drilldown',
    priority: 7,
  },

  // ── Program family ──────────────────────────────────────────────────
  {
    slug: 'year-to-date-performance',
    canonicalName: 'Year To Date - Longitudinal Report',
    shortName: 'Year To Date',
    icon: LineChart,
    group: 'program',
    kind: 'interactive',
    priority: 1,
  },
  {
    slug: 'standard-summary',
    canonicalName: 'Standard Summary',
    shortName: 'Standard Summary',
    icon: GraduationCap,
    group: 'program',
    kind: 'paginated',
    priority: 2,
  },
  {
    slug: 'strand-summary',
    canonicalName: 'Strand Summary',
    shortName: 'Strand Summary',
    icon: Network,
    group: 'program',
    kind: 'paginated',
    priority: 3,
  },
] as const;

const BY_SLUG: Record<ReportSlug, ReportType> = Object.fromEntries(
  REPORT_TYPES.map((r) => [r.slug, r]),
) as Record<ReportSlug, ReportType>;

/** All reports in a family, in registry order. */
export function getReportsByGroup(group: ReportGroup): ReportType[] {
  return REPORT_TYPES.filter((r) => r.group === group);
}

/** Look up one report by its route slug. */
export function getReportBySlug(slug: ReportSlug): ReportType {
  return BY_SLUG[slug];
}

/** True when the pathname ends in this report's slug segment. */
export function isReportActive(pathname: string, slug: ReportSlug): boolean {
  return pathname.endsWith(`/${slug}`);
}

/** Resolve which report (if any) a pathname currently points at. */
export function getReportByPathname(pathname: string): ReportType | undefined {
  return REPORT_TYPES.find((r) => isReportActive(pathname, r.slug));
}

export interface ReportHrefContext {
  /** Assessment id — required for every assessment report link. */
  item_id?: string;
  /** Question id — only honoured by the IAD drill-through. */
  question_id?: string | null;
}

type ReportHref =
  | string
  | { pathname: string; query: Record<string, string> };

/**
 * Build a typed Next.js href for a report, carrying the assessment context.
 *
 *   • Program reports never need context → plain path.
 *   • Assessment reports carry `item_id`.
 *   • The IAD drill-through additionally carries `question_id` when present.
 */
export function buildHref(slug: ReportSlug, ctx: ReportHrefContext = {}): ReportHref {
  const report = BY_SLUG[slug];
  const pathname = `/app/reports/${slug}`;
  if (report.group === 'program') return pathname;

  const query: Record<string, string> = {};
  if (ctx.item_id) query.item_id = ctx.item_id;
  if (slug === 'incorrect-answer-details' && ctx.question_id) {
    query.question_id = ctx.question_id;
  }
  return { pathname, query };
}
