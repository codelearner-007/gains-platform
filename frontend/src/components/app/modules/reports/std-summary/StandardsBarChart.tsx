'use client';

import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { StandardSummaryRollupRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';
import ChartContainer from '../shared/ChartContainer';

interface Props {
  rows: StandardSummaryRollupRow[];
}

interface ChartRow {
  schoology_standard: string;
  grade_average: number;
  num_questions: number;
  num_assessments: number;
  strand: string;
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
      {datum.strand && (
        <div className="text-neutral-700">{datum.strand}</div>
      )}
      <div className="text-neutral-700">
        % Correct: {formatPercent(datum.grade_average, 1)}
      </div>
      <div className="text-neutral-700">
        Questions: {datum.num_questions}
      </div>
      <div className="text-neutral-700">
        Assessments: {datum.num_assessments}
      </div>
    </div>
  );
}

export default function StandardsBarChart({ rows }: Props) {
  const data = useMemo<ChartRow[]>(
    () =>
      rows
        .filter((r) => r.schoology_standard)
        .map((r) => ({
          schoology_standard: r.schoology_standard,
          grade_average: r.grade_average,
          num_questions: r.num_questions,
          num_assessments: r.num_assessments,
          strand: r.strand,
          fill: performanceColor(r.grade_average),
        }))
        .sort((a, b) => b.grade_average - a.grade_average),
    [rows],
  );

  const chartHeight = Math.max(280, Math.min(1100, 24 * data.length + 60));

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
        Correct % by Standards
      </div>
      <div className="p-2" style={{ height: chartHeight }}>
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-neutral-500">
            No standards match the current filters
          </div>
        ) : (
          <ChartContainer height="100%">
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
                width={170}
                tick={{ fontSize: 11, fill: '#000' }}
                interval={0}
              />
              <Tooltip content={<ChartTooltip />} />
              <Bar
                dataKey="grade_average"
                isAnimationActive={false}
                name="% Correct"
              >
                {data.map((row, i) => (
                  <Cell
                    key={`cell-${i}-${row.schoology_standard}`}
                    fill={row.fill}
                  />
                ))}
              </Bar>
            </BarChart>
          </ChartContainer>
        )}
      </div>
    </div>
  );
}
