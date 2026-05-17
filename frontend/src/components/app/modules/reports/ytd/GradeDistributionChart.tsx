'use client';

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { YTDGradeDistribution } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  PERF_GREEN,
  PERF_PINK,
  PERF_YELLOW,
} from '@/lib/reports/colors';

interface Props {
  data: YTDGradeDistribution[];
}

interface ChartRow {
  date: string;
  high: number;
  mid: number;
  low: number;
  highCount: number;
  midCount: number;
  lowCount: number;
}

export default function GradeDistributionChart({ data }: Props) {
  const rows: ChartRow[] = data.map((d) => {
    const total = d.band_high + d.band_mid + d.band_low;
    const high = total > 0 ? (d.band_high / total) * 100 : 0;
    const mid = total > 0 ? (d.band_mid / total) * 100 : 0;
    const low = total > 0 ? (d.band_low / total) * 100 : 0;
    return {
      date: d.date,
      high: Math.round(high * 10) / 10,
      mid: Math.round(mid * 10) / 10,
      low: Math.round(low * 10) / 10,
      highCount: d.band_high,
      midCount: d.band_mid,
      lowCount: d.band_low,
    };
  });

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Grade Distribution Over Time
      </div>
      <div style={{ height: 280 }} className="p-2">
        {rows.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-neutral-500">
            No distribution data available
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={rows}
              margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12, fill: '#000' }}
                interval={0}
                angle={-30}
                textAnchor="end"
                height={50}
              />
              <YAxis
                tick={{ fontSize: 12, fill: '#000' }}
                domain={[0, 100]}
                tickFormatter={(v: number) => `${v}%`}
              />
              <Tooltip content={<DistTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area
                type="monotone"
                dataKey="low"
                name="Low (<70%)"
                stackId="1"
                stroke={PERF_PINK}
                fill={PERF_PINK}
              />
              <Area
                type="monotone"
                dataKey="mid"
                name="Mid (70-80%)"
                stackId="1"
                stroke={PERF_YELLOW}
                fill={PERF_YELLOW}
              />
              <Area
                type="monotone"
                dataKey="high"
                name="High (>=80%)"
                stackId="1"
                stroke={PERF_GREEN}
                fill={PERF_GREEN}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

interface TooltipPayload {
  active?: boolean;
  payload?: { payload: ChartRow }[];
  label?: string;
}

function DistTooltip({ active, payload, label }: TooltipPayload) {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0].payload;
  return (
    <div className="bg-white border border-neutral-300 rounded shadow-md px-2 py-1 text-xs">
      <div className="font-semibold text-black">{label}</div>
      <div className="text-neutral-700">
        High: {row.highCount} ({row.high.toFixed(1)}%)
      </div>
      <div className="text-neutral-700">
        Mid: {row.midCount} ({row.mid.toFixed(1)}%)
      </div>
      <div className="text-neutral-700">
        Low: {row.lowCount} ({row.low.toFixed(1)}%)
      </div>
    </div>
  );
}
