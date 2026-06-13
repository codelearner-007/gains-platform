'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ChevronDown } from 'lucide-react';
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
 * Dashboard (PBIX "Home"). A single grid whose grouping/columns switch via a
 * View toggle:
 *   • By Assessment — one row per item (the legacy main grid, real data)
 *   • By Standard   — school-wide standards rollup (rebuilt from real data;
 *                     legacy's template binding was broken)
 *   • By Strand     — school-wide strand rollup (the legacy "Avg by Strands")
 * Every detail row carries a grade-average data bar with a dashed marker at
 * the school-wide average (same filter scope).
 */

export type SummaryView = 'assessment' | 'standard' | 'strand';

const VIEWS: { value: SummaryView; label: string }[] = [
  { value: 'assessment', label: 'By Assessment' },
  { value: 'standard', label: 'By Standard' },
  { value: 'strand', label: 'By Strand' },
];

// Launch menu = the assessment report family, minus the drill-through (IAD),
// straight from the registry — identical to the AssessmentBrowser launcher.
const ROW_ACTIONS = getReportsByGroup('assessment').filter(
  (r) => r.kind !== 'drilldown',
);

interface Props {
  /** School-wide grade average (0..1) for the data-bar reference marker. */
  schoolAverage: number | null;
  assessments: AssessmentSummaryListRow[];
  standards: StandardSummaryRollupRow[];
  strands: StrandSummaryRollupRow[];
  loading: boolean;
}

export default function AssessmentsSummaryTable({
  schoolAverage,
  assessments,
  standards,
  strands,
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
        <ByAssessment rows={assessments} schoolAverage={schoolAverage} />
      ) : view === 'standard' ? (
        <ByStandard rows={standards} schoolAverage={schoolAverage} />
      ) : (
        <ByStrand rows={strands} schoolAverage={schoolAverage} />
      )}
    </div>
  );
}

// ── Shared table chrome ──────────────────────────────────────────────────
function Th({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'center' | 'right' }) {
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

function EmptyRow({ cols, label }: { cols: number; label: string }) {
  return (
    <tr>
      <td colSpan={cols} className="px-3 py-10 text-center text-sm text-muted-foreground">
        {label}
      </td>
    </tr>
  );
}

// ── Variant A: By Assessment ─────────────────────────────────────────────
type AKey = 'grade' | 'date' | 'item' | 'students' | 'average';

function ByAssessment({
  rows,
  schoolAverage,
}: {
  rows: AssessmentSummaryListRow[];
  schoolAverage: number | null;
}) {
  const accessors: Record<AKey, SortAccessor<AssessmentSummaryListRow>> = {
    grade: (r) => (r.grade ?? '').toLowerCase(),
    date: (r) => r.assessment_date ?? '',
    item: (r) => (r.item_name ?? '').toLowerCase(),
    students: (r) => r.total_students ?? -1,
    average: (r) => r.grade_average ?? -1,
  };
  const { sortedRows, sortColumn, sortDirection, onHeaderClick } = useTableSort<
    AssessmentSummaryListRow,
    AKey
  >({
    rows,
    accessors,
    defaultColumn: 'date',
    defaultDirection: 'desc',
    initialDirections: { students: 'desc', average: 'desc', date: 'desc' },
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
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
          {sortedRows.length === 0 ? (
            <EmptyRow cols={6} label="No assessments match the current filters." />
          ) : (
            sortedRows.map((r) => (
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
    </div>
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

function ByStandard({
  rows,
  schoolAverage,
}: {
  rows: StandardSummaryRollupRow[];
  schoolAverage: number | null;
}) {
  const accessors: Record<SKey, SortAccessor<StandardSummaryRollupRow>> = {
    standard: (r) => (r.cpalms_standard || r.schoology_standard || '').toLowerCase(),
    strand: (r) => (r.strand ?? '').toLowerCase(),
    subject: (r) => (r.subject ?? '').toLowerCase(),
    questions: (r) => r.num_questions,
    assessments: (r) => r.num_assessments,
    average: (r) => r.grade_average,
  };
  const { sortedRows, sortColumn, sortDirection, onHeaderClick } = useTableSort<
    StandardSummaryRollupRow,
    SKey
  >({
    rows,
    accessors,
    defaultColumn: 'standard',
    defaultDirection: 'asc',
    initialDirections: { questions: 'desc', assessments: 'desc', average: 'desc' },
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
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
          {sortedRows.length === 0 ? (
            <EmptyRow cols={6} label="No standards match the current filters." />
          ) : (
            sortedRows.map((r) => (
              <tr key={`${r.schoology_standard}-${r.subject}`} className="transition-colors hover:bg-accent/30">
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
    </div>
  );
}

// ── Variant C: By Strand ─────────────────────────────────────────────────
type StKey = 'strand' | 'standards' | 'questions' | 'assessments' | 'average';

function ByStrand({
  rows,
  schoolAverage,
}: {
  rows: StrandSummaryRollupRow[];
  schoolAverage: number | null;
}) {
  const accessors: Record<StKey, SortAccessor<StrandSummaryRollupRow>> = {
    strand: (r) => (r.strand ?? '').toLowerCase(),
    standards: (r) => r.num_standards,
    questions: (r) => r.num_questions,
    assessments: (r) => r.num_assessments,
    average: (r) => r.grade_average,
  };
  const { sortedRows, sortColumn, sortDirection, onHeaderClick } = useTableSort<
    StrandSummaryRollupRow,
    StKey
  >({
    rows,
    accessors,
    defaultColumn: 'strand',
    defaultDirection: 'asc',
    initialDirections: { standards: 'desc', questions: 'desc', assessments: 'desc', average: 'desc' },
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <Th><SortableHeader column="strand" label="Strand" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
            <Th align="center"><SortableHeader column="standards" label="# Standards" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" /></Th>
            <Th align="center"><SortableHeader column="questions" label="# Questions" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" /></Th>
            <Th align="center"><SortableHeader column="assessments" label="# Assessments" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" /></Th>
            <Th><SortableHeader column="average" label="Grade Average" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} /></Th>
          </tr>
        </thead>
        <tbody>
          {sortedRows.length === 0 ? (
            <EmptyRow cols={5} label="No strands match the current filters." />
          ) : (
            sortedRows.map((r) => (
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
    </div>
  );
}
