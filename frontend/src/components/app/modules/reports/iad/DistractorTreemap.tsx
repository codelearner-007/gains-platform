'use client';

import { useMemo } from 'react';
import { ResponsiveContainer, Tooltip, Treemap } from 'recharts';
import type { IadDistractorRow } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import { sanitizeShortAnswer } from '@/lib/reports/format';
import { distractorFill, maxIncorrectShareOf } from './distractorFill';

interface Props {
  rows: IadDistractorRow[];
}

interface TreeRow {
  name: string;
  fullAnswer: string;
  size: number;
  share: number;
  isCorrect: boolean;
  fill: string;
  [key: string]: unknown;
}

interface TreemapContentProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  size?: number;
  share?: number;
  fill?: string;
}

function TreeCell(props: TreemapContentProps) {
  const {
    x = 0,
    y = 0,
    width = 0,
    height = 0,
    name = '',
    size = 0,
    share = 0,
    fill,
  } = props;
  if (width <= 0 || height <= 0) return null;
  const showLabel = width > 28 && height > 18;
  const showStats = width > 44 && height > 32;
  // 6.2 px/glyph at fontSize 11 is a safe upper bound for variable-width fonts.
  const maxChars = Math.max(2, Math.floor((width - 8) / 6.2));
  const label =
    name.length > maxChars ? `${name.slice(0, Math.max(1, maxChars - 1))}…` : name;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{ fill: fill ?? '#ccc', stroke: '#fff', strokeWidth: 2 }}
      />
      {showLabel && (
        <text
          x={x + 4}
          y={y + 14}
          fill="#0a0a0a"
          stroke="none"
          fontSize={11}
          fontWeight={600}
          fontFamily="system-ui, -apple-system, Segoe UI, sans-serif"
          paintOrder="fill"
          // pointerEvents disabled so text doesn't intercept tooltip hover.
          style={{ pointerEvents: 'none' }}
        >
          {label}
        </text>
      )}
      {showStats && (
        <text
          x={x + 4}
          y={y + 28}
          fill="#0a0a0a"
          stroke="none"
          fontSize={10}
          fontFamily="system-ui, -apple-system, Segoe UI, sans-serif"
          paintOrder="fill"
          style={{ pointerEvents: 'none' }}
        >
          {size} ({(share * 100).toFixed(0)}%)
        </text>
      )}
    </g>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: TreeRow }[];
}

function ChartTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-white border border-neutral-300 rounded shadow-md px-2 py-1 text-xs">
      <div className="font-semibold text-black">{d.fullAnswer}</div>
      <div className="text-neutral-700">
        {d.isCorrect ? 'Correct answer' : 'Incorrect answer'}
      </div>
      <div className="text-neutral-700">
        {d.size} students ({(d.share * 100).toFixed(1)}%)
      </div>
    </div>
  );
}

export default function DistractorTreemap({ rows }: Props) {
  const data = useMemo<TreeRow[]>(() => {
    const sorted = [...rows].sort(
      (a, b) => b.students_count - a.students_count,
    );
    const maxIncorrectShare = maxIncorrectShareOf(sorted);
    return sorted.map((r) => {
      const clean = sanitizeShortAnswer(r.answer_submission) || '(blank)';
      return {
        name: clean,
        fullAnswer: clean,
        size: r.students_count,
        share: r.share_of_attempts,
        isCorrect: r.is_correct,
        fill: distractorFill(r, maxIncorrectShare),
      };
    });
  }, [rows]);

  return (
    <div
      className="flex flex-col bg-white border h-full min-h-[300px]"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Answer Distribution
      </div>
      <div className="p-2 flex-1" style={{ minHeight: 280 }}>
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-neutral-500">
            No answer data.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <Treemap
              data={data}
              dataKey="size"
              nameKey="name"
              isAnimationActive={false}
              content={<TreeCell />}
              stroke="#fff"
            >
              <Tooltip content={<ChartTooltip />} />
            </Treemap>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
