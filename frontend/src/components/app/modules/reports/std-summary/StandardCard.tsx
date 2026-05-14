'use client';

import { useState } from 'react';
import type { StandardSummaryRollupRow } from '@/lib/reports/types';
import {
  INCORRECT_GREY,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';

const STANDARD_CARD_HEADER_BG = '#0E1A77'; // PBIX deep navy header (spec §8)
const DESC_TRUNC = 240;

interface StandardCardProps {
  std: StandardSummaryRollupRow;
}

function ComplexityChip({ value }: { value: string }) {
  if (!value) return null;
  const v = value.toLowerCase();
  let bg = '#E5E5E5';
  let fg = '#000';
  if (v.includes('high')) {
    bg = '#FECACA';
    fg = '#7F1D1D';
  } else if (v.includes('moderate') || v.includes('mid')) {
    bg = '#FEF3C7';
    fg = '#78350F';
  } else if (v.includes('low')) {
    bg = '#DCFCE7';
    fg = '#14532D';
  }
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
          backgroundColor: STANDARD_CARD_HEADER_BG,
          color: '#FFFFFF',
        }}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="truncate">{std.cpalms_standard}</span>
          {std.subject && (
            <span className="text-[11px] font-medium opacity-90 truncate max-w-[130px]">
              {std.subject}
            </span>
          )}
        </div>
      </div>

      <div className="px-3 py-2 space-y-2 flex-1 flex flex-col">
        <div className="flex flex-wrap gap-1.5 text-[11px] text-neutral-700">
          {std.strand && (
            <span
              className="inline-flex items-center rounded px-1.5 py-0.5 font-medium"
              style={{
                backgroundColor: '#E0E7FF',
                color: '#1E1B4B',
              }}
            >
              {std.strand}
            </span>
          )}
          {std.cluster && (
            <span
              className="inline-flex items-center rounded px-1.5 py-0.5 font-medium truncate max-w-full"
              style={{
                backgroundColor: '#F3F4F6',
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
              style={{ backgroundColor: '#F3F4F6' }}
            >
              {std.num_questions} Q
            </span>
            {std.num_assessments > 0 && (
              <span
                className="inline-flex items-center rounded-full px-2 py-0.5 font-semibold"
                style={{ backgroundColor: '#F3F4F6' }}
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
