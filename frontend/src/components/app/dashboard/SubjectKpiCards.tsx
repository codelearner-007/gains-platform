'use client';

import { Skeleton } from '@/components/ui/skeleton';
import { performanceBand } from '@/lib/reports/colors';
import type { DashboardSubjectCard } from '@/lib/reports/types';
import HScrollRow from './HScrollRow';

interface SubjectKpiCardsProps {
  subjects: DashboardSubjectCard[];
  selected?: string;
  onSelect: (subject: string | undefined) => void;
  loading?: boolean;
  /** Lock interaction while filter-dependent data is refetching. */
  disabled?: boolean;
}

/**
 * Subject KPI cards — the dashboard's hero stat and primary subject filter
 * (legacy PowerBI subject slicer). Each card is fully tinted by its
 * performance band (green ≥80 / amber 70–80 / rose <70) with a matching accent
 * border and WCAG-AA dark text, so the traffic-light reads at a glance without
 * relying on a tiny dot. Single-select: click a card to scope the dashboard to
 * that subject, click the selected card again to clear. The cards lay out in an
 * even wrapping row that fills the width and reflows on smaller screens.
 */
export default function SubjectKpiCards({
  subjects,
  selected,
  onSelect,
  loading,
  disabled,
}: SubjectKpiCardsProps) {
  if (loading) {
    return (
      <div className="flex gap-3 overflow-hidden px-0.5 py-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[78px] min-w-[150px] max-w-[360px] flex-1 rounded-xl" />
        ))}
      </div>
    );
  }
  if (subjects.length === 0) {
    return (
      <p className="px-1 text-sm text-muted-foreground">
        No subjects for the selected filters.
      </p>
    );
  }

  return (
    <HScrollRow ariaLabel="Filter by subject" gapClass="gap-3">
      {subjects.map((s) => {
        const isSelected = selected === s.subject;
        const band = s.grade_average != null ? performanceBand(s.grade_average) : null;
        return (
          <button
            key={s.subject}
            type="button"
            aria-pressed={isSelected}
            disabled={disabled}
            onClick={() => onSelect(isSelected ? undefined : s.subject)}
            style={
              band
                ? { backgroundColor: band.bg, borderColor: band.accent, color: band.fg }
                : undefined
            }
            className={[
              'flex min-w-[150px] max-w-[360px] flex-1 flex-col gap-1 rounded-xl border-2 px-4 py-3 text-left transition-all duration-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
              'disabled:cursor-not-allowed disabled:opacity-55 disabled:shadow-none',
              'enabled:cursor-pointer motion-safe:enabled:hover:-translate-y-0.5',
              band ? '' : 'border-border bg-card text-foreground',
              isSelected ? 'shadow-md ring-2 ring-ring ring-offset-1' : 'shadow-sm enabled:hover:shadow-md',
            ].join(' ')}
          >
            <span className="truncate text-sm font-semibold">{s.subject}</span>
            <span className="text-[1.75rem] font-bold leading-none tabular-nums">
              {s.grade_average_pct}
            </span>
          </button>
        );
      })}
    </HScrollRow>
  );
}
