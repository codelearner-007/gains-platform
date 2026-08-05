'use client';

import type { ForwardViewStandardRow } from '@/lib/reports/types';
import {
  INCORRECT_GREY,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';

interface TopFocusStripProps {
  /** ≤10 flagged rows, scope-pooled, already pct-ascending (worst first). */
  rows: ForwardViewStandardRow[];
}

/**
 * Worst-first horizontal-bar list for the scope-pooled top-focus standards.
 * Mirrors the SDD `StandardRowList` bar treatment (FROZEN `performanceColor`
 * fill over an `INCORRECT_GREY` track, code + question count + %) without its
 * SDD-coupled cross-filter/selection props. The rows arrive pre-sorted, so the
 * order is preserved as-is.
 */
export default function TopFocusStrip({ rows }: TopFocusStripProps) {
  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <ul className="flex flex-col gap-1.5 px-3 py-2.5">
        {rows.map((row, i) => {
          const unassessed = row.grade_average == null;
          const pct = unassessed
            ? 0
            : Math.max(0, Math.min(1, row.grade_average as number));
          const fill = performanceColor(pct);
          const label = row.cpalms_standard || row.schoology_standard;
          const pctLabel = unassessed ? '' : formatPercent(pct, 1);
          const subLine = `(${row.num_questions} Q${row.num_questions === 1 ? '' : 's'})`;
          return (
            <li
              key={`${row.schoology_standard}-${i}`}
              className="flex items-center gap-2 text-[11px] leading-tight"
            >
              <div
                className="shrink-0 truncate font-medium text-black"
                style={{ width: '38%' }}
                title={`${label} · ${row.strand}`}
              >
                <span>{label}</span>{' '}
                <span className="text-neutral-600">{subLine}</span>
              </div>
              <div
                className="relative h-4 flex-1 overflow-hidden rounded-sm"
                style={{ backgroundColor: INCORRECT_GREY }}
                aria-label={`${label} ${pctLabel} correct`}
              >
                {!unassessed && (
                  <div
                    className="absolute inset-y-0 left-0"
                    style={{ width: `${pct * 100}%`, backgroundColor: fill }}
                  />
                )}
              </div>
              <div
                className="shrink-0 text-right font-semibold text-black tabular-nums"
                style={{ width: 44 }}
              >
                {pctLabel}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
