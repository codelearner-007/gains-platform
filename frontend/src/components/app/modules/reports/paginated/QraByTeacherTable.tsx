'use client';

import { Fragment } from 'react';
import type { PaginatedQuestionRow, QraTeacherGroup } from '@/lib/reports/types';
import {
  GROUP_HEADER_CYAN,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { splitStandards } from '@/lib/reports/format';
import {
  SortableHeader,
  sortRowsBy,
  useSharedSort,
} from '@/lib/reports/useTableSort';
import PaginatedQuestionRowCells from './PaginatedQuestionRow';
import ScrollableTableContainer from '../shared/ScrollableTableContainer';
import { STICKY_HEADER_BAND } from '../shared/tableStyles';

interface Props {
  teacherGroups: QraTeacherGroup[];
}

type ByTeacherSortKey =
  | 'question_no'
  | 'question'
  | 'standard'
  | 'grade_average'
  | 'correct_answer'
  | 'incorrect_choice_details';

const SORT_ACCESSORS: Record<
  ByTeacherSortKey,
  (q: PaginatedQuestionRow) => string | number | null
> = {
  question_no: (q) => {
    const n = Number(q.sorting_question_no ?? q.question_no);
    return Number.isFinite(n) ? n : (q.question_no ?? '');
  },
  question: (q) => (q.question || '').toLowerCase(),
  standard: (q) =>
    splitStandards(q.cpalms_standard || q.standards).join(' ').toLowerCase(),
  grade_average: (q) => q.grade_average ?? null,
  correct_answer: (q) => (q.correct_answer || '').toLowerCase(),
  incorrect_choice_details: (q) =>
    (q.incorrect_choice_details || '').toLowerCase(),
};

const INITIAL_DIRECTIONS: Partial<Record<ByTeacherSortKey, 'asc' | 'desc'>> = {
  question_no: 'asc',
  grade_average: 'asc',
};

export default function QraByTeacherTable({ teacherGroups }: Props) {
  // Legacy clean by-teacher PDF order = % Correct ascending within each
  // teacher group. One header click re-sorts every group consistently.
  const { sortColumn, sortDirection, onHeaderClick } =
    useSharedSort<ByTeacherSortKey>('grade_average', 'asc', INITIAL_DIRECTIONS);

  return (
    <ScrollableTableContainer
      className="bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <table className="min-w-full text-[11px] border-collapse">
        <thead>
          <tr className="font-semibold">
            <th scope="col" className="border-r border-b px-2 py-1 text-left" style={STICKY_HEADER_BAND}>
              <SortableHeader column="question_no" label="No." title="Question Number" description="The question's sequence number within the assessment." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th scope="col" className="border-r border-b px-2 py-1 text-left" style={STICKY_HEADER_BAND}>
              <SortableHeader column="question" label="Question" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th scope="col" className="border-r border-b px-2 py-1 text-left w-[140px]" style={STICKY_HEADER_BAND}>
              <SortableHeader column="standard" label="Standard" title="Standard (CPALMS code)" description="The CPALMS academic standard code the question aligns to." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th scope="col" className="border-r border-b px-2 py-1 text-right" style={STICKY_HEADER_BAND}>
              <SortableHeader column="grade_average" label="% Correct" title="Percent Correct" description="Share of students who answered the question correctly." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="right" />
            </th>
            <th scope="col" className="border-r border-b px-2 py-1 text-left" style={STICKY_HEADER_BAND}>
              <SortableHeader column="correct_answer" label="Correct Answer" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th scope="col" className="border-b px-2 py-1 text-left" style={STICKY_HEADER_BAND}>
              <SortableHeader column="incorrect_choice_details" label="Incorrect Choice Details" title="Incorrect Choice Details" description="Which wrong answers students chose and the percent who chose each." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
          </tr>
        </thead>
        <tbody>
          {teacherGroups.map((group, idx) => {
            const sorted = sortRowsBy(
              group.questions,
              SORT_ACCESSORS[sortColumn],
              sortDirection,
            );
            return (
              <Fragment key={group.section_instructor}>
                <tr
                  className={`font-semibold border-b border-t-2 ${idx > 0 ? 'print:break-before-page' : ''}`}
                  style={{
                    borderColor: LAYOUT_BORDER,
                    backgroundColor: GROUP_HEADER_CYAN,
                  }}
                >
                  <td colSpan={3} className="px-2 py-1">
                    Teacher: {group.section_instructor}
                  </td>
                  <td
                    className="border-l px-2 py-1 text-right tabular-nums"
                    style={{
                      borderColor: LAYOUT_BORDER,
                      backgroundColor: performanceColor(group.teacher_grade_average),
                    }}
                  >
                    {group.teacher_grade_average_pct}
                  </td>
                  <td colSpan={2} className="px-2 py-1 text-neutral-700 italic">
                    {group.questions.length} questions
                  </td>
                </tr>
                {sorted.map((q) => (
                  <tr
                    key={`${group.section_instructor}-${q.question_id}`}
                    className="border-b align-top"
                    style={{ borderColor: LAYOUT_BORDER }}
                  >
                    <PaginatedQuestionRowCells row={q} showStandardsColumn />
                  </tr>
                ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </ScrollableTableContainer>
  );
}
