'use client';

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
import type { StandardSummaryStrandCount } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';

interface Props {
  rows: StandardSummaryStrandCount[];
}

interface ChartRow extends StandardSummaryStrandCount {
  fill: string;
}

interface TooltipPayload {
  payload: ChartRow;
}

interface TooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
}

function ChartTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const datum = payload[0].payload;
  return (
    <div className="bg-white border border-neutral-300 rounded shadow-md px-2 py-1 text-xs">
      <div className="font-semibold text-black">{datum.strand}</div>
      <div className="text-neutral-700">
        Standards: {datum.num_standards}
      </div>
      <div className="text-neutral-700">
        Questions: {datum.num_questions}
      </div>
      <div className="text-neutral-700">
        Avg: {formatPercent(datum.grade_average, 1)}
      </div>
    </div>
  );
}

export default function StandardsByStrandChart({ rows }: Props) {
  const data: ChartRow[] = rows
    .filter((r) => r.strand)
    .map((r) => ({ ...r, fill: performanceColor(r.grade_average) }));

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
        # of Standards by Strand
      </div>
      <div className="p-2" style={{ height: 280 }}>
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-neutral-500">
            No strand data available
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 4, right: 32, left: 4, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                allowDecimals={false}
                tick={{ fontSize: 11, fill: '#000' }}
              />
              <YAxis
                type="category"
                dataKey="strand"
                width={200}
                tick={{ fontSize: 12, fill: '#000' }}
                interval={0}
              />
              <Tooltip content={<ChartTooltip />} />
              <Bar
                dataKey="num_standards"
                isAnimationActive={false}
                name="# of Standards"
              >
                {data.map((row, i) => (
                  <Cell key={`cell-${i}-${row.strand}`} fill={row.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
