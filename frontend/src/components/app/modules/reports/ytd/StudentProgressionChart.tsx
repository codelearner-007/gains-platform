'use client';

import {
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import type { YTDStudentScatter } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';

const COLOR_IMPROVING = '#16a34a';
const COLOR_DECLINING = '#dc2626';
const COLOR_STABLE = '#9ca3af';

interface Props {
  data: YTDStudentScatter[];
}

interface ChartPoint {
  x: number;
  y: number;
  z: number;
  user_name: string;
  delta: number;
  taken: number;
}

function colorFor(delta: number): string {
  if (delta >= 0.05) return COLOR_IMPROVING;
  if (delta <= -0.05) return COLOR_DECLINING;
  return COLOR_STABLE;
}

export default function StudentProgressionChart({ data }: Props) {
  const points: ChartPoint[] = data.map((s) => ({
    x: Math.round(s.first_avg * 1000) / 10,
    y: Math.round(s.latest_avg * 1000) / 10,
    z: Math.max(20, Math.min(120, s.assessments_taken * 30)),
    user_name: s.user_name,
    delta: s.delta,
    taken: s.assessments_taken,
  }));

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Student Progression: First vs Latest Attempt
      </div>
      <div style={{ height: 320 }} className="p-2">
        {points.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-neutral-500">
            No progression data available (need 2+ attempts per student)
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 24, left: 8, bottom: 36 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="x"
                name="First avg"
                tick={{ fontSize: 12, fill: '#000' }}
                domain={[0, 100]}
                tickFormatter={(v: number) => `${v}%`}
                label={{
                  value: 'First Attempt %',
                  position: 'insideBottom',
                  offset: -16,
                  fontSize: 11,
                }}
              />
              <YAxis
                type="number"
                dataKey="y"
                name="Latest avg"
                tick={{ fontSize: 12, fill: '#000' }}
                domain={[0, 100]}
                tickFormatter={(v: number) => `${v}%`}
                label={{
                  value: 'Latest Attempt %',
                  angle: -90,
                  position: 'insideLeft',
                  fontSize: 11,
                }}
              />
              <ZAxis type="number" dataKey="z" range={[20, 120]} />
              <ReferenceLine
                segment={[
                  { x: 0, y: 0 },
                  { x: 100, y: 100 },
                ]}
                stroke="#9ca3af"
                strokeDasharray="4 4"
              />
              <Tooltip content={<ScatterTooltip />} />
              <Scatter data={points} fillOpacity={0.7}>
                {points.map((p, i) => (
                  <Cell key={`scatter-${i}`} fill={colorFor(p.delta)} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3 px-3 py-1.5 text-[11px] text-black border-t border-[#E5E5E5]">
        <LegendDot color={COLOR_IMPROVING} label="Improving (≥+5%)" />
        <LegendDot color={COLOR_STABLE} label="Stable" />
        <LegendDot color={COLOR_DECLINING} label="Declining (≤-5%)" />
        <span className="text-neutral-600">
          Diagonal line = no change. Dot size = assessments taken.
        </span>
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: ChartPoint }[];
}

function ScatterTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  const sign = p.delta >= 0 ? '+' : '';
  return (
    <div className="bg-white border border-neutral-300 rounded shadow-md px-2 py-1 text-xs">
      <div className="font-semibold text-black">{p.user_name}</div>
      <div className="text-neutral-700">First: {p.x.toFixed(1)}%</div>
      <div className="text-neutral-700">Latest: {p.y.toFixed(1)}%</div>
      <div className="text-neutral-700">
        Delta: {sign}
        {(p.delta * 100).toFixed(1)}%
      </div>
      <div className="text-neutral-700">Assessments: {p.taken}</div>
    </div>
  );
}
