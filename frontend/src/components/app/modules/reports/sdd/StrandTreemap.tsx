'use client';

import { useMemo } from 'react';
import { Treemap, Tooltip } from 'recharts';
import type { SddStrandRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  PERF_PINK,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';
import ChartContainer from '../shared/ChartContainer';

interface StrandTreemapProps {
  strands: SddStrandRow[];
  selectedStrand?: string | null;
  onSelectStrand?: (strand: string) => void;
}

interface TreemapDatum {
  name: string;
  size: number;
  color: string;
  percentage: number;
  numStandards: number;
  [key: string]: string | number;
}

export default function StrandTreemap({
  strands,
  selectedStrand,
  onSelectStrand,
}: StrandTreemapProps) {
  // Memoise — Recharts re-layouts when the data reference changes.
  const data = useMemo<TreemapDatum[]>(
    () =>
      strands
        .filter((s) => s.num_questions > 0)
        .map((s) => ({
          name: s.strand,
          size: s.num_questions,
          color: performanceColor(s.grade_average ?? 0),
          percentage: s.grade_average ?? 0,
          numStandards: s.num_standards,
        })),
    [strands],
  );

  const handleNodeClick = (node: unknown) => {
    // Recharts spreads the leaf datum directly onto the click payload.
    const n = node as Partial<TreemapDatum> | undefined;
    if (n?.name && onSelectStrand) onSelectStrand(n.name);
  };

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
          <ChartContainer height="100%">
            <Treemap
              data={data}
              dataKey="size"
              stroke="#fff"
              isAnimationActive={false}
              content={
                <TreemapNode
                  onSelect={onSelectStrand}
                  selectedStrand={selectedStrand ?? null}
                />
              }
              onClick={handleNodeClick}
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
  // Recharts spreads the original data row's fields directly onto the
  // leaf node props (see Treemap.js line 650: `_objectSpread(..., node)`).
  // So our `color` field arrives at this level, not under `payload`.
  color?: string;
  percentage?: number;
  /** Injected by parent — used for the selection ring. */
  selectedStrand?: string | null;
  /** Injected by parent — clicking the tile cross-filters the dashboard. */
  onSelect?: (strand: string) => void;
}

function TreemapNode(props: NodeProps) {
  const {
    x = 0,
    y = 0,
    width = 0,
    height = 0,
    name,
    color,
    percentage,
    selectedStrand,
    onSelect,
  } = props;
  const fill = color || PERF_PINK;
  if (width <= 0 || height <= 0) return null;
  const isSelected = !!name && selectedStrand === name;
  // Wrap long labels onto multiple lines so multi-word strands ("Algebra:
  // Reasoning with Equations & Inequalities") remain legible on narrow tiles.
  const lines = wrapLabel(name ?? '', Math.max(6, Math.floor(width / 7)), 3);
  const labelFontSize = width > 220 && height > 80 ? 14 : 12;
  const pctFontSize = width > 220 && height > 80 ? 16 : 13;
  const lineHeight = labelFontSize + 2;
  // Show the % below the label when the tile is at least ~50px tall
  // (matches Schoology — "Other 73.0%" rendered inside the tile).
  const showPct = typeof percentage === 'number' && width > 60 && height > 50;
  const labelBlockHeight = lines.length * lineHeight;
  const totalHeight = showPct
    ? labelBlockHeight + pctFontSize + 6
    : labelBlockHeight;
  const startY = y + height / 2 - totalHeight / 2 + labelFontSize / 2;
  const handleTileClick = () => {
    if (name && onSelect) onSelect(name);
  };
  return (
    <g
      onClick={handleTileClick}
      style={{ cursor: onSelect ? 'pointer' : 'default' }}
    >
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{
          fill,
          stroke: isSelected ? '#1f2937' : '#fff',
          strokeWidth: isSelected ? 3 : 2,
          opacity: selectedStrand && !isSelected ? 0.45 : 1,
        }}
      />
      {width > 60 && height > 26 &&
        lines.map((line, i) => (
          <text
            key={i}
            x={x + width / 2}
            y={startY + i * lineHeight}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={labelFontSize}
            fill="#000"
            fontWeight={600}
            // White halo guarantees legibility on every band color.
            stroke="#fff"
            strokeWidth={3}
            paintOrder="stroke"
            strokeLinejoin="round"
          >
            {line}
          </text>
        ))}
      {showPct && (
        <text
          x={x + width / 2}
          y={startY + labelBlockHeight + pctFontSize}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={pctFontSize}
          fill="#000"
          fontWeight={700}
          stroke="#fff"
          strokeWidth={3}
          paintOrder="stroke"
          strokeLinejoin="round"
        >
          {formatPercent(percentage as number, 1)}
        </text>
      )}
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
  // Truncate the final line if the source kept going past our budget.
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
      <div className="text-neutral-700">Questions: {datum.size}</div>
      <div className="text-neutral-700">Standards: {datum.numStandards}</div>
      <div className="text-neutral-700">
        Avg: {formatPercent(datum.percentage, 1)}
      </div>
    </div>
  );
}
