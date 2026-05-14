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
import type { StrandSummaryBandRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  INCORRECT_GREY,
  LAYOUT_BORDER,
  PERF_GREEN,
  PERF_PINK,
  PERF_YELLOW,
} from '@/lib/reports/colors';

interface BandPanelProps {
  title: string;
  rows: StrandSummaryBandRow[];
  correctColor: string;
  emptyMessage: string;
}

interface ChartRow {
  name: string;
  correct: number;
  incorrect: number;
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
        name: r.strand,
        correct: Math.round(correct * 10) / 10,
        incorrect: Math.round((100 - correct) * 10) / 10,
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
        style={{
          backgroundColor: HEADER_BAR_BG,
          borderColor: LAYOUT_BORDER,
        }}
      >
        {title}
      </div>
      <div className="p-2 flex-1">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-neutral-500 text-center px-2">
            {emptyMessage}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(rowHeight, 220)}>
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 4, right: 8, left: 4, bottom: 4 }}
              stackOffset="expand"
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                domain={[0, 1]}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                tick={{ fontSize: 10, fill: '#000' }}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 10, fill: '#000' }}
                width={140}
                interval={0}
              />
              <Tooltip
                formatter={(v) =>
                  typeof v === 'number' ? `${v.toFixed(1)}%` : String(v)
                }
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

interface Props {
  bandHigh: StrandSummaryBandRow[];
  bandMid: StrandSummaryBandRow[];
  bandLow: StrandSummaryBandRow[];
}

export default function BandBars({ bandHigh, bandMid, bandLow }: Props) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 h-full">
      <BandPanel
        title="At Target (≥80%)"
        rows={bandHigh}
        correctColor={PERF_GREEN}
        emptyMessage="No strands at target"
      />
      <BandPanel
        title="Approaching (70%–80%)"
        rows={bandMid}
        correctColor={PERF_YELLOW}
        emptyMessage="No strands in approaching band"
      />
      <BandPanel
        title="Needs Attention (<70%)"
        rows={bandLow}
        correctColor={PERF_PINK}
        emptyMessage="No strands need attention"
      />
    </div>
  );
}
