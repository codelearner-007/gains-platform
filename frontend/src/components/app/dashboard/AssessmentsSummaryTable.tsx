'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, Loader2 } from 'lucide-react';
import type {
  AssessmentSummaryListRow,
  StandardSummaryRollupRow,
  StrandSummaryRollupRow,
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
} from '@/lib/reports/useTableSort';
import GradeAverageBar from '@/components/app/modules/reports/shared/GradeAverageBar';

/**
 * Assessments Summary — the centerpiece of the legacy Assessment Analysis
 * Dashboard. A single grid whose grouping/columns switch via a View toggle
 * (By Assessment / By Standard / By Strand). The body scrolls inside a capped
 * region so the program reports below stay reachable; rows reveal in pages of
 * PAGE_SIZE as the sentinel scrolls into view — purely client-side over the
 * already-fetched rows, so scrolling issues NO extra API calls.
 */

export type SummaryView = 'assessment' | 'standard' | 'strand';

const VIEWS: { value: SummaryView; label: string }[] = [
  { value: 'assessment', label: 'By Assessment' },
  { value: 'standard', label: 'By Standard' },
  { value: 'strand', label: 'By Strand' },
];

const PAGE_SIZE = 25;

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
  assessments: AssessmentSummaryListRow[];
  standards: StandardSummaryRollupRow[];
  strands: StrandSummaryRollupRow[];
  /** Free-text search; filters the active variant's primary text column. */
  search: string;
  loading: boolean;
}

