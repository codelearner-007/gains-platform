'use client';

import { useMemo } from 'react';
import { Check, X } from 'lucide-react';
import type { IadDistractorRow } from '@/lib/reports/types';
import {
  EMPTY_TABLE_FG,
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  STATUS_CORRECT_FG,
  STATUS_INCORRECT_FG,
} from '@/lib/reports/colors';
import { distractorFill, maxIncorrectShareOf } from './distractorFill';
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
export default function DistractorTable({ rows }: Props) {
  const sorted = useMemo(
    () => [...rows].sort((a, b) => b.students_count - a.students_count),
    [rows],
  );
  const maxIncorrectShare = useMemo(
    () => maxIncorrectShareOf(sorted),
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
              const fill = distractorFill(r, maxIncorrectShare);
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
                        style={{ color: STATUS_CORRECT_FG }}
                        aria-label="correct"
                      />
                    ) : (
                      <X
                        className="inline h-4 w-4"
                        style={{ color: STATUS_INCORRECT_FG }}
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
                    color: EMPTY_TABLE_FG,
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
