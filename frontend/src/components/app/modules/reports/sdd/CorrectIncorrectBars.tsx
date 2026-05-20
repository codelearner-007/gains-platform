'use client';

import { useMemo } from 'react';
import type { SddBandStandardRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  INCORRECT_GREY,
  LAYOUT_BORDER,
  PERF_GREEN,
  PERF_PINK,
  PERF_YELLOW,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';

const BAND_COLORS = {
  high: PERF_GREEN,
  mid: PERF_YELLOW,
  low: PERF_PINK,
};

interface BandPanelProps {
  title: string;
  rows: SddBandStandardRow[];
  correctColor: string;
  emptyMessage: string;
  selectedStandard?: string | null;
  onSelectStandard?: (cpalms_standard: string) => void;
}

/**
 * Each row is a label + a 100%-stacked bar (correct/incorrect) + the
 * percentage. Implemented in plain HTML/CSS rather than a Recharts BarChart
 * because:
 *
 * - Recharts' YAxis category labels need a fixed pixel width which clips
 *   long cPalms codes (e.g. ``MAFS.912.A-REI.2.4.a``) inside narrow
 *   3-column panels (~250 px wide each on a 1280 px viewport).
 * - When the panel holds 10+ standards the chart's computed row-height
 *   pushes the inner plot below the visible viewport and bars disappear
 *   entirely — pure CSS rows scroll inside a max-height container
 *   instead.
 *
 * The visual remains faithful to legacy PBIX / Schoology: stacked bar
 * with the band color filling the correct% and a grey remainder.
 */
function BandPanel({
  title,
  rows,
  correctColor,
  emptyMessage,
  selectedStandard,
  onSelectStandard,
}: BandPanelProps) {
  const sorted = useMemo(
    () => [...rows].sort((a, b) => b.grade_average - a.grade_average),
    [rows],
  );
  const isEmpty = sorted.length === 0;

  return (
    <div
      className="flex flex-col bg-white border h-full min-h-[260px]"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[12px] font-bold text-black border-b"
        style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      >
        {title}
      </div>
      {isEmpty ? (
        <div className="flex-1 flex items-center justify-center text-xs text-neutral-500 text-center px-2 py-6">
          {emptyMessage}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto max-h-[360px] px-2 py-2">
          <ul className="flex flex-col gap-1.5">
            {sorted.map((r, i) => (
              <BandRow
                key={`${r.cpalms_standard}-${i}`}
                row={r}
                correctColor={correctColor}
                selected={selectedStandard === r.cpalms_standard}
                dim={
                  !!selectedStandard &&
                  selectedStandard !== r.cpalms_standard
                }
                onSelect={onSelectStandard}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function BandRow({
  row,
  correctColor,
  selected = false,
  dim = false,
  onSelect,
}: {
  row: SddBandStandardRow;
  correctColor: string;
  selected?: boolean;
  dim?: boolean;
  onSelect?: (cpalms_standard: string) => void;
}) {
  const pct = Math.max(0, Math.min(1, row.grade_average));
  const pctText = formatPercent(pct, 1);
  return (
    <li
      className={`flex items-center gap-2 text-[11px] leading-tight rounded-sm px-1 -mx-1 transition-opacity ${onSelect ? 'cursor-pointer' : ''} ${selected ? 'ring-2 ring-neutral-800 ring-offset-1' : ''}`}
      style={{ opacity: dim ? 0.45 : 1 }}
      onClick={() => onSelect?.(row.cpalms_standard)}
      role={onSelect ? 'button' : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={(e) => {
        if (onSelect && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onSelect(row.cpalms_standard);
        }
      }}
    >
      <div
        className="shrink-0 truncate font-medium text-black"
        style={{ width: '46%' }}
        title={`${row.cpalms_standard} · ${row.strand} · ${row.num_questions} question${row.num_questions === 1 ? '' : 's'}`}
      >
        {row.cpalms_standard}
      </div>
      <div
        className="flex-1 relative h-4 rounded-sm overflow-hidden"
        style={{ backgroundColor: INCORRECT_GREY }}
        aria-label={`${row.cpalms_standard} ${pctText} correct`}
      >
        <div
          className="absolute inset-y-0 left-0"
          style={{ width: `${pct * 100}%`, backgroundColor: correctColor }}
        />
      </div>
      <div
        className="shrink-0 text-right font-semibold text-black tabular-nums"
        style={{ width: 44 }}
      >
        {pctText}
      </div>
    </li>
  );
}

interface PerformanceBandBarsProps {
  bandHigh: SddBandStandardRow[];
  bandMid: SddBandStandardRow[];
  bandLow: SddBandStandardRow[];
  selectedStandard?: string | null;
  onSelectStandard?: (cpalms_standard: string) => void;
}

export default function PerformanceBandBars({
  bandHigh,
  bandMid,
  bandLow,
  selectedStandard,
  onSelectStandard,
}: PerformanceBandBarsProps) {
  const shared = { selectedStandard, onSelectStandard };
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
      {/* All three panels share the legacy PBIX title; band membership is
          implicit via the correctColor (per data/_pbix_extract/50_sdd_spec.md:165-177). */}
      <BandPanel
        title="Correct and Incorrect % by Standards"
        rows={bandHigh}
        correctColor={BAND_COLORS.high}
        emptyMessage="No standards at target (≥80%)"
        {...shared}
      />
      <BandPanel
        title="Correct and Incorrect % by Standards"
        rows={bandMid}
        correctColor={BAND_COLORS.mid}
        emptyMessage="No standards approaching (70%–80%)"
        {...shared}
      />
      <BandPanel
        title="Correct and Incorrect % by Standards"
        rows={bandLow}
        correctColor={BAND_COLORS.low}
        emptyMessage="No standards need attention (<70%)"
        {...shared}
      />
    </div>
  );
}
