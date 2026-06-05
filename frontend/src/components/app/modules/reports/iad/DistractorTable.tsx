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
import { distractorFill } from './distractorFill';
import {
  tableCellStyle as cellBase,
  tableHeaderStyle as headerStyle,
} from '../shared/tableStyles';
import { formatAnswerHtml } from '@/lib/reports/format';
import RichReportHtml from '../shared/RichReportHtml';
import { SortableHeader, useTableSort } from '@/lib/reports/useTableSort';

interface Props {
  rows: IadDistractorRow[];
}

type DistractorSortKey =
  | 'is_correct'
  | 'answer_submission'
  | 'students_count'
  | 'share_of_attempts';

const DISTRACTOR_SORT_ACCESSORS: Record<
  DistractorSortKey,
  (r: IadDistractorRow) => string | number
> = {
  is_correct: (r) => (r.is_correct ? 1 : 0),
  answer_submission: (r) => (r.answer_submission || '').toLowerCase(),
  students_count: (r) => r.students_count,
  share_of_attempts: (r) => r.share_of_attempts,
};

const DISTRACTOR_INITIAL_DIRECTIONS: Partial<
  Record<DistractorSortKey, 'asc' | 'desc'>
> = {
  students_count: 'desc',
  share_of_attempts: 'desc',
  is_correct: 'desc',
};

/**
 * Distractor frequency table — replicates the "Answer Distribution"
 * tableEx (visual #4) on the PBIX IAD page. Shows every distinct
 * answer_submission with the # of students who chose it, % share,
 * status (correct/incorrect), and an inline % bar. The bar uses a
 * neutral fill (no traffic-light encoding) to match legacy, which sets
 * no per-cell color rule on this table (01_legacy_logic.md §4.3).
 */
export default function DistractorTable({ rows }: Props) {
  const { sortedRows: sorted, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<IadDistractorRow, DistractorSortKey>({
      rows,
      accessors: DISTRACTOR_SORT_ACCESSORS,
      defaultColumn: 'students_count',
      defaultDirection: 'desc',
      initialDirections: DISTRACTOR_INITIAL_DIRECTIONS,
    });
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
              <th style={{ ...headerStyle, textAlign: 'center' }}>
                <SortableHeader
                  column="is_correct"
                  label="Status"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="center"
                />
              </th>
              <th style={headerStyle}>
                <SortableHeader
                  column="answer_submission"
                  label="Answer"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>
                <SortableHeader
                  column="students_count"
                  label="# Students"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="right"
                />
              </th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>
                <SortableHeader
                  column="share_of_attempts"
                  label="%"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="right"
                />
              </th>
              <th style={headerStyle}>Distribution</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, idx) => {
              const fill = distractorFill(r);
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
                    {r.answer_submission ? (
                      <RichReportHtml
                        className="pilot-answer-html"
                        html={formatAnswerHtml(r.answer_submission, 'answer choice')}
                      />
                    ) : (
                      '(blank)'
                    )}
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
