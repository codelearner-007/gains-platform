'use client';

import { Fragment } from 'react';
import type { PaginatedQuestionRow, QraStandardGroup } from '@/lib/reports/types';
import {
  GROUP_HEADER_CYAN,
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  PBIX_ACCENT_NAVY,
  performanceColor,
} from '@/lib/reports/colors';
import {
  SortableHeader,
  sortRowsBy,
  useSharedSort,
  type SortDirection,
} from '@/lib/reports/useTableSort';
import PaginatedQuestionRowCells from './PaginatedQuestionRow';

interface Props {
  standardGroups: QraStandardGroup[];
}

type StdTeacherSortKey =
  | 'question_no'
  | 'question'
  | 'grade_average'
  | 'correct_answer'
  | 'incorrect_choice_details';

const SORT_ACCESSORS: Record<
  StdTeacherSortKey,
  (q: PaginatedQuestionRow) => string | number | null
> = {
  question_no: (q) => {
    const n = Number(q.sorting_question_no ?? q.question_no);
    return Number.isFinite(n) ? n : (q.question_no ?? '');
  },
  question: (q) => (q.question || '').toLowerCase(),
  grade_average: (q) => q.grade_average ?? null,
  correct_answer: (q) => (q.correct_answer || '').toLowerCase(),
  incorrect_choice_details: (q) =>
    (q.incorrect_choice_details || '').toLowerCase(),
};

const INITIAL_DIRECTIONS: Partial<Record<StdTeacherSortKey, 'asc' | 'desc'>> = {
  question_no: 'asc',
  grade_average: 'asc',
};

function StandardBlockHead({
  sortColumn,
  sortDirection,
  onHeaderClick,
}: {
  sortColumn: StdTeacherSortKey;
  sortDirection: SortDirection;
  onHeaderClick: (c: StdTeacherSortKey) => void;
}) {
  return (
    <tr className="font-semibold" style={{ backgroundColor: HEADER_BAR_BG }}>
      <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>
        <SortableHeader column="question_no" label="No." title="Question Number" description="Question sequence number within the standard/teacher block." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
      </th>
      <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>
        <SortableHeader column="question" label="Question" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
      </th>
      <th scope="col" className="border-r border-b px-2 py-1 text-right" style={{ borderColor: LAYOUT_BORDER }}>
        <SortableHeader column="grade_average" label="% Correct" title="Percent Correct" description="Share of students who answered the question correctly." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="right" />
      </th>
      <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>
        <SortableHeader column="correct_answer" label="Correct Answer" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
      </th>
      <th scope="col" className="border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>
        <SortableHeader column="incorrect_choice_details" label="Incorrect Choice Details" title="Incorrect Choice Details" description="Per-distractor breakdown of wrong answers chosen and percent who chose each." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
      </th>
    </tr>
  );
}

export default function QraByStandardTeacherTable({ standardGroups }: Props) {
  // Legacy SSRS order = % Correct ascending within each teacher block. One
  // header click re-sorts every standard/teacher block consistently.
  const { sortColumn, sortDirection, onHeaderClick } =
    useSharedSort<StdTeacherSortKey>(
      'grade_average',
      'asc',
      INITIAL_DIRECTIONS,
    );

  return (
    <div className="space-y-3">
      {standardGroups.map((sg, idx) => (
        <div
          key={`${sg.cpalms_standard}-${idx}`}
          className={`bg-white border ${idx > 0 ? 'print:break-before-page' : ''}`}
          style={{ borderColor: LAYOUT_BORDER }}
        >
          <div
            className="px-3 py-2 border-b"
            style={{
              borderColor: LAYOUT_BORDER,
              backgroundColor: PBIX_ACCENT_NAVY,
            }}
          >
            <div className="text-white">
              <div className="font-bold text-[13px] font-mono">
                {sg.cpalms_standard}
              </div>
              {sg.standard_description && (
                <div className="text-[11px] text-white leading-snug">
                  {sg.standard_description}
                </div>
              )}
            </div>
          </div>
          <table className="min-w-full text-[11px] border-collapse">
            <thead>
              <StandardBlockHead
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onHeaderClick={onHeaderClick}
              />
            </thead>
            <tbody>
              {sg.teacher_groups.map((tg, ti) => {
                const sorted = sortRowsBy(
                  tg.questions,
                  SORT_ACCESSORS[sortColumn],
                  sortDirection,
                );
                return (
                  <Fragment key={`${tg.section_instructor}-${ti}`}>
                    <tr
                      className="font-semibold border-b border-t"
                      style={{
                        borderColor: LAYOUT_BORDER,
                        backgroundColor: GROUP_HEADER_CYAN,
                      }}
                    >
                      <td colSpan={2} className="px-2 py-1">
                        Section Instructor: {tg.section_instructor}
                      </td>
                      <td
                        className="border-l px-2 py-1 text-right tabular-nums"
                        style={{
                          borderColor: LAYOUT_BORDER,
                          backgroundColor: performanceColor(
                            tg.teacher_standard_average,
                          ),
                        }}
                      >
                        {tg.teacher_standard_average_pct}
                      </td>
                      <td colSpan={2} className="px-2 py-1 text-neutral-700 italic">
                        {tg.questions.length} questions
                      </td>
                    </tr>
                    {sorted.map((q, qi) => (
                      <tr
                        key={`${tg.section_instructor}-${q.question_id}-${qi}`}
                        className="border-b align-top"
                        style={{ borderColor: LAYOUT_BORDER }}
                      >
                        <PaginatedQuestionRowCells row={q} />
                      </tr>
                    ))}
                  </Fragment>
                );
              })}
            </tbody>
            {/* Standard Average in the FOOTER, matching the legacy SSRS
                render (the *By Standard And Teacher.pdf* set; PAG-7). */}
            <tfoot>
              <tr
                className="font-bold border-t-2"
                style={{ borderColor: LAYOUT_BORDER }}
              >
                <td colSpan={2} className="px-2 py-1 text-right">
                  Standard Average:
                </td>
                <td
                  className="border-l px-2 py-1 text-right tabular-nums"
                  style={{
                    borderColor: LAYOUT_BORDER,
                    backgroundColor: performanceColor(sg.standard_average),
                  }}
                >
                  {sg.standard_average_pct}
                </td>
                <td colSpan={2} className="px-2 py-1" />
              </tr>
            </tfoot>
          </table>
        </div>
      ))}
    </div>
  );
}
