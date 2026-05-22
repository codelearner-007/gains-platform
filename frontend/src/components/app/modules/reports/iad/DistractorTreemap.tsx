'use client';

import { useMemo } from 'react';
import { ResponsiveContainer, Tooltip, Treemap } from 'recharts';
import type { IadDistractorRow } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import {
  normalizeSchoologyAssetUrl,
  sanitizeShortAnswer,
} from '@/lib/reports/format';
import { distractorFill, maxIncorrectShareOf } from './distractorFill';

// Pulls the first <https://…> URL token out of a Schoology answer string,
// matching the same `URL_IN_BRACKETS` regex format.ts uses to render
// image answers in HTML tables. Returns null for plain-text answers.
const URL_TOKEN = /<(https?:\/\/[^>\s]+)>/;
function extractAnswerImageUrl(raw: string): string | null {
  if (!raw) return null;
  const m = raw.match(URL_TOKEN);
  return m ? normalizeSchoologyAssetUrl(m[1]) : null;
}

interface Props {
  rows: IadDistractorRow[];
}

interface TreeRow {
  name: string;
  fullAnswer: string;
  imageUrl: string | null;
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
  imageUrl?: string | null;
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
    imageUrl,
  } = props;
  if (width <= 0 || height <= 0) return null;
  const canFitLabel = width > 40 && height > 26;
  const canFitImage = !!imageUrl && width > 50 && height > 50;
  const countLine = `${size} (${(share * 100).toFixed(0)}%)`;

  // Image answers (Schoology screenshots of math): render the picture
  // inside the cell so teachers can see the math, not the URL fragment.
  // Reserve the bottom strip of the cell for the count label.
  const padding = 6;
  const labelStripHeight = 18;
  const imgX = x + padding;
  const imgY = y + padding;
  const imgWidth = Math.max(0, width - padding * 2);
  const imgHeight = Math.max(0, height - padding * 2 - labelStripHeight);

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{ fill: fill ?? '#ccc', stroke: '#fff', strokeWidth: 2 }}
      />
      {canFitImage && (
        <image
          href={imageUrl!}
          x={imgX}
          y={imgY}
          width={imgWidth}
          height={imgHeight}
          preserveAspectRatio="xMidYMid meet"
        />
      )}
      {canFitLabel && !canFitImage && (
        <text x={x + padding} y={y + 16} fill="#000" fontSize={11} fontWeight={600}>
          {name.length > 24 ? `${name.slice(0, 23)}…` : name}
        </text>
      )}
      {canFitLabel && (
        <text
          x={x + padding}
          y={y + height - padding}
          fill="#000"
          fontSize={11}
          fontWeight={600}
        >
          {countLine}
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
        imageUrl: extractAnswerImageUrl(r.answer_submission),
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
