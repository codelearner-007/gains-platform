'use client';

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { YTDTimelinePoint } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';

const OVERALL_COLOR = '#1e40af';
const SUBJECT_PALETTE = [
  '#dc2626',
  '#16a34a',
  '#ea580c',
  '#9333ea',
  '#0891b2',
  '#ca8a04',
  '#db2777',
];

interface OverallTrendChartProps {
  timeline: YTDTimelinePoint[];
}

interface ChartRow {
  date: string;
  overall: number;
  [subject: string]: number | string;
}

export default function OverallTrendChart({
  timeline,
}: OverallTrendChartProps) {
  const subjectSet = new Set<string>();
  for (const point of timeline) {
    for (const s of Object.keys(point.per_subject)) subjectSet.add(s);
  }
  const subjects = Array.from(subjectSet).sort();

  const data: ChartRow[] = timeline.map((p) => {
    const row: ChartRow = {
      date: p.date,
      overall: Math.round(p.overall_avg * 1000) / 10,
    };
    for (const s of subjects) {
      const v = p.per_subject[s];
      if (typeof v === 'number')
        row[s] = Math.round(v * 1000) / 10;
    }
    return row;
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
        Overall Trend Over Time
      </div>
      <div style={{ height: 280 }} className="p-2">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-neutral-500">
            No timeline data available
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
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
              <Tooltip
                contentStyle={{ fontSize: 12 }}
                formatter={(v) =>
                  typeof v === 'number'
                    ? `${v.toFixed(1)}%`
                    : String(v)
                }
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="overall"
                name="Overall"
                stroke={OVERALL_COLOR}
                strokeWidth={3}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
              />
              {subjects.map((s, i) => (
                <Line
                  key={s}
                  type="monotone"
                  dataKey={s}
                  name={s}
                  stroke={SUBJECT_PALETTE[i % SUBJECT_PALETTE.length]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
