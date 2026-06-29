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
import OpenInReportPopover from '@/components/app/modules/reports/shared/OpenInReportPopover';

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
  // Multi-select: every active standard code. Clicking a bar toggles membership.
  selectedStandards?: Set<string>;
  onSelectStandard?: (schoology_standard: string) => void;
  /** When set, each bar shows an "open in QRA filtered by this standard" link. */
  itemId?: string;
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
  selectedStandards,
  onSelectStandard,
  itemId,
}: BandPanelProps) {
  const hasSelection = !!selectedStandards && selectedStandards.size > 0;
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
        <div className="flex-1 overflow-y-auto max-h-[360px] print:max-h-none print:overflow-visible px-2 py-2">
          <ul className="flex flex-col gap-1.5">
            {sorted.map((r, i) => (
              <BandRow
                key={`${r.schoology_standard}-${i}`}
                row={r}
                correctColor={correctColor}
                selected={!!selectedStandards?.has(r.schoology_standard)}
                dim={
                  hasSelection &&
                  !selectedStandards?.has(r.schoology_standard)
                }
                onSelect={onSelectStandard}
                itemId={itemId}
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
  itemId,
}: {
  row: SddBandStandardRow;
  correctColor: string;
  selected?: boolean;
  dim?: boolean;
  onSelect?: (schoology_standard: string) => void;
  itemId?: string;
}) {
  const pct = Math.max(0, Math.min(1, row.grade_average));
  const pctText = formatPercent(pct, 1);
  return (
    <li
      className={`flex items-center gap-2 text-[11px] leading-tight rounded-sm px-1 -mx-1 transition-opacity ${onSelect ? 'cursor-pointer' : ''} ${selected ? 'ring-2 ring-neutral-800 ring-offset-1' : ''}`}
      style={{ opacity: dim ? 0.45 : 1 }}
      onClick={() => onSelect?.(row.schoology_standard)}
      role={onSelect ? 'button' : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={(e) => {
        if (onSelect && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onSelect(row.schoology_standard);
        }
      }}
    >
      <div
        className="shrink-0 truncate font-medium text-black"
        style={{ width: '46%' }}
        title={`${row.schoology_standard} · ${row.strand} · ${row.num_questions} question${row.num_questions === 1 ? '' : 's'}`}
      >
        {row.schoology_standard}
      </div>
      <div
        className="flex-1 relative h-4 rounded-sm overflow-hidden"
        style={{ backgroundColor: INCORRECT_GREY }}
        aria-label={`${row.schoology_standard} ${pctText} correct`}
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
      {itemId ? (
        <OpenInReportPopover
          itemId={itemId}
          standard={row.schoology_standard}
          label={row.schoology_standard}
        />
      ) : null}
    </li>
  );
}

interface PerformanceBandBarsProps {
  bandHigh: SddBandStandardRow[];
  bandMid: SddBandStandardRow[];
  bandLow: SddBandStandardRow[];
  // Multi-select: every active standard code. Clicking a bar toggles membership.
  selectedStandards?: string[];
  onSelectStandard?: (schoology_standard: string) => void;
  /** When set, each bar shows an "open in QRA filtered by this standard" link. */
  itemId?: string;
}

export default function PerformanceBandBars({
  bandHigh,
  bandMid,
  bandLow,
  selectedStandards,
  onSelectStandard,
  itemId,
}: PerformanceBandBarsProps) {
  const selectedSet = useMemo(
    () => new Set(selectedStandards ?? []),
    [selectedStandards],
  );
  const shared = { selectedStandards: selectedSet, onSelectStandard, itemId };
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
      <BandPanel
        title="At Target (≥80%)"
        rows={bandHigh}
        correctColor={BAND_COLORS.high}
        emptyMessage="No standards at target (≥80%)"
        {...shared}
      />
      <BandPanel
        title="Approaching (70%–80%)"
        rows={bandMid}
        correctColor={BAND_COLORS.mid}
        emptyMessage="No standards approaching (70%–80%)"
        {...shared}
      />
      <BandPanel
        title="Needs Attention (<70%)"
        rows={bandLow}
        correctColor={BAND_COLORS.low}
        emptyMessage="No standards need attention (<70%)"
        {...shared}
      />
    </div>
  );
}
