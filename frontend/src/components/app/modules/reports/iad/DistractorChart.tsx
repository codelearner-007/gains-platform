'use client';

import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { IadDistractorRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  INCORRECT_GREY,
  LAYOUT_BORDER,
  PERF_GREEN,
  PERF_PINK,
  PERF_YELLOW,
} from '@/lib/reports/colors';

interface Props {
  rows: IadDistractorRow[];
}

interface ChartRow {
  label: string;
  fullAnswer: string;
  count: number;
  share: number;
  isCorrect: boolean;
  fill: string;
}

const TRUNCATE_AT = 38;

function truncate(s: string, n: number): string {
  if (!s) return '(blank)';
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/**
 * Horizontal bar chart of # students per answer_submission. Replaces
 * the PBIX treemap (visual #14) with a more readable bar chart that
 * keeps the answer text legible and uses traffic-light colours for
 * the wrong answers (PERF_PINK = dominant wrong, PERF_YELLOW =
 * secondary wrong, INCORRECT_GREY = minor wrong).
 */
export default function DistractorChart({ rows }: Props) {
  const data = useMemo<ChartRow[]>(() => {
    const sorted = [...rows].sort(
      (a, b) => b.students_count - a.students_count,
    );
    const maxIncorrectShare = sorted
      .filter((r) => !r.is_correct)
      .reduce((m, r) => Math.max(m, r.share_of_attempts), 0);
    return sorted.map((r) => {
      let fill = PERF_GREEN;
      if (!r.is_correct) {
        if (maxIncorrectShare <= 0) fill = INCORRECT_GREY;
        else {
          const ratio = r.share_of_attempts / maxIncorrectShare;
          if (ratio >= 0.66) fill = PERF_PINK;
          else if (ratio >= 0.33) fill = PERF_YELLOW;
          else fill = INCORRECT_GREY;
        }
      }
      return {
        label: truncate(r.answer_submission, TRUNCATE_AT),
        fullAnswer: r.answer_submission || '(blank)',
        count: r.students_count,
        share: r.share_of_attempts,
        isCorrect: r.is_correct,
        fill,
      };
    });
  }, [rows]);

  // Match SDD's per-row sizing pattern: ~28px per row, min 220px.
  const height = data.length === 0 ? 220 : Math.max(220, data.length * 38 + 24);

  return (
    <div
      className="flex flex-col bg-white border h-full min-h-[260px]"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Answer Distribution
      </div>
      <div className="p-2 flex-1">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-neutral-500">
            No answer data.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 4, right: 28, left: 4, bottom: 4 }}
            >
              <XAxis
                type="number"
                allowDecimals={false}
                tick={{ fontSize: 10, fill: '#000' }}
              />
              <YAxis
                type="category"
                dataKey="label"
                tick={{ fontSize: 10, fill: '#000' }}
                width={250}
                interval={0}
              />
              <Tooltip
                contentStyle={{ fontSize: 12 }}
                formatter={(value: unknown, _name, item) => {
                  const row = (item?.payload ?? {}) as ChartRow;
                  const v = typeof value === 'number' ? value : Number(value);
                  return [
                    `${v} students (${(row.share * 100).toFixed(1)}%)`,
                    row.isCorrect ? 'Correct answer' : 'Incorrect answer',
                  ];
                }}
                labelFormatter={(_l, payload) =>
                  (payload?.[0]?.payload as ChartRow | undefined)?.fullAnswer ??
                  ''
                }
              />
              <Bar
                dataKey="count"
                isAnimationActive={false}
                label={{
                  position: 'right',
                  fontSize: 11,
                  fill: '#000',
                }}
              >
                {data.map((entry, idx) => (
                  <Cell key={`cell-${idx}`} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
