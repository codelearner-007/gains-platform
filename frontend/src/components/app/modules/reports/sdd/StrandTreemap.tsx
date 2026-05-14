'use client';

import { ResponsiveContainer, Treemap, Tooltip } from 'recharts';
import type { SddStrandRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  PERF_PINK,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';

interface StrandTreemapProps {
  strands: SddStrandRow[];
}

interface TreemapDatum {
  name: string;
  size: number;
  color: string;
  percentage: number;
  numStandards: number;
  [key: string]: string | number;
}

export default function StrandTreemap({ strands }: StrandTreemapProps) {
  const data: TreemapDatum[] = strands
    .filter((s) => s.num_questions > 0)
    .map((s) => ({
      name: s.strand,
      size: s.num_questions,
      color: performanceColor(s.grade_average),
      percentage: s.grade_average,
      numStandards: s.num_standards,
    }));

  return (
    <div
      className="flex flex-col bg-white border h-full"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black border-b"
        style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      >
        # of Standards by Strand
      </div>
      <div style={{ height: 250 }} className="p-2">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-neutral-500">
            No strand data available
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <Treemap
              data={data}
              dataKey="size"
              stroke="#fff"
              isAnimationActive={false}
              content={<TreemapNode />}
            >
              <Tooltip content={<TreemapTooltip />} />
            </Treemap>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

interface NodeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  // Recharts spreads the original data row's fields directly onto the
  // leaf node props (see Treemap.js line 650: `_objectSpread(..., node)`).
  // So our `color` field arrives at this level, not under `payload`.
  color?: string;
  percentage?: number;
}

function TreemapNode(props: NodeProps) {
  const { x = 0, y = 0, width = 0, height = 0, name, color } = props;
  const fill = color || PERF_PINK;
  if (width <= 0 || height <= 0) return null;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{ fill, stroke: '#fff', strokeWidth: 2 }}
      />
      {width > 60 && height > 24 && (
        <text
          x={x + width / 2}
          y={y + height / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={12}
          fill="#000"
          fontWeight={600}
        >
          {truncate(name ?? '', Math.max(6, Math.floor(width / 8)))}
        </text>
      )}
    </g>
  );
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return `${s.slice(0, Math.max(1, max - 1))}…`;
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: TreemapDatum }[];
}

function TreemapTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const datum = payload[0].payload;
  return (
    <div className="bg-white border border-neutral-300 rounded shadow-md px-2 py-1 text-xs">
      <div className="font-semibold text-black">{datum.name}</div>
      <div className="text-neutral-700">Questions: {datum.size}</div>
      <div className="text-neutral-700">Standards: {datum.numStandards}</div>
      <div className="text-neutral-700">
        Avg: {formatPercent(datum.percentage, 1)}
      </div>
    </div>
  );
}
