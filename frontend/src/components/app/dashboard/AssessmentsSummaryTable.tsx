'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, Loader2 } from 'lucide-react';
import type {
  AssessmentSummaryListRow,
  DashboardStrandRow,
  StandardSummaryRollupRow,
} from '@/lib/reports/types';
import { getReportsByGroup, buildHref } from '@/lib/reports/report-types';
import {
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  PBIX_ACCENT_LIGHT_BLUE,
} from '@/lib/reports/colors';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  SortableHeader,
  useTableSort,
  type SortAccessor,
  type SortDirection,
} from '@/lib/reports/useTableSort';
import GradeAverageBar from '@/components/app/modules/reports/shared/GradeAverageBar';

/**
 * Assessments Summary — the centerpiece of the legacy Assessment Analysis
 * Dashboard. A single grid whose grouping/columns switch via a View toggle:
 *
 *   • By Assessment — SERVER-PAGINATED: one page per request, server sort +
 *     server name-search, more pages fetched on scroll (the assessments set is
 *     unbounded). Owned by DashboardPage; this component just renders it.
 *   • By Standard / By Strand — client-side over the bounded standard-/strand-
 *     summary rollups (fully fetched): client search, sort and window-on-scroll.
 */

export type SummaryView = 'assessment' | 'standard' | 'strand';

/** Server sort keys for the By-Assessment grid (match the backend whitelist). */
export type AssessmentSortKey = 'grade' | 'date' | 'item' | 'students' | 'average';

/** Server sort keys for the By-Strand grid (match the backend whitelist). */
export type StrandRowSortKey =
  | 'grade'
  | 'strand'
  | 'standards'
  | 'questions'
  | 'average'
  | 'date';

const VIEWS: { value: SummaryView; label: string }[] = [
  { value: 'assessment', label: 'By Assessment' },
  { value: 'standard', label: 'By Standard' },
  { value: 'strand', label: 'By Strand' },
];

const PAGE_SIZE = 25; // client window step for the bounded std/strand variants

// Launch menu = the assessment report family, minus the drill-through (IAD),
// straight from the report registry (the single source of truth for routing).
const ROW_ACTIONS = getReportsByGroup('assessment').filter(
  (r) => r.kind !== 'drilldown',
);

const matches = (haystack: string | null | undefined, q: string) =>
  (haystack ?? '').toLowerCase().includes(q);

interface Props {
  /** School-wide grade average (0..1) for the data-bar reference marker. */
  schoolAverage: number | null;

  // ── By Assessment (server-paginated, owned by DashboardPage) ──
  assessments: AssessmentSummaryListRow[]; // accumulated page rows, server order
  assessmentTotal: number;
  assessmentHasMore: boolean;
  assessmentFetchingMore: boolean;
  onAssessmentFetchMore: () => void;
  assessmentSort: AssessmentSortKey;
  assessmentDir: SortDirection;
  onAssessmentSort: (col: AssessmentSortKey) => void;
  assessmentLoading: boolean;

  // ── By Strand (server-paginated — legacy per-assessment × strand grain) ──
  strandRows: DashboardStrandRow[];
  strandTotal: number;
  strandHasMore: boolean;
  strandFetchingMore: boolean;
  onStrandFetchMore: () => void;
  strandSort: StrandRowSortKey;
  strandDir: SortDirection;
  onStrandSort: (col: StrandRowSortKey) => void;
  strandLoading: boolean;

  // ── By Standard (client-side, bounded) ──
  standards: StandardSummaryRollupRow[];
  /** Client filter for the By-Standard rollup (assessment + strand use server q). */
  search: string;
  loading: boolean; // By-Standard initial load
}

