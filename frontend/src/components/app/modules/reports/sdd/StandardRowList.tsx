'use client';

import { useMemo } from 'react';
import type { SddStandardRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  INCORRECT_GREY,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';

interface StandardRowListProps {
  standards: SddStandardRow[];
  selectedStandard?: string | null;
  onSelectStandard?: (cpalms_standard: string) => void;
}

// Sorted ascending by grade_avg so worst performers appear first
// (matches the PBIX Charticulator default — pink rows on top, yellow
// at the bottom).
export default function StandardRowList({
  standards,
  selectedStandard,
  onSelectStandard,
}: StandardRowListProps) {
  const rows = useMemo(
    () => [...standards].sort((a, b) => a.grade_average - b.grade_average),
    [standards],
  );

  return (
    <div
      className="flex flex-col bg-white border h-full min-h-[260px]"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[12px] font-bold text-black border-b"
        style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      >
        Correct % by Standard
      </div>
      {rows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-xs text-neutral-500 py-6">
          No standards data
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto max-h-[360px] px-2 py-2 flex flex-col gap-1">
          {rows.map((row, i) => {
            const pct = Math.max(0, Math.min(1, row.grade_average));
            const fill = performanceColor(pct);
            const subLine = `(${row.num_questions} Q${row.num_questions === 1 ? '' : 's'})`;
            const isSelected = selectedStandard === row.cpalms_standard;
            const dim = !!selectedStandard && !isSelected;
            return (
              <li
                key={`${row.cpalms_standard}-${row.strand}-${i}`}
                className={`flex items-center gap-2 text-[11px] leading-tight rounded-sm px-1 -mx-1 transition-opacity ${onSelectStandard ? 'cursor-pointer' : ''} ${isSelected ? 'ring-2 ring-neutral-800 ring-offset-1' : ''}`}
                style={{ opacity: dim ? 0.45 : 1 }}
                onClick={() => onSelectStandard?.(row.cpalms_standard)}
                role={onSelectStandard ? 'button' : undefined}
                tabIndex={onSelectStandard ? 0 : undefined}
                onKeyDown={(e) => {
                  if (
                    onSelectStandard &&
                    (e.key === 'Enter' || e.key === ' ')
                  ) {
                    e.preventDefault();
                    onSelectStandard(row.cpalms_standard);
                  }
                }}
              >
                <div
                  className="shrink-0 truncate font-medium text-black"
                  style={{ width: '46%' }}
                  title={`${row.cpalms_standard} · ${row.strand}`}
                >
                  <span>{row.cpalms_standard}</span>{' '}
                  <span className="text-neutral-600">{subLine}</span>
                </div>
                <div
                  className="flex-1 relative h-4 rounded-sm overflow-hidden"
                  style={{ backgroundColor: INCORRECT_GREY }}
                  aria-label={`${row.cpalms_standard} ${formatPercent(pct, 1)} correct`}
                >
                  <div
                    className="absolute inset-y-0 left-0"
                    style={{
                      width: `${pct * 100}%`,
                      backgroundColor: fill,
                    }}
                  />
                </div>
                <div
                  className="shrink-0 text-right font-semibold text-black tabular-nums"
                  style={{ width: 44 }}
                >
                  {formatPercent(pct, 1)}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
