'use client';

import {
  HEADER_BAR_BG,
  INCORRECT_GREY,
  LAYOUT_BORDER,
} from '@/lib/reports/colors';

export interface RankedBarRow {
  /** Stable React key (caller guarantees uniqueness). */
  key: string;
  /** Primary left label (e.g. a standard code or strand name). */
  label: string;
  /** Muted secondary label after the primary (e.g. "(6 Qs)"). */
  sublabel?: string;
  /** Bar width as 0..1. `null` = no data → empty track, no fill. */
  fraction: number | null;
  /** Right-aligned value text (e.g. "85%" or a raw count "12"). */
  valueLabel: string;
  /** Bar fill color (e.g. performanceColor(...) or a neutral accent). */
  color: string;
  /** Full detail surfaced via the native title tooltip. */
  title?: string;
}

interface RankedBarListProps {
  title: string;
  rows: RankedBarRow[];
  emptyMessage?: string;
  /** Capped scroll-viewport height; rows beyond it scroll. Default 520. */
  maxHeight?: number;
  /** Left label column width (%). Default 46. */
  labelWidthPct?: number;
}

/**
 * A ranked horizontal-bar list rendered as plain DOM rows (not SVG), inside a
 * capped `overflow-y-auto` viewport. Each row keeps a fixed legible height, so
 * ANY number of categories stays readable and the list simply scrolls — it can
 * never collapse hundreds of bars/labels into an illegible smear the way a
 * fixed-height recharts category chart does. Far cheaper than rendering
 * hundreds of SVG bars + labels, and screen-reader friendly (real text rows).
 *
 * The canonical pattern for "one bar per category" in the reports; rows are
 * rendered in the order given (the caller sorts).
 */
export default function RankedBarList({
  title,
  rows,
  emptyMessage = 'No data',
  maxHeight = 520,
  labelWidthPct = 46,
}: RankedBarListProps) {
  return (
    <div
      className="flex h-full min-h-[260px] flex-col border bg-white"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="border-b px-3 py-1.5 text-[13px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      >
        {title}
      </div>
      {rows.length === 0 ? (
        <div className="flex flex-1 items-center justify-center py-6 text-sm text-neutral-500">
          {emptyMessage}
        </div>
      ) : (
        <ul
          className="flex flex-1 flex-col gap-1 overflow-y-auto px-2 py-2"
          style={{ maxHeight }}
          tabIndex={0}
          aria-label={title}
        >
          {rows.map((row) => {
            const empty = row.fraction == null;
            const pct = Math.max(0, Math.min(1, row.fraction ?? 0));
            return (
              <li
                key={row.key}
                className="flex items-center gap-2 text-[11px] leading-tight"
                title={row.title}
              >
                <div
                  className="shrink-0 truncate font-medium text-black"
                  style={{ width: `${labelWidthPct}%` }}
                >
                  <span>{row.label}</span>
                  {row.sublabel ? (
                    <span className="text-neutral-600"> {row.sublabel}</span>
                  ) : null}
                </div>
                <div
                  className="relative h-4 flex-1 overflow-hidden rounded-sm"
                  style={{ backgroundColor: INCORRECT_GREY }}
                  aria-label={`${row.label} ${row.valueLabel}`}
                >
                  {!empty && (
                    <div
                      className="absolute inset-y-0 left-0"
                      style={{ width: `${pct * 100}%`, backgroundColor: row.color }}
                    />
                  )}
                </div>
                <div
                  className="shrink-0 text-right font-semibold tabular-nums text-black"
                  style={{ width: 48 }}
                >
                  {row.valueLabel}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
