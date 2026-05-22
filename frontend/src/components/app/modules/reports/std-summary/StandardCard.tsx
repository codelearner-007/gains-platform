'use client';

import { useState } from 'react';
import type { StandardSummaryRollupRow } from '@/lib/reports/types';
import {
  COMPLEXITY_DEFAULT_BG,
  COMPLEXITY_DEFAULT_FG,
  COMPLEXITY_HIGH_BG,
  COMPLEXITY_HIGH_FG,
  COMPLEXITY_LOW_BG,
  COMPLEXITY_LOW_FG,
  COMPLEXITY_MID_BG,
  COMPLEXITY_MID_FG,
  INCORRECT_GREY,
  LAYOUT_BORDER,
  NEUTRAL_CHIP_BG,
  performanceColor,
  STANDARD_HEADER_BG,
  STANDARD_HEADER_FG,
  STRAND_CHIP_BG,
  STRAND_CHIP_FG,
} from '@/lib/reports/colors';

const DESC_TRUNC = 320;

interface StandardCardProps {
  std: StandardSummaryRollupRow;
}

function complexityColors(value: string): { bg: string; fg: string } {
  const v = value.toLowerCase();
  if (v.includes('high')) {
    return { bg: COMPLEXITY_HIGH_BG, fg: COMPLEXITY_HIGH_FG };
  }
  if (v.includes('moderate') || v.includes('mid')) {
    return { bg: COMPLEXITY_MID_BG, fg: COMPLEXITY_MID_FG };
  }
  if (v.includes('low')) {
    return { bg: COMPLEXITY_LOW_BG, fg: COMPLEXITY_LOW_FG };
  }
  return { bg: COMPLEXITY_DEFAULT_BG, fg: COMPLEXITY_DEFAULT_FG };
}

function ComplexityChip({ value }: { value: string }) {
  if (!value) return null;
  const { bg, fg } = complexityColors(value);
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold"
      style={{ backgroundColor: bg, color: fg }}
    >
      {value}
    </span>
  );
}

function MiniBar({ grade }: { grade: number }) {
  const pct = Math.max(0, Math.min(1, grade));
  const fill = performanceColor(grade);
  return (
    <div
      className="w-full overflow-hidden rounded-sm"
      style={{
        height: 10,
        backgroundColor: INCORRECT_GREY,
        border: `1px solid ${LAYOUT_BORDER}`,
      }}
    >
      <div
        style={{
          width: `${pct * 100}%`,
          height: '100%',
          backgroundColor: fill,
          transition: 'width 0.25s ease',
        }}
      />
    </div>
  );
}

function formatChangeDate(iso: string | null): string | null {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return null;
  }
}

export default function StandardCard({ std }: StandardCardProps) {
  const [showFull, setShowFull] = useState(false);
  const fullDesc = std.description || '';
  const truncated = fullDesc.length > DESC_TRUNC;
  const renderedDesc =
    truncated && !showFull
      ? `${fullDesc.slice(0, DESC_TRUNC).trim()}…`
      : fullDesc;
  const dateStr = formatChangeDate(std.last_change_date_time);

  return (
    <div
      className="flex flex-col bg-white border overflow-hidden h-full"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-2 text-[15px] font-bold tracking-wide"
        style={{
          backgroundColor: STANDARD_HEADER_BG,
          color: STANDARD_HEADER_FG,
        }}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="truncate">{std.schoology_standard}</span>
          <span className="flex items-center gap-1.5 text-[11px] font-medium opacity-90 truncate max-w-[180px]">
            {std.subject && <span className="truncate">{std.subject}</span>}
            {std.grades && std.grades.length > 0 && (
              <span className="rounded bg-white/20 px-1.5 py-0.5 text-[10px]">
                {std.grades.join(', ')}
              </span>
            )}
          </span>
        </div>
      </div>

      <div className="px-3 py-2 space-y-2 flex-1 flex flex-col">
        <div className="flex flex-wrap gap-1.5 text-[11px] text-neutral-700">
          {std.strand && (
            <span
              className="inline-flex items-center rounded px-1.5 py-0.5 font-medium"
              style={{
                backgroundColor: STRAND_CHIP_BG,
                color: STRAND_CHIP_FG,
              }}
            >
              {std.strand}
            </span>
          )}
          {std.cluster && (
            <span
              className="inline-flex items-center rounded px-1.5 py-0.5 font-medium truncate max-w-full"
              style={{
                backgroundColor: NEUTRAL_CHIP_BG,
                color: '#111827',
              }}
              title={std.cluster}
            >
              {std.cluster.length > 60
                ? `${std.cluster.slice(0, 60)}…`
                : std.cluster}
            </span>
          )}
          <ComplexityChip value={std.cognitive_complexity} />
        </div>

        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-[11px] text-neutral-700">
            <span
              className="inline-flex items-center rounded-full px-2 py-0.5 font-semibold"
              style={{ backgroundColor: NEUTRAL_CHIP_BG }}
            >
              {std.num_questions} Q
            </span>
            {std.num_assessments > 0 && (
              <span
                className="inline-flex items-center rounded-full px-2 py-0.5 font-semibold"
                style={{ backgroundColor: NEUTRAL_CHIP_BG }}
              >
                {std.num_assessments} assessment
                {std.num_assessments === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <div className="text-[20px] font-bold leading-none text-black">
            {std.grade_average_pct}
          </div>
        </div>

        <MiniBar grade={std.grade_average} />

        {fullDesc && (
          <div className="text-[11.5px] leading-snug text-neutral-700 flex-1">
            {renderedDesc}
            {truncated && (
              <button
                type="button"
                className="ml-1 text-primary underline-offset-2 hover:underline text-[11px] font-medium"
                onClick={() => setShowFull((s) => !s)}
              >
                {showFull ? 'Show less' : 'Show more'}
              </button>
            )}
          </div>
        )}

        {dateStr && (
          <div className="pt-1 border-t border-neutral-200 text-[10px] text-neutral-500">
            Adopted/Revised: {dateStr}
          </div>
        )}
      </div>
    </div>
  );
}
