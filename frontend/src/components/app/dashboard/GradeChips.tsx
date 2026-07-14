'use client';

import { Skeleton } from '@/components/ui/skeleton';

interface GradeChipsProps {
  grades: string[];
  selected?: string;
  onSelect: (grade: string | undefined) => void;
  loading?: boolean;
  /** Lock interaction while filter-dependent data is refetching. */
  disabled?: boolean;
}

/**
 * Single-select grade filter — the dashboard's other primary front slicer
 * (legacy grade slicer). One connected segmented control on a muted track
 * (not a crowd of pills), so it reads as a single control. Full grade labels
 * never truncate; the track scrolls horizontally when it overflows. Click a
 * segment to scope to that grade, click the selected one again to clear.
 */
export default function GradeChips({
  grades,
  selected,
  onSelect,
  loading,
  disabled,
}: GradeChipsProps) {
  if (loading) {
    return <Skeleton className="h-9 w-full max-w-xl rounded-lg" />;
  }
  if (grades.length === 0) return null;

  return (
    <div
      role="group"
      aria-label="Filter by grade"
      className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-lg bg-muted p-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
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
              'h-8 shrink-0 whitespace-nowrap rounded-md px-3 text-sm font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              'enabled:cursor-pointer disabled:cursor-not-allowed disabled:opacity-55',
              isSelected
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground enabled:hover:bg-background/70 enabled:hover:text-foreground',
            ].join(' ')}
          >
            {g}
          </button>
        );
      })}
    </div>
  );
}