export default function AssessmentsSummaryTable({
  schoolAverage,
  assessments,
  assessmentTotal,
  assessmentHasMore,
  assessmentFetchingMore,
  onAssessmentFetchMore,
  assessmentSort,
  assessmentDir,
  onAssessmentSort,
  assessmentLoading,
  strandRows,
  strandTotal,
  strandHasMore,
  strandFetchingMore,
  onStrandFetchMore,
  strandSort,
  strandDir,
  onStrandSort,
  strandLoading,
  standards,
  search,
  loading,
}: Props) {
  const [view, setView] = useState<SummaryView>('assessment');
  const variantLoading =
    view === 'assessment'
      ? assessmentLoading
      : view === 'strand'
        ? strandLoading
        : loading;

  return (
    <div
      className="overflow-hidden rounded-lg border bg-card"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2.5"
        style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      >
        <h2 className="text-sm font-bold text-foreground">Assessments Summary</h2>
        <div
          role="tablist"
          aria-label="Assessments Summary view"
          className="inline-flex items-center gap-1 rounded-md bg-background/60 p-0.5"
        >
          {VIEWS.map((v) => {
            const active = view === v.value;
            return (
              <button
                key={v.value}
                role="tab"
                aria-selected={active}
                onClick={() => setView(v.value)}
                className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'text-foreground/70 hover:bg-background'
                }`}
              >
                {v.label}
              </button>
            );
          })}
        </div>
      </div>

      {variantLoading ? (
        <div className="space-y-2 p-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : view === 'assessment' ? (
        <ByAssessment
          rows={assessments}
          total={assessmentTotal}
          hasMore={assessmentHasMore}
          isFetchingMore={assessmentFetchingMore}
          onFetchMore={onAssessmentFetchMore}
          sort={assessmentSort}
          dir={assessmentDir}
          onSort={onAssessmentSort}
          schoolAverage={schoolAverage}
        />
      ) : view === 'standard' ? (
        <ByStandard rows={standards} search={search} schoolAverage={schoolAverage} />
      ) : (
        <ByStrandRows
          rows={strandRows}
          total={strandTotal}
          hasMore={strandHasMore}
          isFetchingMore={strandFetchingMore}
          onFetchMore={onStrandFetchMore}
          sort={strandSort}
          dir={strandDir}
          onSort={onStrandSort}
          schoolAverage={schoolAverage}
        />
      )}
    </div>
  );
}

// ── Shared chrome ────────────────────────────────────────────────────────
function Th({
  children,
  align = 'left',
}: {
  children: React.ReactNode;
  align?: 'left' | 'center' | 'right';
}) {
  return (
    <th
      className="border-b px-3 py-2 text-xs font-semibold text-foreground"
      style={{ backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER, textAlign: align }}
    >
      {children}
    </th>
  );
}

const TD = 'border-b px-3 py-1.5 text-sm';
const STICKY_THEAD = 'sticky top-0 z-10';

function ScrollRegion({
  scrollRef,
  children,
}: {
  scrollRef: React.RefObject<HTMLDivElement | null>;
  children: React.ReactNode;
}) {
  return (
    <div ref={scrollRef} className="max-h-[26rem] overflow-auto">
      {children}
    </div>
  );
}

/** Sentinel row shown at the foot of the scroll region while more can load. */
function LoadMore({
  sentinelRef,
  hasMore,
  spinning = true,
}: {
  sentinelRef: React.RefObject<HTMLDivElement | null>;
  hasMore: boolean;
  spinning?: boolean;
}) {
  if (!hasMore) return null;
  return (
    <div
      ref={sentinelRef}
      className="flex items-center justify-center gap-2 py-3 text-xs text-muted-foreground"
    >
      {spinning && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {spinning ? 'Loading more…' : ' '}
    </div>
  );
}

function ShownFooter({ shown, total }: { shown: number; total: number }) {
  if (total === 0) return null;
  return (
    <div
      className="border-t px-4 py-2 text-right text-[11px] tabular-nums text-muted-foreground"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      Showing {shown} of {total}
    </div>
  );
}

function EmptyRow({ cols, label }: { cols: number; label: string }) {
  return (
    <tr>
      <td colSpan={cols} className="px-3 py-10 text-center text-sm text-muted-foreground">
        {label}
      </td>
    </tr>
  );
}

/**
 * Client-side window for the BOUNDED std/strand rollups: reveal PAGE_SIZE more
 * rows when the sentinel scrolls in. Resets when the (filtered+sorted) rows
 * change. Never hits the network.
 */
function useInfiniteWindow<T>(rows: T[]) {
  const [count, setCount] = useState(PAGE_SIZE);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setCount(PAGE_SIZE);
    scrollRef.current?.scrollTo({ top: 0 });
  }, [rows]);

  const hasMore = count < rows.length;

  useEffect(() => {
    if (!hasMore) return;
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setCount((c) => Math.min(c + PAGE_SIZE, rows.length));
        }
      },
      { root: scrollRef.current ?? null, rootMargin: '160px' },
    );
    io.observe(sentinel);
    return () => io.disconnect();
  }, [hasMore, rows.length]);

  return {
    visibleRows: rows.slice(0, count),
    scrollRef,
    sentinelRef,
    hasMore,
    shown: Math.min(count, rows.length),
    total: rows.length,
  };
}

/**
 * Fetch-more-on-scroll for the SERVER-paginated assessment grid: when the
 * sentinel enters the scroll container, ask the parent to fetch the next page
 * (guarded so it never fires while a fetch is already in flight).
 */
function useFetchMoreSentinel(
  hasMore: boolean,
  isFetching: boolean,
  onFetchMore: () => void,
) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const cb = useRef(onFetchMore);
  cb.current = onFetchMore;

  useEffect(() => {
    if (!hasMore || isFetching) return;
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) cb.current();
      },
      { root: scrollRef.current ?? null, rootMargin: '160px' },
    );
    io.observe(sentinel);
    return () => io.disconnect();
  }, [hasMore, isFetching]);

  return { scrollRef, sentinelRef };
}

// ── Variant A: By Assessment (server-paginated) ──────────────────────────
function ByAssessment({
  rows,
  total,
  hasMore,
  isFetchingMore,
  onFetchMore,
  sort,
  dir,
  onSort,
  schoolAverage,
}: {
  rows: AssessmentSummaryListRow[];
  total: number;
  hasMore: boolean;
  isFetchingMore: boolean;
  onFetchMore: () => void;
  sort: AssessmentSortKey;
  dir: SortDirection;
  onSort: (col: AssessmentSortKey) => void;
  schoolAverage: number | null;
}) {
  const { scrollRef, sentinelRef } = useFetchMoreSentinel(
    hasMore,
    isFetchingMore,
    onFetchMore,
  );

  return (
    <>
      <ScrollRegion scrollRef={scrollRef}>
        <table className="w-full border-collapse">
          <thead className={STICKY_THEAD}>
            <tr>
              <Th><SortableHeader column="grade" label="Grade" sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
              <Th><SortableHeader column="date" label="Assessment Date" sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
              <Th><SortableHeader column="item" label="Assessment" sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
              <Th align="center"><SortableHeader column="students" label="Student Count" sortColumn={sort} sortDirection={dir} onClick={onSort} align="center" /></Th>
              <Th><SortableHeader column="average" label="Grade Average" sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
              <Th align="right">Report</Th>
            </tr>
          </thead>
          <tbody>
            {total === 0 ? (
              <EmptyRow cols={6} label="No assessments match the current filters." />
            ) : (
              rows.map((r) => (
                <tr key={r.item_id} className="transition-colors hover:bg-accent/30">
                  <td className={TD} style={{ borderColor: LAYOUT_BORDER }}>{r.grade ?? '—'}</td>
                  <td className={`${TD} tabular-nums whitespace-nowrap`} style={{ borderColor: LAYOUT_BORDER }}>{r.assessment_date ?? '—'}</td>
                  <td className={`${TD} font-medium text-foreground`} style={{ borderColor: LAYOUT_BORDER }}>{r.item_name ?? r.item_id}</td>
                  <td className={`${TD} text-center tabular-nums`} style={{ borderColor: LAYOUT_BORDER }}>{r.total_students ?? '—'}</td>
                  <td className={`${TD} min-w-[200px]`} style={{ borderColor: LAYOUT_BORDER }}>
                    <GradeAverageBar value={r.grade_average} marker={schoolAverage} />
                  </td>
                  <td className={`${TD} text-right`} style={{ borderColor: LAYOUT_BORDER }}>
                    <OpenReportMenu itemId={r.item_id} itemName={r.item_name ?? r.item_id} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <LoadMore sentinelRef={sentinelRef} hasMore={hasMore} spinning={isFetchingMore} />
      </ScrollRegion>
      <ShownFooter shown={rows.length} total={total} />
    </>
  );
}

function OpenReportMenu({ itemId, itemName }: { itemId: string; itemName: string }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 gap-1.5">
          Open report
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[22rem] max-w-[calc(100vw-2rem)]">
        <DropdownMenuLabel className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Report type
        </DropdownMenuLabel>
        {ROW_ACTIONS.map((report) => {
          const Icon = report.icon;
          return (
            <DropdownMenuItem key={report.slug} asChild>
              <Link
                href={buildHref(report.slug, { item_id: itemId })}
                aria-label={`Open ${report.canonicalName} for ${itemName}`}
                className="flex cursor-pointer items-start gap-2.5 py-2"
              >
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-sm font-medium leading-snug text-foreground">{report.canonicalName}</span>
                  <span className="text-[11px] leading-tight text-muted-foreground">{report.menuHint}</span>
                </span>
              </Link>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ── Variant B: By Standard (client-side, bounded) ────────────────────────
type SKey = 'standard' | 'strand' | 'subject' | 'questions' | 'assessments' | 'average';

const S_ACCESSORS: Record<SKey, SortAccessor<StandardSummaryRollupRow>> = {
  standard: (r) => (r.cpalms_standard || r.schoology_standard || '').toLowerCase(),
  strand: (r) => (r.strand ?? '').toLowerCase(),
  subject: (r) => (r.subject ?? '').toLowerCase(),
  questions: (r) => r.num_questions,
  assessments: (r) => r.num_assessments,
  average: (r) => r.grade_average,
};

function ByStandard({
  rows,
  search,
  schoolAverage,
}: {
  rows: StandardSummaryRollupRow[];
  search: string;
  schoolAverage: number | null;
}) {
  const q = search.trim().toLowerCase();
  const filtered = useMemo(
    () =>
      q
        ? rows.filter(
            (r) =>
              matches(r.cpalms_standard, q) ||
              matches(r.schoology_standard, q) ||
              matches(r.strand, q),
          )
        : rows,
    [rows, q],
  );
  const { sortedRows, sortColumn, sortDirection, onHeaderClick } = useTableSort<
    StandardSummaryRollupRow,
    SKey
  >({
    rows: filtered,
    accessors: S_ACCESSORS,
    defaultColumn: 'standard',
    defaultDirection: 'asc',
    initialDirections: { questions: 'desc', assessments: 'desc', average: 'desc' },
  });
  const { visibleRows, scrollRef, sentinelRef, hasMore, shown, total } =
    useInfiniteWindow(sortedRows);

  return (
    <>
      <ScrollRegion scrollRef={scrollRef}>
        <table className="w-full border-collapse">
          <thead className={STICKY_THEAD}>
            <tr>
              <Th><SortableHeader column="standard" label="Standard" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
              <Th><SortableHeader column="strand" label="Strand" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
              <Th><SortableHeader column="subject" label="Subject" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
              <Th align="center"><SortableHeader column="questions" label="# Questions" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" /></Th>
              <Th align="center"><SortableHeader column="assessments" label="# Assessments" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" /></Th>
              <Th><SortableHeader column="average" label="Grade Average" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
            </tr>
          </thead>
          <tbody>
            {total === 0 ? (
              <EmptyRow cols={6} label="No standards match the current filters." />
            ) : (
              visibleRows.map((r, i) => (
                <tr key={`${r.schoology_standard}-${r.subject}-${i}`} className="transition-colors hover:bg-accent/30">
                  <td className={`${TD} font-medium text-foreground`} style={{ borderColor: LAYOUT_BORDER }} title={r.description || undefined}>{r.cpalms_standard || r.schoology_standard}</td>
                  <td className={TD} style={{ borderColor: LAYOUT_BORDER }}>{r.strand || '—'}</td>
                  <td className={TD} style={{ borderColor: LAYOUT_BORDER }}>{r.subject || '—'}</td>
                  <td className={`${TD} text-center tabular-nums`} style={{ borderColor: LAYOUT_BORDER }}>{r.num_questions}</td>
                  <td className={`${TD} text-center tabular-nums`} style={{ borderColor: LAYOUT_BORDER }}>{r.num_assessments}</td>
                  <td className={`${TD} min-w-[200px]`} style={{ borderColor: LAYOUT_BORDER }}>
                    <GradeAverageBar value={r.grade_average} marker={schoolAverage} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <LoadMore sentinelRef={sentinelRef} hasMore={hasMore} />
      </ScrollRegion>
      <ShownFooter shown={shown} total={total} />
    </>
  );
}

// ── Variant C: By Strand (server-paginated, legacy per-assessment × strand) ──
function ByStrandRows({
  rows,
  total,
  hasMore,
  isFetchingMore,
  onFetchMore,
  sort,
  dir,
  onSort,
  schoolAverage,
}: {
  rows: DashboardStrandRow[];
  total: number;
  hasMore: boolean;
  isFetchingMore: boolean;
  onFetchMore: () => void;
  sort: StrandRowSortKey;
  dir: SortDirection;
  onSort: (col: StrandRowSortKey) => void;
  schoolAverage: number | null;
}) {
  const { scrollRef, sentinelRef } = useFetchMoreSentinel(
    hasMore,
    isFetchingMore,
    onFetchMore,
  );

  return (
    <>
      <ScrollRegion scrollRef={scrollRef}>
        <table className="w-full border-collapse">
          <thead className={STICKY_THEAD}>
            <tr>
              <Th><SortableHeader column="grade" label="Grade" sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
              <Th><SortableHeader column="strand" label="Strand" sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
              <Th align="center"><SortableHeader column="standards" label="Total Standards" sortColumn={sort} sortDirection={dir} onClick={onSort} align="center" /></Th>
              <Th align="center"><SortableHeader column="questions" label="Total Questions" sortColumn={sort} sortDirection={dir} onClick={onSort} align="center" /></Th>
              <Th><SortableHeader column="average" label="Grade Average" sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
              <Th><SortableHeader column="date" label="Assessment Date" sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
              <Th>Assessment</Th>
            </tr>
          </thead>
          <tbody>
            {total === 0 ? (
              <EmptyRow cols={7} label="No strands match the current filters." />
            ) : (
              rows.map((r, i) => (
                <tr
                  key={`${r.item_id}-${r.strand}-${i}`}
                  className="transition-colors hover:bg-accent/30"
                >
                  <td className={TD} style={{ borderColor: LAYOUT_BORDER }}>{r.grade ?? '—'}</td>
                  <td className={`${TD} font-medium text-foreground`} style={{ borderColor: LAYOUT_BORDER }}>{r.strand}</td>
                  <td className={`${TD} text-center tabular-nums`} style={{ borderColor: LAYOUT_BORDER }}>{r.total_standards}</td>
                  <td className={`${TD} text-center tabular-nums`} style={{ borderColor: LAYOUT_BORDER }}>{r.total_questions}</td>
                  <td className={`${TD} min-w-[200px]`} style={{ borderColor: LAYOUT_BORDER }}>
                    <GradeAverageBar value={r.grade_average} marker={schoolAverage} />
                  </td>
                  <td className={`${TD} tabular-nums whitespace-nowrap`} style={{ borderColor: LAYOUT_BORDER }}>{r.assessment_date ?? '—'}</td>
                  <td className={`${TD} text-foreground`} style={{ borderColor: LAYOUT_BORDER }}>{r.assessment ?? '—'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <LoadMore sentinelRef={sentinelRef} hasMore={hasMore} spinning={isFetchingMore} />
      </ScrollRegion>
      <ShownFooter shown={rows.length} total={total} />
    </>
  );
}
