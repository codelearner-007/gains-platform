'use client';

import { useMemo } from 'react';
import { Check, X } from 'lucide-react';
import type { IadDistractorRow } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  INCORRECT_GREY,
  LAYOUT_BORDER,
  PERF_GREEN,
  PERF_PINK,
  PERF_YELLOW,
} from '@/lib/reports/colors';
import {
  tableCellStyle as cellBase,
  tableHeaderStyle as headerStyle,
} from '../shared/tableStyles';

interface Props {
  rows: IadDistractorRow[];
}

/**
 * Distractor frequency table — replicates the pivotTable (visual #3)
 * on the PBIX IAD page. Shows every distinct answer_submission with
 * the # of students who chose it, % share, status (correct/incorrect),
 * and an inline % bar (PERF colour-graded for wrong choices).
 */

function fillForRow(row: IadDistractorRow, maxIncorrectShare: number): string {
  if (row.is_correct) return PERF_GREEN;
  // Color-grade incorrect choices by relative dominance among wrong answers.
  if (maxIncorrectShare <= 0) return INCORRECT_GREY;
  const ratio = row.share_of_attempts / maxIncorrectShare;
  if (ratio >= 0.66) return PERF_PINK;
  if (ratio >= 0.33) return PERF_YELLOW;
  return INCORRECT_GREY;
}

export default function DistractorTable({ rows }: Props) {
  const sorted = useMemo(
    () => [...rows].sort((a, b) => b.students_count - a.students_count),
    [rows],
  );
  const maxIncorrectShare = useMemo(
    () =>
      sorted
        .filter((r) => !r.is_correct)
        .reduce((m, r) => Math.max(m, r.share_of_attempts), 0),
    [sorted],
  );
  const maxShare = useMemo(
    () => sorted.reduce((m, r) => Math.max(m, r.share_of_attempts), 0),
    [sorted],
  );

  return (
    <div
      className="flex flex-col bg-white border h-full"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Distractor Breakdown
      </div>
      <div className="w-full overflow-auto">
        <table
          style={{
            borderCollapse: 'collapse',
            width: '100%',
            tableLayout: 'fixed',
          }}
        >
          <colgroup>
            <col style={{ width: '8%' }} />
            <col style={{ width: '46%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '11%' }} />
            <col style={{ width: '23%' }} />
          </colgroup>
          <thead>
            <tr>
              <th style={{ ...headerStyle, textAlign: 'center' }}>Status</th>
              <th style={headerStyle}>Answer</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>
                # Students
              </th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>%</th>
              <th style={headerStyle}>Distribution</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, idx) => {
              const fill = fillForRow(r, maxIncorrectShare);
              const widthPct =
                maxShare > 0 ? (r.share_of_attempts / maxShare) * 100 : 0;
              return (
                <tr
                  key={`${r.answer_submission}-${idx}`}
                  className="hover:bg-neutral-50"
                >
                  <td style={{ ...cellBase, textAlign: 'center' }}>
                    {r.is_correct ? (
                      <Check
                        className="inline h-4 w-4"
                        style={{ color: '#15803d' }}
                        aria-label="correct"
                      />
                    ) : (
                      <X
                        className="inline h-4 w-4"
                        style={{ color: '#b91c1c' }}
                        aria-label="incorrect"
                      />
                    )}
                  </td>
                  <td
                    style={{
                      ...cellBase,
                      whiteSpace: 'normal',
                      wordBreak: 'break-word',
                    }}
                  >
                    {r.answer_submission || '(blank)'}
                  </td>
                  <td
                    style={{
                      ...cellBase,
                      textAlign: 'right',
                      fontWeight: 600,
                    }}
                  >
                    {r.students_count}
                  </td>
                  <td
                    style={{
                      ...cellBase,
                      textAlign: 'right',
                      fontWeight: 600,
                    }}
                  >
                    {r.share_pct}
                  </td>
                  <td style={cellBase}>
                    <div
                      className="h-3 rounded-sm"
                      style={{
                        width: `${widthPct}%`,
                        backgroundColor: fill,
                        minWidth: 2,
                      }}
                      title={`${r.students_count} (${r.share_pct})`}
                    />
                  </td>
                </tr>
              );
            })}
            {sorted.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  style={{
                    ...cellBase,
                    textAlign: 'center',
                    color: '#6b7280',
                  }}
                >
                  No answer-choice data for this question.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
