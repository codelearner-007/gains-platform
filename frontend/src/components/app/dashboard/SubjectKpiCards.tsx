'use client';

import { Skeleton } from '@/components/ui/skeleton';
import { perfTextClass } from '@/lib/reports/colors';
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
 * Subject filter cards — the dashboard's primary subject slicer (legacy PowerBI
 * subject slicer). Neutral card chrome; the performance traffic-light lives on
 * the % value only (it IS the data), so the card box never carries colour.
 * Selection reads through the single indigo accent (border + ring + soft wash),
 * not a coloured band. Single-select: click to scope the dashboard to that
 * subject, click the selected card again to clear.
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
      <div className="flex gap-3 overflow-hidden px-0.5 py-1">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[84px] min-w-[10.5rem] max-w-[17.5rem] flex-1 rounded-lg" />
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
        return (
          <button
            key={s.subject}
            type="button"
            aria-pressed={isSelected}
            disabled={disabled}
            title={s.subject}
            onClick={() => onSelect(isSelected ? undefined : s.subject)}
            className={[
              'flex min-w-[10.5rem] max-w-[17.5rem] flex-1 flex-col gap-1.5 rounded-lg border bg-card px-4 py-3 text-left transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
              'enabled:cursor-pointer disabled:cursor-not-allowed disabled:opacity-55',
              isSelected
                ? 'border-primary ring-1 ring-primary bg-primary-soft/50'
                : 'border-border enabled:hover:border-primary/40 enabled:hover:bg-accent/40',
            ].join(' ')}
          >
            <span className="line-clamp-2 min-h-[2.25rem] text-sm font-medium leading-snug text-foreground">
              {s.subject}
            </span>
            <span
              className={[
                'text-2xl font-semibold leading-none tabular-nums',
                s.grade_average != null ? perfTextClass(s.grade_average) : 'text-foreground',
              ].join(' ')}
            >
              {s.grade_average_pct}
            </span>
          </button>
        );
      })}
    </HScrollRow>
  );
}
