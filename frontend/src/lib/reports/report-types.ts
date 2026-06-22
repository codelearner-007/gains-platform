import type { Metadata } from 'next';
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
 * dashboard launch menu, the in-report ReportTypeSwitcher, page headers,
 * breadcrumbs, and the per-route browser <title> metadata — reads from THIS
 * registry so the names and routes can never drift apart.
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
 * How a report behaves — on-screen interactive vs print/PDF-shaped vs
 * per-question drill-through:
 *   • interactive — on-screen, filterable PowerBI-style pages
 *   • paginated   — print/PDF-shaped SSRS-style pages
 *   • drilldown   — per-question drill-through (only reachable with a question)
 */
export type ReportKind = 'interactive' | 'paginated' | 'drilldown';

/**
 * Assessment "family" — the top-level report-type tab. Multiple report routes
 * can belong to one family and are reached via a contextual sub-tab row:
 *   • qra — Question Response Analysis (Interactive + 3 printable renderings)
 *   • sdd — Standards Deep Dive (single interactive page)
 *   • qsr — Question Summary (one route, ?variant sub-tabs)
 * Reports with no family (the IAD drill-through) are not shown as a top tab.
 */
export type ReportFamily = 'qra' | 'sdd' | 'qsr';

export interface ReportType {
  slug: ReportSlug;
  /** Full legacy name — used for headers, tab titles, breadcrumbs, menus. */
  canonicalName: string;
  /** Clear, non-cryptic label for tight inline tabs (e.g. "By Teacher"). */
  shortName: string;
  /** One-line descriptor shown under the name in the "Open report" menu so
   *  the similarly-named QRA variants are easy to tell apart. */
  menuHint: string;
  icon: LucideIcon;
  group: ReportGroup;
  kind: ReportKind;
  /** Assessment family this report belongs to (drives the family tab + sub-tabs).
   *  Omitted for the IAD drill-through, which has no top-nav tab. */
  family?: ReportFamily;
  /** Label for this rendering in the family sub-tab row (e.g. "Base"). Reads
   *  inside the family context, so it names the rendering, not the report;
   *  falls back to `shortName`. Only set for families with a sub-tab row (QRA). */
  subTabLabel?: string;
  /**
   * Lower number = more prominent. Retained for the program-group inline order.
   */
  priority: number;
}

/**
 * Ordered registry. Order here drives menu/sub-tab order; `priority` now only
 * orders the program-group inline tabs (the old inline-vs-overflow split was
 * removed when the "More reports" menu gave way to family tabs + sub-tabs).
 */
