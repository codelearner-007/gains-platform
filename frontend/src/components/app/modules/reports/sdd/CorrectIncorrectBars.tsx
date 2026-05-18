'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { SddBandStandardRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  INCORRECT_GREY,
  LAYOUT_BORDER,
  PERF_GREEN,
  PERF_PINK,
  PERF_YELLOW,
} from '@/lib/reports/colors';

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
}

interface ChartRow {
  name: string;
  correct: number;
  incorrect: number;
  num_questions: number;
  grade_average: number;
}

function BandPanel({
  title,
  rows,
  correctColor,
  emptyMessage,
}: BandPanelProps) {
  const data: ChartRow[] = [...rows]
    .sort((a, b) => b.num_questions - a.num_questions)
    .map((r) => {
      const correct = Math.max(0, Math.min(100, r.grade_average * 100));
      return {
        name: r.cpalms_standard,
        correct: Math.round(correct * 10) / 10,
        incorrect: Math.round((100 - correct) * 10) / 10,
        num_questions: r.num_questions,
        grade_average: r.grade_average,
      };
    });
  const rowHeight = data.length === 0 ? 0 : Math.max(180, data.length * 28);

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
      <div className="p-2 flex-1">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-neutral-500 text-center px-2">
            {emptyMessage}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(rowHeight, 240)}>
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 6, right: 12, left: 6, bottom: 6 }}
              stackOffset="expand"
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                domain={[0, 1]}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                tick={{ fontSize: 11, fill: '#000' }}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 12, fill: '#000' }}
                width={180}
                interval={0}
              />
              <Tooltip
                formatter={(v, name, ctx) => {
                  const payload = ctx?.payload as ChartRow | undefined;
                  const pct =
                    typeof v === 'number' ? `${v.toFixed(1)}%` : String(v);
                  if (payload && name === 'Correct') {
                    return [`${pct} (${payload.num_questions} questions)`, name];
                  }
                  return [pct, name];
                }}
                contentStyle={{ fontSize: 12 }}
              />
              <Bar
                dataKey="correct"
                stackId="pct"
                fill={correctColor}
                name="Correct"
                isAnimationActive={false}
              />
              <Bar
                dataKey="incorrect"
                stackId="pct"
                fill={INCORRECT_GREY}
                name="Incorrect"
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

interface PerformanceBandBarsProps {
  bandHigh: SddBandStandardRow[];
  bandMid: SddBandStandardRow[];
  bandLow: SddBandStandardRow[];
}

export default function PerformanceBandBars({
  bandHigh,
  bandMid,
  bandLow,
}: PerformanceBandBarsProps) {
  // Stack panels on narrower viewports (≤ lg) so the YAxis labels for
  // cpalms standards (e.g. "MAFS.912.A-REI.2.4.a") aren't crammed into a
  // ~120 px column where they wrap vertically and overlap. Each panel
  // keeps its own scroll bounds.
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
      <BandPanel
        title="At Target (≥80%)"
        rows={bandHigh}
        correctColor={BAND_COLORS.high}
        emptyMessage="No standards at target"
      />
      <BandPanel
        title="Approaching (70%–80%)"
        rows={bandMid}
        correctColor={BAND_COLORS.mid}
        emptyMessage="No standards in approaching band"
      />
      <BandPanel
        title="Needs Attention (<70%)"
        rows={bandLow}
        correctColor={BAND_COLORS.low}
        emptyMessage="No standards need attention"
      />
    </div>
  );
}
