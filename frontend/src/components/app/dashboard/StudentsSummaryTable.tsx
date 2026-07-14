'use client';

import { useEffect, useRef } from 'react';
import { ExternalLink, Loader2 } from 'lucide-react';
import type { StudentBrowseRow } from '@/lib/reports/types';
import { LAYOUT_BORDER } from '@/lib/reports/colors';
import { Skeleton } from '@/components/ui/skeleton';
import {
  SortableHeader,
  type SortDirection,
} from '@/lib/reports/useTableSort';
import GradeAverageBar from '@/components/app/modules/reports/shared/GradeAverageBar';
import { bandTone } from '@/components/app/modules/students/bands';

/** Server sort keys for the roster (match the backend whitelist). */
export type StudentSortKey = 'name' | 'overall' | 'assessments' | 'subjects';

interface Props {
  schoolId?: string;
  session?: string;
  /** School-wide overall class average (0..1) for the data-bar reference marker. */
  classAverage: number | null;
  rows: StudentBrowseRow[];
  total: number;
  hasMore: boolean;
  isFetchingMore: boolean;
  onFetchMore: () => void;
  sort: StudentSortKey;
  dir: SortDirection;
  onSort: (col: StudentSortKey) => void;
  loading: boolean;
}

function reportHref(uid: string, schoolId?: string, session?: string): string {
  const qs = new URLSearchParams();
  if (schoolId) qs.set('school_id', schoolId);
  if (session) qs.set('session', session);
  const q = qs.toString();
  return `/app/students/${encodeURIComponent(uid)}/report${q ? `?${q}` : ''}`;
}

function SubjectChip({ subject, pct, band }: { subject: string; pct: number | null; band: import('@/lib/reports/types').PerfBandName }) {
  const t = bandTone(band);
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10.5px] font-medium tabular-nums"
      style={{ background: t.bg, color: t.fg, border: `1px solid ${t.accent}` }}
      title={`${subject}: ${pct === null ? '—' : `${pct.toFixed(1)}%`}`}
    >
      {subject}
      <span className="opacity-80">{pct === null ? '—' : Math.round(pct)}</span>
    </span>
  );
}

function MasteryMini({ green, yellow, pink }: { green: number; yellow: number; pink: number }) {
  const total = green + yellow + pink;
  if (total === 0) return <span className="text-xs text-muted-foreground">—</span>;
  const cell = (n: number, band: 'green' | 'yellow' | 'pink') =>
    n > 0 ? (
      <span
        style={{ width: `${(n / total) * 100}%`, background: bandTone(band).accent }}
        className="h-2.5"
        title={`${n}`}
      />
    ) : null;
  return (
    <div className="flex items-center gap-1.5">
      <span className="flex h-2.5 w-16 overflow-hidden rounded-sm border" style={{ borderColor: LAYOUT_BORDER }}>
        {cell(green, 'green')}
        {cell(yellow, 'yellow')}
        {cell(pink, 'pink')}
      </span>
      <span className="text-[11px] tabular-nums text-muted-foreground">{total}</span>
    </div>
  );
}

function Th({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'center' | 'right' }) {
  return (
    <th
      className="border-b border-border bg-muted px-3 py-2 text-xs font-medium text-muted-foreground"
      style={{ textAlign: align }}
    >
      {children}
    </th>
  );
}

const TD = 'border-b px-3 py-1.5 text-sm';

export default function StudentsSummaryTable({
  schoolId,
  session,
  classAverage,
  rows,
  total,
  hasMore,
  isFetchingMore,
  onFetchMore,
  sort,
  dir,
  onSort,
  loading,
}: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const cb = useRef(onFetchMore);
  useEffect(() => {
    cb.current = onFetchMore;
  });

  useEffect(() => {
    if (!hasMore || isFetchingMore) return;
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
  }, [hasMore, isFetchingMore]);

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
      {loading ? (
        <div className="space-y-2 p-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : (
        <>
          <div ref={scrollRef} className="max-h-[26rem] overflow-auto">
            <table className="w-full border-collapse">
              <thead className="sticky top-0 z-10">
                <tr>
                  <Th><SortableHeader column="name" label="Student" sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
                  <Th>Subjects</Th>
                  <Th align="center"><SortableHeader column="assessments" label="Assessments" title="Assessments" description="Number of assessments the student has taken in scope." sortColumn={sort} sortDirection={dir} onClick={onSort} align="center" /></Th>
                  <Th align="center">Standards mastery</Th>
                  <Th><SortableHeader column="overall" label="Overall" title="Overall" description="Overall percent-correct across all subjects, with the class-average marker." sortColumn={sort} sortDirection={dir} onClick={onSort} /></Th>
                  <Th align="right">Report</Th>
                </tr>
              </thead>
              <tbody>
                {total === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-10 text-center text-sm text-muted-foreground">
                      No students match the current filters.
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => {
                    const href = reportHref(r.uid, schoolId, session);
                    return (
                      <tr key={r.uid} className="transition-colors hover:bg-accent/30">
                        <td className={`${TD} min-w-[180px]`} style={{ borderColor: LAYOUT_BORDER }}>
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-foreground hover:text-primary hover:underline"
                          >
                            {r.name}
                          </a>
                          {r.grades.length > 0 && (
                            <span className="ml-1.5 text-[11px] text-muted-foreground">
                              {r.grades.join(', ')}
                            </span>
                          )}
                        </td>
                        <td className={`${TD} max-w-[320px]`} style={{ borderColor: LAYOUT_BORDER }}>
                          <div className="flex flex-wrap gap-1">
                            {r.subjects.slice(0, 6).map((s) => (
                              <SubjectChip key={`${s.subject}-${s.grade}`} subject={s.subject} pct={s.pct} band={s.band} />
                            ))}
                            {r.subjects.length > 6 && (
                              <span className="text-[11px] text-muted-foreground">+{r.subjects.length - 6}</span>
                            )}
                          </div>
                        </td>
                        <td className={`${TD} text-center tabular-nums`} style={{ borderColor: LAYOUT_BORDER }}>{r.n_assessments}</td>
                        <td className={`${TD}`} style={{ borderColor: LAYOUT_BORDER }}>
                          <MasteryMini green={r.mastery.green} yellow={r.mastery.yellow} pink={r.mastery.pink} />
                        </td>
                        <td className={`${TD} min-w-[190px]`} style={{ borderColor: LAYOUT_BORDER }}>
                          <GradeAverageBar
                            value={r.overall_pct === null ? null : r.overall_pct / 100}
                            marker={classAverage}
                          />
                        </td>
                        <td className={`${TD} text-right`} style={{ borderColor: LAYOUT_BORDER }}>
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs font-medium text-foreground transition-colors hover:bg-accent"
                            style={{ borderColor: LAYOUT_BORDER }}
                            aria-label={`Open full report for ${r.name} in a new tab`}
                          >
                            Open
                            <ExternalLink className="h-3 w-3 text-muted-foreground" />
                          </a>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
            {hasMore && (
              <div ref={sentinelRef} className="flex items-center justify-center gap-2 py-3 text-xs text-muted-foreground">
                {isFetchingMore && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {isFetchingMore ? 'Loading more…' : ' '}
              </div>
            )}
          </div>
          {total > 0 && (
            <div
              className="border-t px-4 py-2 text-right text-[11px] tabular-nums text-muted-foreground"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              Showing {rows.length} of {total}
            </div>
          )}
        </>
      )}
    </div>
  );
}