export const REPORT_TYPES: readonly ReportType[] = [
  // ── Assessment family ───────────────────────────────────────────────
  {
    slug: 'question-response-analysis',
    canonicalName: 'Question Response Analysis Interactive',
    shortName: 'Question Response',
    menuHint: 'Interactive — slicers, sort & cross-filter',
    icon: FileBarChart,
    group: 'assessment',
    kind: 'interactive',
    family: 'qra',
    subTabLabel: 'Interactive',
    priority: 1,
  },
  {
    slug: 'standards-deep-dive',
    canonicalName: 'Standards Deep Dive interactive',
    shortName: 'Standards Deep Dive',
    menuHint: 'Interactive standards deep-dive',
    icon: Layers,
    group: 'assessment',
    kind: 'interactive',
    family: 'sdd',
    priority: 2,
  },
  {
    slug: 'question-summary-paginated',
    canonicalName: 'Question Summary Report',
    shortName: 'Question Summary',
    menuHint: 'Per-student score matrix',
    icon: Grid3x3,
    group: 'assessment',
    kind: 'paginated',
    family: 'qsr',
    priority: 3,
  },
  {
    slug: 'question-response-analysis-paginated',
    canonicalName: 'Question Response Analysis',
    shortName: 'QRA (Print)',
    menuHint: 'Printable per-question report',
    icon: FileText,
    group: 'assessment',
    kind: 'paginated',
    family: 'qra',
    subTabLabel: 'Base',
    priority: 4,
  },
  {
    slug: 'question-response-analysis-by-teacher',
    canonicalName: 'Question Response Analysis - By Teacher',
    shortName: 'By Teacher',
    menuHint: 'Per-question results grouped by teacher',
    icon: Users,
    group: 'assessment',
    kind: 'paginated',
    family: 'qra',
    subTabLabel: 'By Teacher',
    priority: 5,
  },
  {
    slug: 'question-response-analysis-by-standard-and-teacher',
    canonicalName: 'Question Response Analysis - By Standard and Teacher',
    shortName: 'By Standard and Teacher',
    menuHint: 'Grouped by standard, then teacher',
    icon: UsersRound,
    group: 'assessment',
    kind: 'paginated',
    family: 'qra',
    subTabLabel: 'By Standard + Teacher',
    priority: 6,
  },
  {
    slug: 'incorrect-answer-details',
    canonicalName: 'Incorrect Answer Details',
    shortName: 'Incorrect Answers',
    menuHint: 'Per-question wrong-answer drill-down',
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
    menuHint: 'Longitudinal trend across the session',
    icon: LineChart,
    group: 'program',
    kind: 'interactive',
    priority: 1,
  },
  {
    slug: 'standard-summary',
    canonicalName: 'Standard Summary',
    shortName: 'Standard Summary',
    menuHint: 'School-wide standards rollup',
    icon: GraduationCap,
    group: 'program',
    kind: 'paginated',
    priority: 2,
  },
  {
    slug: 'strand-summary',
    canonicalName: 'Strand Summary',
    shortName: 'Strand Summary',
    menuHint: 'Strand rollup with treemap',
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

/**
 * Static `metadata` factory for per-report `layout.tsx` files.
 *
 * Next requires `metadata` to be a statically-resolvable export per route
 * segment, so each report layout calls this with its own slug. Title still
 * flows from the `canonicalName` registry above.
 */
export function makeReportMetadata(slug: ReportSlug): Metadata {
  return { title: getReportBySlug(slug).canonicalName };
}

/** True when the pathname ends in this report's slug segment. */
export function isReportActive(pathname: string, slug: ReportSlug): boolean {
  return pathname.endsWith(`/${slug}`);
}

/** Resolve which report (if any) a pathname currently points at. */
export function getReportByPathname(pathname: string): ReportType | undefined {
  return REPORT_TYPES.find((r) => isReportActive(pathname, r.slug));
}

// ── Assessment families (two-level tab navigation) ──────────────────────────

export interface AssessmentFamilyTab {
  family: ReportFamily;
  /** Tight tab label (e.g. "Question Response"). */
  label: string;
  /** Full canonical name for aria-label / title. */
  fullName: string;
  icon: LucideIcon;
  /** The route the family tab links to (its landing report). */
  defaultSlug: ReportSlug;
}

const FAMILY_ORDER: ReportFamily[] = ['qra', 'sdd', 'qsr'];

/** The assessment family tabs (Question Response / Standards Deep Dive /
 *  Question Summary), in display order, each pointing at its landing report. */
export function getAssessmentFamilyTabs(): AssessmentFamilyTab[] {
  return FAMILY_ORDER.map((fam) => {
    // The family's landing report is the first one listed for that family.
    const def = REPORT_TYPES.find((r) => r.family === fam)!;
    return {
      family: fam,
      label: def.shortName,
      fullName: def.canonicalName,
      icon: def.icon,
      defaultSlug: def.slug,
    };
  });
}

/** All reports in a family, in registry order. */
export function getReportsByFamily(family: ReportFamily): ReportType[] {
  return REPORT_TYPES.filter((r) => r.family === family);
}

/** The family owning the active route (undefined for the IAD drill-through or
 *  any program report — those show no active assessment family tab). */
export function getFamilyByPathname(pathname: string): ReportFamily | undefined {
  return getReportByPathname(pathname)?.family;
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
