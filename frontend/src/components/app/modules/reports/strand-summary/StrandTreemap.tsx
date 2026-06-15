'use client';

import { Treemap, Tooltip } from 'recharts';
import type { StrandSummaryRollupRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  PERF_PINK,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';
import ChartContainer from '../shared/ChartContainer';

interface Props {
  rows: StrandSummaryRollupRow[];
}

interface TreemapDatum {
  name: string;
  size: number;
  color: string;
  percentage: number;
  numStandards: number;
  numQuestions: number;
  [key: string]: string | number | boolean;
}

export default function StrandTreemap({ rows }: Props) {
  const data: TreemapDatum[] = rows
    .filter((s) => s.num_standards > 0)
    .map((s) => ({
      name: s.strand,
      size: Math.max(s.num_standards, 1),
      color: performanceColor(s.grade_average),
      percentage: s.grade_average,
      numStandards: s.num_standards,
      numQuestions: s.num_questions,
    }));

  return (
    <div
      className="flex flex-col bg-white border h-full"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black border-b flex items-center justify-between"
        style={{
          backgroundColor: HEADER_BAR_BG,
          borderColor: LAYOUT_BORDER,
        }}
      >
        <span># of Standards by Strand</span>
      </div>
      <div style={{ height: 280 }} className="p-2">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-neutral-500">
            No strand data available
          </div>
        ) : (
          <ChartContainer height="100%">
            <Treemap
              data={data}
              dataKey="size"
              stroke="#fff"
              isAnimationActive={false}
              content={<TreemapNode />}
            >
              <Tooltip content={<TreemapTooltip />} />
            </Treemap>
          </ChartContainer>
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
  color?: string;
  percentage?: number;
  numStandards?: number;
}

function TreemapNode(props: NodeProps) {
  const { x = 0, y = 0, width = 0, height = 0, name = '', color } = props;
  const fill = color || PERF_PINK;
  if (width <= 0 || height <= 0) return null;
  const lines = wrapLabel(name, Math.max(6, Math.floor(width / 7)), 3);
  const fontSize = width > 220 && height > 80 ? 14 : 12;
  const lineHeight = fontSize + 2;
  const totalHeight = lines.length * lineHeight;
  const startY = y + height / 2 - totalHeight / 2 + fontSize / 2;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{ fill, stroke: '#fff', strokeWidth: 2 }}
      />
      {width > 60 && height > 26 &&
        lines.map((line, i) => (
          <text
            key={i}
            x={x + width / 2}
            y={startY + i * lineHeight}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={fontSize}
            fill="#000"
            fontWeight={600}
            stroke="#fff"
            strokeWidth={3}
            paintOrder="stroke"
            strokeLinejoin="round"
          >
            {line}
          </text>
        ))}
    </g>
  );
}

function wrapLabel(s: string, maxChars: number, maxLines: number): string[] {
  if (!s) return [''];
  const words = s.split(/\s+/);
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    const candidate = cur ? `${cur} ${w}` : w;
    if (candidate.length <= maxChars || !cur) {
      cur = candidate;
    } else {
      lines.push(cur);
      cur = w;
      if (lines.length >= maxLines - 1) break;
    }
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) lines.length = maxLines;
  const lastIdx = lines.length - 1;
  const consumed = lines.slice(0, lastIdx + 1).join(' ').length;
  if (consumed < s.length) {
    lines[lastIdx] =
      lines[lastIdx].length > maxChars - 1
        ? `${lines[lastIdx].slice(0, Math.max(1, maxChars - 1))}…`
        : `${lines[lastIdx]}…`;
  }
  return lines;
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
      <div className="text-neutral-700">Standards: {datum.numStandards}</div>
      <div className="text-neutral-700">Questions: {datum.numQuestions}</div>
      <div className="text-neutral-700">
        Avg: {formatPercent(datum.percentage, 1)}
      </div>
    </div>
  );
}
