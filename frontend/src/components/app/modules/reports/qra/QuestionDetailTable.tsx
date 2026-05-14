'use client';

import { useMemo } from 'react';
import type { IncorrectChoice, QuestionOverall } from '@/lib/reports/types';
import { cellColor, HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import {
  formatCorrectAnswer,
  formatPercent,
  formatQuestionHtml,
} from '@/lib/reports/format';
import {
  tableCellStyleLarge as cellBase,
  tableHeaderStyleLarge as headerStyle,
} from '../shared/tableStyles';

interface QuestionDetailTableProps {
  questions: QuestionOverall[];
  // incorrectChoices reserved for future per-question expansion; kept for API parity
  incorrectChoices?: IncorrectChoice[];
}

export default function QuestionDetailTable({
  questions,
}: QuestionDetailTableProps) {
  const rows = useMemo(
    () =>
      [...questions].sort(
        (a, b) => Number(a.question_no) - Number(b.question_no),
      ),
    [questions],
  );

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Question Summary Report
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
            <col style={{ width: '5%' }} />
            <col style={{ width: '32%' }} />
            <col style={{ width: '11%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '14%' }} />
            <col style={{ width: '18%' }} />
            <col style={{ width: '8%' }} />
          </colgroup>
          <thead>
            <tr>
              <th style={{ ...headerStyle, textAlign: 'center' }}>No</th>
              <th style={headerStyle}>Question</th>
              <th style={{ ...headerStyle, textAlign: 'center' }}>
                % of Correct Answers
              </th>
              <th style={headerStyle}>Correct Answer</th>
              <th style={headerStyle}>Incorrect Choice Details</th>
              <th style={headerStyle}>Incorrect Details Name</th>
              <th style={headerStyle}>Standards</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((q, idx) => {
              const ga = q.grade_average;
              const pctBg = cellColor(ga);
              const correctLines = formatCorrectAnswer(q.correct_answer);
              const incorrectChoice =
                ga >= 1 ? '' : q.incorrect_choice_details ?? '';
              const incorrectNames =
                ga >= 1 ? '' : q.incorrect_details_name ?? '';
              const standards = q.standards || q.strand || '—';

              return (
                <tr key={`${q.question_id}-${q.question_no}-${idx}`} className="hover:bg-neutral-50">
                  <td
                    style={{
                      ...cellBase,
                      textAlign: 'center',
                      fontWeight: 600,
                    }}
                  >
                    {q.question_no}
                  </td>
                  <td style={cellBase}>
                    <div
                      className="pilot-question-html"
                      dangerouslySetInnerHTML={{
                        __html: formatQuestionHtml(q.question),
                      }}
                    />
                  </td>
                  <td
                    style={{
                      ...cellBase,
                      textAlign: 'center',
                      fontWeight: 600,
                      backgroundColor: pctBg,
                    }}
                  >
                    {formatPercent(ga, 1)}
                  </td>
                  <td style={{ ...cellBase, whiteSpace: 'pre-line' }}>
                    {correctLines.join('\n')}
                  </td>
                  <td style={cellBase}>{incorrectChoice}</td>
                  <td style={{ ...cellBase, whiteSpace: 'pre-line' }}>
                    {incorrectNames}
                  </td>
                  <td style={{ ...cellBase, textAlign: 'center' }}>
                    {standards}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
