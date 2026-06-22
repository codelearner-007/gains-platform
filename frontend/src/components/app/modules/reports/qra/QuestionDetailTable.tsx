'use client';

import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import type { QuestionOverall } from '@/lib/reports/types';
import { cellColor, HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import {
  formatAnswerHtml,
  formatCorrectAnswerWithPositions,
  formatPercent,
  formatQuestionHtml,
  splitStandards,
} from '@/lib/reports/format';
import RichReportHtml from '../shared/RichReportHtml';
import {
  tableCellStyleLarge as cellBase,
  tableHeaderStyleLarge as headerStyle,
} from '../shared/tableStyles';
import { SortableHeader, useTableSort } from '@/lib/reports/useTableSort';

interface QuestionDetailTableProps {
  questions: QuestionOverall[];
  /** Item id for drill-through to Incorrect Answer Details. When omitted,
   *  the per-row "deep dive" link is hidden. */
  itemId?: string;
  /** Bidirectional cross-filter: clicking a standard chip in a question row
   *  toggles that standard in the page filter (PBIX was fully bidirectional). */
  onSelectStandard?: (schoology_standard: string) => void;
  /** Standards currently active in the filter (for chip highlight). */
  selectedStandards?: string[];
}

type QraSortKey =
  | 'question_no'
  | 'grade_average'
  | 'correct_answer'
  | 'standards'
  | 'description'
  | 'question'
  | 'incorrect_choice_details'
  | 'incorrect_details_name';

const QRA_SORT_ACCESSORS: Record<
  QraSortKey,
  (q: QuestionOverall) => string | number | null
> = {
  question_no: (q) => {
    const n = Number(q.question_no);
    return Number.isFinite(n) ? n : q.question_no ?? '';
  },
  grade_average: (q) => q.grade_average ?? null,
  correct_answer: (q) => (q.correct_answer || '').toLowerCase(),
  standards: (q) => (q.standards || '').toLowerCase(),
  description: (q) => (q.description || '').toLowerCase(),
  question: (q) => (q.question || '').toLowerCase(),
  incorrect_choice_details: (q) =>
    (q.incorrect_choice_details || '').toLowerCase(),
  incorrect_details_name: (q) => (q.incorrect_details_name || '').toLowerCase(),
};

const QRA_INITIAL_DIRECTIONS: Partial<Record<QraSortKey, 'asc' | 'desc'>> = {
  grade_average: 'asc',
  question_no: 'asc',
};

export default function QuestionDetailTable({
  questions,
  itemId,
  onSelectStandard,
  selectedStandards,
}: QuestionDetailTableProps) {
  const selectedStandardSet = new Set(selectedStandards ?? []);
  // Legacy PBIX default (QRA Interactive, ord 2): the question-detail tableEx
  // binds `Sum(cube_question_summary_overall.Sorting Question_No)` as its first
  // field, i.e. question-number ascending (Q1 → Q18).
  const { sortedRows: rows, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<QuestionOverall, QraSortKey>({
      rows: questions,
      accessors: QRA_SORT_ACCESSORS,
      defaultColumn: 'question_no',
      defaultDirection: 'asc',
      initialDirections: QRA_INITIAL_DIRECTIONS,
    });

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
          <span className="ml-2 text-[11px] font-normal text-neutral-700 print:hidden">
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
            <col style={{ width: '4%' }} />
            <col style={{ width: '27%' }} />
            <col style={{ width: '9%' }} />
            <col style={{ width: '11%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '15%' }} />
            <col style={{ width: '11%' }} />
            <col style={{ width: '11%' }} />
          </colgroup>
          <thead>
            <tr>
              <th style={{ ...headerStyle, textAlign: 'center' }}>
                <SortableHeader
                  column="question_no"
                  label="No"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="center"
                />
              </th>
              <th style={headerStyle}>
                <SortableHeader
                  column="question"
                  label="Question"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={{ ...headerStyle, textAlign: 'center' }}>
                <SortableHeader
                  column="grade_average"
                  label="% of Correct Answers"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="center"
                />
              </th>
              <th style={headerStyle}>
                <SortableHeader
                  column="correct_answer"
                  label="Correct Answer"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={headerStyle}>
                <SortableHeader
                  column="incorrect_choice_details"
                  label="Incorrect Choice Details"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={headerStyle}>
                <SortableHeader
                  column="incorrect_details_name"
                  label="Incorrect Details Name"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={headerStyle}>
                <SortableHeader
                  column="standards"
                  label="Standards"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={headerStyle}>
                <SortableHeader
                  column="description"
                  label="Description"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((q, idx) => {
              const ga = q.grade_average;
              const pctBg = cellColor(ga);
              const correctHtml = formatCorrectAnswerWithPositions(
                q.correct_answer,
                q.position_number,
              )
                .map((line) => formatAnswerHtml(line, 'correct answer'))
                .join('<br />');
              // Split entries onto their own line. The cube emits a
              // single string like "3.7% chose [a. ...], 7.4% chose
              // [b. ...]"; lookahead anchors on the next entry's
              // percentage so the split is safe even when an answer's
              // own text contains "], ".
              const incorrectChoiceRaw = (q.incorrect_choice_details || '').replace(
                /\], (?=\d+\.?\d*% chose \[)/g,
                ']\n',
              );
              const incorrectChoiceHtml =
                ga >= 1
                  ? ''
                  : formatAnswerHtml(incorrectChoiceRaw, 'incorrect choice');
              const incorrectNamesHtml =
                ga >= 1
                  ? ''
                  : formatAnswerHtml(q.incorrect_details_name, 'incorrect choice');
              const standardsList = splitStandards(q.standards);
              const descriptionText = (q.description || '').trim();

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
                        <ChevronRight className="h-3 w-3 opacity-60 print:hidden" />
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
                  <td
                    style={{
                      ...cellBase,
                      whiteSpace: 'pre-line',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    <RichReportHtml
                      className="pilot-answer-html"
                      html={correctHtml}
                    />
                  </td>
                  <td
                    style={{
                      ...cellBase,
                      overflowWrap: 'anywhere',
                      lineHeight: '1.5',
                    }}
                  >
                    <RichReportHtml
                      className="pilot-answer-html"
                      html={incorrectChoiceHtml}
                    />
                  </td>
                  <td
                    style={{
                      ...cellBase,
                      whiteSpace: 'pre-line',
                      overflowWrap: 'anywhere',
                      lineHeight: '1.5',
                    }}
                  >
                    <RichReportHtml
                      className="pilot-answer-html"
                      html={incorrectNamesHtml}
                    />
                  </td>
                  <td style={cellBase}>
                    {standardsList.length > 0 ? (
                      <div className="flex flex-col gap-0.5 text-[11px] font-mono leading-tight break-all">
                        {standardsList.map((s, i) =>
                          onSelectStandard ? (
                            <button
                              key={`${q.question_id}-std-${i}`}
                              type="button"
                              onClick={() => onSelectStandard(s)}
                              aria-pressed={selectedStandardSet.has(s)}
                              title="Filter the report by this standard"
                              className={`text-left rounded px-1 -mx-1 cursor-pointer hover:bg-blue-50 ${
                                selectedStandardSet.has(s)
                                  ? 'bg-blue-100 font-semibold text-blue-800'
                                  : 'text-blue-700'
                              }`}
                            >
                              {s}
                            </button>
                          ) : (
                            <span key={`${q.question_id}-std-${i}`}>{s}</span>
                          ),
                        )}
                      </div>
                    ) : (
                      <span className="text-neutral-400">—</span>
                    )}
                  </td>
                  <td
                    style={{
                      ...cellBase,
                      fontSize: '11px',
                      lineHeight: '1.45',
                      color: 'rgb(82 82 82)',
                      whiteSpace: 'pre-line',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {descriptionText || (
                      <span className="text-neutral-400">—</span>
                    )}
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
