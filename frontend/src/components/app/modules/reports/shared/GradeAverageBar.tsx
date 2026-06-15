import {
  DATA_BAR_MARKER,
  DATA_BAR_TRACK,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';

interface GradeAverageBarProps {
  /** Row grade average, 0..1. `null` renders an em-dash (no data). */
  value: number | null;
  /**
   * School-wide grade average (same filter scope), 0..1. Drawn as a dashed
   * vertical reference marker — the legacy "_Data Bar - Grade Average"
   * AvgValue line. Omit to hide the marker.
   */
  marker?: number | null;
}

/**
 * Horizontal grade-average data bar for the dashboard Assessments Summary
 * table — a faithful rebuild of the legacy PowerBI `Measure._Data Bar -
 * Grade Average` inline-SVG measure.
 *
 *   • fill width  = value (0..1), capped at 100%
 *   • fill color  = performanceColor(value)  (<70% pink / 70-80% yellow / ≥80% green)
 *   • dashed line = the school-wide average (marker), for at-a-glance context
 *   • right label = the exact % (text, so meaning never relies on color alone)
 */
export default function GradeAverageBar({ value, marker }: GradeAverageBarProps) {
  if (value === null) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  const pct = Math.max(0, Math.min(1, value));
  const markerPct =
    marker === null || marker === undefined
      ? null
      : Math.max(0, Math.min(1, marker));
  const label = formatPercent(value, 1);

  return (
    <div
      className="flex items-center gap-2"
      role="img"
      aria-label={`Grade average ${label}${
        markerPct !== null ? `, school average ${formatPercent(marker as number, 1)}` : ''
      }`}
    >
      <div
        className="relative h-4 flex-1 overflow-hidden rounded-sm"
        style={{ backgroundColor: DATA_BAR_TRACK, border: `1px solid ${LAYOUT_BORDER}` }}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-sm"
          style={{ width: `${pct * 100}%`, backgroundColor: performanceColor(value) }}
        />
        {markerPct !== null && (
          <div
            className="absolute inset-y-0 w-px"
            style={{
              left: `${markerPct * 100}%`,
              borderLeft: `1px dashed ${DATA_BAR_MARKER}`,
            }}
            aria-hidden
          />
        )}
      </div>
      <span className="w-12 shrink-0 text-right text-xs font-semibold tabular-nums text-foreground">
        {label}
      </span>
    </div>
  );
}
