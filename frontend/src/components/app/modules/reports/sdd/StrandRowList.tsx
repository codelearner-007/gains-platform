'use client';

import { useMemo } from 'react';
import type { SddStrandRow } from '@/lib/reports/types';
import {
  INCORRECT_GREY,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';

interface StrandRowListProps {
  strands: SddStrandRow[];
  // Multi-select: every active strand value. Clicking a row toggles membership.
  selectedStrands?: string[];
  onSelectStrand?: (strand: string) => void;
}

export default function StrandRowList({
  strands,
  selectedStrands,
  onSelectStrand,
}: StrandRowListProps) {
  const selectedSet = useMemo(
    () => new Set(selectedStrands ?? []),
    [selectedStrands],
  );
  const hasSelection = selectedSet.size > 0;
  const rows = useMemo(
    // Unassessed strands (grade_average === null) sort first; blank label.
    () =>
      [...strands].sort(
        (a, b) => (a.grade_average ?? -1) - (b.grade_average ?? -1),
      ),
    [strands],
  );

  return (
    <div
      className="flex flex-col bg-white border h-full min-h-[180px]"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      {rows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-xs text-neutral-500 py-6">
          No strand data
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto max-h-[260px] p-2 flex flex-col gap-1.5">
          {rows.map((row, i) => {
            const pct = Math.max(0, Math.min(1, row.grade_average ?? 0));
            const fill = performanceColor(pct);
            const pctLabel = row.grade_average == null ? '' : formatPercent(pct, 1);
            const isSelected = selectedSet.has(row.strand);
            const dim = hasSelection && !isSelected;
            return (
              <li
                key={`${row.strand}-${i}`}
                className={`flex flex-col gap-0.5 text-[11px] leading-tight rounded-sm transition-opacity ${onSelectStrand ? 'cursor-pointer' : ''} ${isSelected ? 'ring-2 ring-neutral-800 ring-offset-1' : ''}`}
                style={{ opacity: dim ? 0.45 : 1 }}
                onClick={() => onSelectStrand?.(row.strand)}
                role={onSelectStrand ? 'button' : undefined}
                tabIndex={onSelectStrand ? 0 : undefined}
                onKeyDown={(e) => {
                  if (
                    onSelectStrand &&
                    (e.key === 'Enter' || e.key === ' ')
                  ) {
                    e.preventDefault();
                    onSelectStrand(row.strand);
                  }
                }}
              >
                <div className="flex items-center gap-2">
                  <div
                    className="flex-1 relative h-5 rounded-sm overflow-hidden"
                    style={{ backgroundColor: INCORRECT_GREY }}
                  >
                    <div
                      className="absolute inset-y-0 left-0 flex items-center px-1.5"
                      style={{
                        width: `${pct * 100}%`,
                        backgroundColor: fill,
                      }}
                    >
                      <span className="font-semibold text-black text-[11px] tabular-nums">
                        {pctLabel}
                      </span>
                    </div>
                    <span
                      className="absolute inset-y-0 right-0 flex items-center px-1.5 truncate font-semibold text-black"
                      style={{
                        // Right-aligned label. Cap width so it never collides with
                        // the left percentage. When the bar fills past ~85% it sits
                        // over the colored fill rather than the grey track, so a
                        // white halo (mirrors the treemap's stroke) keeps it legible
                        // instead of hiding it — the old `opacity:0` made high-
                        // performing strands (e.g. Foundational Skills 88%) blank.
                        maxWidth: '75%',
                        textShadow: '0 0 2px #fff, 0 0 2px #fff, 0 0 2px #fff',
                      }}
                      title={row.strand}
                    >
                      {row.strand}
                    </span>
                  </div>
                </div>
                <div className="text-[10px] text-neutral-700 pl-1">
                  {row.num_standards} Standard
                  {row.num_standards === 1 ? '' : 's'} across {row.num_questions}{' '}
                  question{row.num_questions === 1 ? '' : 's'}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
