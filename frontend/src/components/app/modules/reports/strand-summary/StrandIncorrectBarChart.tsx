'use client';

import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { StrandSummaryStandardRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';

interface Props {
  rows: StrandSummaryStandardRow[];
}

interface ChartRow {
  schoology_standard: string;
  incorrect_pct: number;
  num_questions: number;
  num_assessments: number;
  grade_average: number;
  fill: string;
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: ChartRow }[];
}

function ChartTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const datum = payload[0].payload;
  return (
    <div className="bg-white border border-neutral-300 rounded shadow-md px-2 py-1 text-xs">
      <div className="font-semibold text-black">{datum.schoology_standard}</div>
      <div className="text-neutral-700">
        Incorrect %: {formatPercent(datum.incorrect_pct, 1)}
      </div>
      <div className="text-neutral-700">
        Correct %: {formatPercent(datum.grade_average, 1)}
      </div>
      <div className="text-neutral-700">
        Questions: {datum.num_questions}
      </div>
    </div>
  );
}

export default function StrandIncorrectBarChart({ rows }: Props) {
  const data = useMemo<ChartRow[]>(
    () =>
      rows
        .filter((r) => r.schoology_standard)
        .map((r) => ({
          schoology_standard: r.schoology_standard,
          incorrect_pct: Math.max(0, 1 - r.grade_average),
          num_questions: r.num_questions,
          num_assessments: r.num_assessments,
          grade_average: r.grade_average,
          fill: performanceColor(r.grade_average),
        }))
        .sort((a, b) => b.incorrect_pct - a.incorrect_pct),
    [rows],
  );

  const chartHeight = Math.max(220, Math.min(720, 24 * data.length + 60));

  return (
    <div
      className="flex flex-col bg-white border h-full"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[13px] font-bold text-black border-b"
        style={{
          backgroundColor: HEADER_BAR_BG,
          borderColor: LAYOUT_BORDER,
        }}
      >
        Incorrect % per Standard
      </div>
      <div className="p-2" style={{ height: chartHeight }}>
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-neutral-500">
            No standards in this strand
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 4, right: 40, left: 4, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                domain={[0, 1]}
                tickFormatter={(v: number) => formatPercent(v, 0)}
                tick={{ fontSize: 11, fill: '#000' }}
              />
              <YAxis
                type="category"
                dataKey="schoology_standard"
                width={160}
                tick={{ fontSize: 11, fill: '#000' }}
                interval={0}
              />
              <Tooltip content={<ChartTooltip />} />
              <Bar
                dataKey="incorrect_pct"
                isAnimationActive={false}
                name="Incorrect %"
              >
                {data.map((row, i) => (
                  <Cell
                    key={`cell-${i}-${row.schoology_standard}`}
                    fill={row.fill}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