export default function AssessmentsSummaryTable({
  schoolAverage,
  assessments,
  standards,
  strands,
  search,
  loading,
}: Props) {
  const [view, setView] = useState<SummaryView>('assessment');

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
          className="inline-flex items-center gap-1 rounded-md bg-white/60 p-0.5"
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
                    : 'text-foreground/70 hover:bg-white'
                }`}
              >
                {v.label}
              </button>
            );
          })}
        </div>
      </div>

      {loading ? (
        <div className="space-y-2 p-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : view === 'assessment' ? (
        <ByAssessment rows={assessments} search={search} schoolAverage={schoolAverage} />
      ) : view === 'standard' ? (
        <ByStandard rows={standards} search={search} schoolAverage={schoolAverage} />
      ) : (
        <ByStrand rows={strands} search={search} schoolAverage={schoolAverage} />
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

/**
 * Capped scroll region + page-on-scroll windowing over an in-memory array.
 * Resets to the first page whenever the (filtered+sorted) rows change. The
 * IntersectionObserver is rooted to the scroll container, so it only fires
 * while the user scrolls this table — never on unrelated re-renders, and never
 * triggers a network request (the rows are already loaded).
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

function LoadMore({
  sentinelRef,
  hasMore,
}: {
  sentinelRef: React.RefObject<HTMLDivElement | null>;
  hasMore: boolean;
}) {
  if (!hasMore) return null;
  return (
    <div
      ref={sentinelRef}
      className="flex items-center justify-center gap-2 py-3 text-xs text-muted-foreground"
    >
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      Loading more…
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

const STICKY_THEAD = 'sticky top-0 z-10';

// ── Variant A: By Assessment ─────────────────────────────────────────────
type AKey = 'grade' | 'date' | 'item' | 'students' | 'average';

const A_ACCESSORS: Record<AKey, SortAccessor<AssessmentSummaryListRow>> = {
  grade: (r) => (r.grade ?? '').toLowerCase(),
  date: (r) => r.assessment_date ?? '',
  item: (r) => (r.item_name ?? '').toLowerCase(),
  students: (r) => r.total_students ?? -1,
  average: (r) => r.grade_average ?? -1,
};

function ByAssessment({
  rows,
  search,
  schoolAverage,
}: {
  rows: AssessmentSummaryListRow[];
  search: string;
  schoolAverage: number | null;
}) {
  const q = search.trim().toLowerCase();
  const filtered = useMemo(
    () => (q ? rows.filter((r) => matches(r.item_name, q)) : rows),
    [rows, q],
  );
  const { sortedRows, sortColumn, sortDirection, onHeaderClick } = useTableSort<
    AssessmentSummaryListRow,
    AKey
  >({
    rows: filtered,
    accessors: A_ACCESSORS,
    defaultColumn: 'date',
    defaultDirection: 'desc',
    initialDirections: { students: 'desc', average: 'desc', date: 'desc' },
  });
  const { visibleRows, scrollRef, sentinelRef, hasMore, shown, total } =
    useInfiniteWindow(sortedRows);

  return (
    <>
      <ScrollRegion scrollRef={scrollRef}>
        <table className="w-full border-collapse">
          <thead className={STICKY_THEAD}>
            <tr>
              <Th><SortableHeader column="grade" label="Grade" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
              <Th><SortableHeader column="date" label="Assessment Date" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
              <Th><SortableHeader column="item" label="Item Name" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
              <Th align="center"><SortableHeader column="students" label="Total Students" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" /></Th>
              <Th><SortableHeader column="average" label="Grade Average" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
              <Th align="right">Report</Th>
            </tr>
          </thead>
          <tbody>
            {total === 0 ? (
              <EmptyRow cols={6} label="No assessments match the current filters." />
            ) : (
              visibleRows.map((r) => (
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
        <LoadMore sentinelRef={sentinelRef} hasMore={hasMore} />
      </ScrollRegion>
      <ShownFooter shown={shown} total={total} />
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

// ── Variant B: By Standard ───────────────────────────────────────────────
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

// ── Variant C: By Strand ─────────────────────────────────────────────────
type StKey = 'strand' | 'standards' | 'questions' | 'assessments' | 'average';

const ST_ACCESSORS: Record<StKey, SortAccessor<StrandSummaryRollupRow>> = {
  strand: (r) => (r.strand ?? '').toLowerCase(),
  standards: (r) => r.num_standards,
  questions: (r) => r.num_questions,
  assessments: (r) => r.num_assessments,
  average: (r) => r.grade_average,
};

function ByStrand({
  rows,
  search,
  schoolAverage,
}: {
  rows: StrandSummaryRollupRow[];
  search: string;
  schoolAverage: number | null;
}) {
  const q = search.trim().toLowerCase();
  const filtered = useMemo(
    () => (q ? rows.filter((r) => matches(r.strand, q)) : rows),
    [rows, q],
  );
  const { sortedRows, sortColumn, sortDirection, onHeaderClick } = useTableSort<
    StrandSummaryRollupRow,
    StKey
  >({
    rows: filtered,
    accessors: ST_ACCESSORS,
    defaultColumn: 'strand',
    defaultDirection: 'asc',
    initialDirections: { standards: 'desc', questions: 'desc', assessments: 'desc', average: 'desc' },
  });
  const { visibleRows, scrollRef, sentinelRef, hasMore, shown, total } =
    useInfiniteWindow(sortedRows);

  return (
    <>
      <ScrollRegion scrollRef={scrollRef}>
        <table className="w-full border-collapse">
          <thead className={STICKY_THEAD}>
            <tr>
              <Th><SortableHeader column="strand" label="Strand" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
              <Th align="center"><SortableHeader column="standards" label="# Standards" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" /></Th>
              <Th align="center"><SortableHeader column="questions" label="# Questions" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" /></Th>
              <Th align="center"><SortableHeader column="assessments" label="# Assessments" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" /></Th>
              <Th><SortableHeader column="average" label="Grade Average" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
            </tr>
          </thead>
          <tbody>
            {total === 0 ? (
              <EmptyRow cols={5} label="No strands match the current filters." />
            ) : (
              visibleRows.map((r) => (
                <tr key={r.strand} className="transition-colors hover:bg-accent/30">
                  <td className={`${TD} font-medium text-foreground`} style={{ borderColor: LAYOUT_BORDER }}>{r.strand}</td>
                  <td className={`${TD} text-center tabular-nums`} style={{ borderColor: LAYOUT_BORDER }}>{r.num_standards}</td>
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
