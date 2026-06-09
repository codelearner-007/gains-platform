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
import type { StrandSummaryStandardRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';
import ChartContainer from '../shared/ChartContainer';

interface Props {
  rows: StrandSummaryStandardRow[];
}

interface ChartRow {
  schoology_standard: string;
  grade_average: number;
  num_questions: number;
  num_assessments: number;
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
        Correct %: {formatPercent(datum.grade_average, 1)}
      </div>
      <div className="text-neutral-700">
        Questions: {datum.num_questions}
      </div>
    </div>
  );
}

export default function StrandCorrectColumnChart({ rows }: Props) {
  const data = useMemo<ChartRow[]>(
    () =>
      rows
        .filter((r) => r.schoology_standard)
        .map((r) => ({
          schoology_standard: r.schoology_standard,
          grade_average: r.grade_average,
          num_questions: r.num_questions,
          num_assessments: r.num_assessments,
          fill: performanceColor(r.grade_average),
        }))
        .sort((a, b) => b.grade_average - a.grade_average),
    [rows],
  );

  const tickAngle = data.length > 6 ? -35 : 0;

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
        Correct % per Standard
      </div>
      <div className="p-2" style={{ height: 320 }}>
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-neutral-500">
            No standards in this strand
          </div>
        ) : (
          <ChartContainer height="100%">
            <BarChart
              data={data}
              margin={{ top: 8, right: 16, left: 8, bottom: 60 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="schoology_standard"
                tick={{ fontSize: 10, fill: '#000' }}
                interval={0}
                angle={tickAngle}
                textAnchor={tickAngle === 0 ? 'middle' : 'end'}
                height={tickAngle === 0 ? 30 : 60}
              />
              <YAxis
                domain={[0, 1]}
                tickFormatter={(v: number) => formatPercent(v, 0)}
                tick={{ fontSize: 11, fill: '#000' }}
              />
              <Tooltip content={<ChartTooltip />} />
              <Bar
                dataKey="grade_average"
                isAnimationActive={false}
                name="Correct %"
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
