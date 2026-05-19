'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import type { IncorrectChoice, QuestionOverall } from '@/lib/reports/types';
import { cellColor, HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import {
  formatAnswerHtml,
  formatCorrectAnswer,
  formatPercent,
  formatQuestionHtml,
} from '@/lib/reports/format';
import RichReportHtml from '../shared/RichReportHtml';
import {
  tableCellStyleLarge as cellBase,
  tableHeaderStyleLarge as headerStyle,
} from '../shared/tableStyles';

interface QuestionDetailTableProps {
  questions: QuestionOverall[];
  // incorrectChoices reserved for future per-question expansion; kept for API parity
  incorrectChoices?: IncorrectChoice[];
  /** Item id for drill-through to Incorrect Answer Details. When omitted,
   *  the per-row "deep dive" link is hidden. */
  itemId?: string;
}

export default function QuestionDetailTable({
  questions,
  itemId,
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
        {itemId ? (
          <span className="ml-2 text-[11px] font-normal text-neutral-700">
            (click a question number to drill into incorrect-answer details)
          </span>
        ) : null}
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
              const correctHtml = formatCorrectAnswer(q.correct_answer)
                .map((line) => formatAnswerHtml(line, 'correct answer'))
                .join('<br />');
              const incorrectChoiceHtml =
                ga >= 1
                  ? ''
                  : formatAnswerHtml(q.incorrect_choice_details, 'incorrect choice');
              const incorrectNamesHtml =
                ga >= 1
                  ? ''
                  : formatAnswerHtml(q.incorrect_details_name, 'incorrect choice');
              const standards = q.standards || q.strand || '—';

              return (
                <tr key={`${q.question_id}-${q.question_no}-${idx}`} className="hover:bg-neutral-50">
                  <td
                    style={{
                      ...cellBase,
                      textAlign: 'center',
                      fontWeight: 600,
                      padding: 0,
                    }}
                  >
                    {itemId ? (
                      <Link
                        href={{
                          pathname: '/app/reports/incorrect-answer-details',
                          query: {
                            item_id: itemId,
                            question_id: q.question_id,
                          },
                        }}
                        title="Drill into Incorrect Answer Details"
                        className="inline-flex items-center justify-center gap-0.5 w-full h-full px-2 py-2 text-blue-700 hover:bg-blue-50 hover:underline transition-colors"
                      >
                        {q.question_no}
                        <ChevronRight className="h-3 w-3 opacity-60" />
                      </Link>
                    ) : (
                      <div className="px-2 py-2">{q.question_no}</div>
                    )}
                  </td>
                  <td style={cellBase}>
                    <RichReportHtml
                      className="pilot-question-html"
                      html={formatQuestionHtml(q.question)}
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
                    <RichReportHtml
                      className="pilot-answer-html"
                      html={correctHtml}
                    />
                  </td>
                  <td style={cellBase}>
                    <RichReportHtml
                      className="pilot-answer-html"
                      html={incorrectChoiceHtml}
                    />
                  </td>
                  <td style={{ ...cellBase, whiteSpace: 'pre-line' }}>
                    <RichReportHtml
                      className="pilot-answer-html"
                      html={incorrectNamesHtml}
                    />
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
