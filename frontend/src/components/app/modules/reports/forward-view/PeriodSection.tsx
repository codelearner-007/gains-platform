'use client';

import type { ForwardViewPeriodGroup } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import UnitStandardsTable from '@/components/app/modules/reports/forward-view/UnitStandardsTable';
import { formatShortDate } from '@/lib/reports/format';

interface PeriodSectionProps {
  period: ForwardViewPeriodGroup;
  /** When true, a period with zero flagged standards collapses to a muted line
   *  and each zero-flagged unit within it collapses too. */
  flaggedOnly: boolean;
}

/**
 * One PERIOD band (tinted `HEADER_BAR_BG` header with a right-aligned date
 * range / unit count / flagged-of-total distinct-standard count) over its stack
 * of UNIT cards. Periods
 * arrive pre-ordered chronologically from the backend; units within a period
 * likewise. In flagged-only mode a period with nothing flagged is still listed
 * but its body collapses to a single muted line.
 */
export default function PeriodSection({
  period,
  flaggedOnly,
}: PeriodSectionProps) {
  const start = formatShortDate(period.date_start);
  const end = formatShortDate(period.date_end);
  const dateRange =
    start && end
      ? start === end
        ? start
        : `${start} – ${end}`
      : start || end || null;

  const unitCount = period.units.length;
  const rightLabel = [
    dateRange,
    `${unitCount} unit${unitCount === 1 ? '' : 's'}`,
    `${period.flagged_count} of ${period.standards_count} standards flagged`,
  ]
    .filter(Boolean)
    .join(' • ');

  const showUnits = !flaggedOnly || period.flagged_count > 0;

  return (
    <section className="flex flex-col gap-2 print:break-inside-avoid">
      <div
        className="flex items-center justify-between gap-3 border px-3 py-1.5"
        style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      >
        <span className="min-w-0 truncate text-[13px] font-bold text-black">
          {period.period}
        </span>
        <span className="shrink-0 text-right text-[11px] font-medium text-black/80">
          {rightLabel}
        </span>
      </div>

      {showUnits ? (
        <div className="flex flex-col gap-2">
          {period.units.map((unit, i) => (
            <UnitStandardsTable
              key={`${unit.unit}-${unit.assessment_date ?? ''}-${i}`}
              unit={unit}
              flaggedOnly={flaggedOnly}
            />
          ))}
        </div>
      ) : (
        <div
          className="rounded border bg-white px-3 py-2 text-xs text-muted-foreground"
          style={{ borderColor: LAYOUT_BORDER }}
        >
          No flagged standards in this period
        </div>
      )}
    </section>
  );
}
