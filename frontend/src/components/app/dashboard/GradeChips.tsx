'use client';

import { Skeleton } from '@/components/ui/skeleton';
import HScrollRow from './HScrollRow';

interface GradeChipsProps {
  grades: string[];
  selected?: string;
  onSelect: (grade: string | undefined) => void;
  loading?: boolean;
  /** Lock interaction while filter-dependent data is refetching. */
  disabled?: boolean;
}

/**
 * Single-select grade pills — the dashboard's other primary front filter
 * (legacy grade slicer). Laid out as an even-width grid that fills the row and
 * reflows responsively, so the grades stay evenly spaced and aligned. Click a
 * chip to scope to that grade, click the selected chip again to clear.
 */
export default function GradeChips({
  grades,
  selected,
  onSelect,
  loading,
  disabled,
}: GradeChipsProps) {
  if (loading) {
    return (
      <div className="flex gap-2 overflow-hidden px-0.5 py-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <Skeleton key={i} className="h-9 min-w-[80px] max-w-[180px] flex-1 rounded-full" />
        ))}
      </div>
    );
  }
  if (grades.length === 0) return null;

  return (
    <HScrollRow ariaLabel="Filter by grade" gapClass="gap-2">
      {grades.map((g) => {
        const isSelected = selected === g;
        return (
          <button
            key={g}
            type="button"
            aria-pressed={isSelected}
            disabled={disabled}
            onClick={() => onSelect(isSelected ? undefined : g)}
            className={[
              'h-9 min-w-[80px] max-w-[180px] flex-1 rounded-full border px-4 text-center text-sm font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              'enabled:cursor-pointer disabled:cursor-not-allowed disabled:opacity-55',
              isSelected
                ? 'border-primary bg-primary text-primary-foreground shadow-sm'
                : 'border-border bg-card text-foreground enabled:hover:border-primary/40 enabled:hover:bg-accent/40',
            ].join(' ')}
          >
            {g}
          </button>
        );
      })}
    </HScrollRow>
  );
}
