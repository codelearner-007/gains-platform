'use client';

import type { CSSProperties } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { performanceBand, perfTextClass } from '@/lib/reports/colors';
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
 * subject slicer). Elevated white cards with a soft performance-tinted wash
 * rising behind the % (colour reads as data, tied to the metric — never a hard
 * border or block). Selection reads through the single indigo accent: brand
 * ring + soft wash + brand glow. Single-select: click to scope the dashboard,
 * click the selected card again to clear.
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
        const band = s.grade_average != null ? performanceBand(s.grade_average) : null;
        // Soft perf-tinted wash rising from the % (the data), fading to the card
        // surface — a gentle colour identity, not a tint block. Selected cards
        // trade the wash for the brand glow so the accent stays singular.
        const style: CSSProperties = {
          backgroundImage:
            band && !isSelected
              ? `linear-gradient(to top, ${band.bg} 0%, ${band.bg} 32%, transparent 88%)`
              : undefined,
          boxShadow: isSelected ? 'var(--shadow-glow)' : undefined,
        };
        return (
          <button
            key={s.subject}
            type="button"
            aria-pressed={isSelected}
            disabled={disabled}
            title={s.subject}
            style={style}
            className={[
              'flex min-w-[10.5rem] max-w-[17.5rem] flex-1 flex-col gap-1.5 rounded-lg border bg-card px-4 py-3 text-left transition-all duration-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
              'enabled:cursor-pointer disabled:cursor-not-allowed disabled:opacity-55',
              isSelected
                ? 'border-primary bg-primary-soft/40 ring-1 ring-primary'
                : 'border-border shadow-sm enabled:hover:-translate-y-0.5 enabled:hover:shadow-md enabled:hover:border-primary/30',
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
