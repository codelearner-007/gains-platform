'use client';

import type { PaginatedQuestionRow } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import { splitStandards } from '@/lib/reports/format';
import { SortableHeader, useTableSort } from '@/lib/reports/useTableSort';
import PaginatedQuestionRowCells from './PaginatedQuestionRow';
import ScrollableTableContainer from '../shared/ScrollableTableContainer';
import { stickyHeaderStyle } from '../shared/tableStyles';

interface Props {
  questions: PaginatedQuestionRow[];
}

type PagSortKey =
  | 'question_no'
  | 'question'
  | 'standard'
  | 'grade_average'
  | 'correct_answer'
  | 'incorrect_choice_details'
  | 'incorrect_details_name';

const PAG_SORT_ACCESSORS: Record<
  PagSortKey,
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
  incorrect_details_name: (q) =>
    (q.incorrect_details_name || '').toLowerCase(),
};

const PAG_INITIAL_DIRECTIONS: Partial<Record<PagSortKey, 'asc' | 'desc'>> = {
  question_no: 'asc',
  grade_average: 'asc',
};

export default function QraPaginatedTable({ questions }: Props) {
  // Legacy "clean" by-teacher PDF order = % Correct ascending (lowest-scoring
  // questions first). Open re-sortable via any header.
  const { sortedRows: rows, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<PaginatedQuestionRow, PagSortKey>({
      rows: questions,
      accessors: PAG_SORT_ACCESSORS,
      defaultColumn: 'grade_average',
      defaultDirection: 'asc',
      initialDirections: PAG_INITIAL_DIRECTIONS,
    });

  const headerCls = 'border-r border-b px-2 py-1';
  // Header-band bg lives on each <th> (a <tr> bg won't paint behind a sticky cell).
  const stickyTh = stickyHeaderStyle(
    { backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER },
    { top: 0, border: LAYOUT_BORDER },
  );
  return (
    <ScrollableTableContainer
      className="bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <table className="min-w-full text-[11px] border-collapse">
        <thead>
          <tr className="font-semibold">
            <th scope="col" className={`${headerCls} text-left w-[44px]`} style={stickyTh}>
              <SortableHeader column="question_no" label="No." title="Question Number" description="The question's sequence number on the assessment." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th scope="col" className={`${headerCls} text-left`} style={stickyTh}>
              <SortableHeader column="question" label="Question" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th scope="col" className={`${headerCls} text-left w-[140px]`} style={stickyTh}>
              <SortableHeader column="standard" label="Standard" title="Standard" description="The CPALMS academic standard the question aligns to." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th scope="col" className={`${headerCls} text-right w-[80px]`} style={stickyTh}>
              <SortableHeader column="grade_average" label="% of Correct Answers" title="% of Correct Answers" description="Share of students who answered this question correctly." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="right" />
            </th>
            <th scope="col" className={`${headerCls} text-left w-[160px]`} style={stickyTh}>
              <SortableHeader column="correct_answer" label="Correct Answer" title="Correct Answer" description="The correct answer choice(s) for this question." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th scope="col" className={`${headerCls} text-left`} style={stickyTh}>
              <SortableHeader column="incorrect_choice_details" label="Incorrect Choice details" title="Incorrect Choice Details" description="Each wrong answer chosen and the percent of students who chose it." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th scope="col" className="border-b px-2 py-1 text-left w-[220px]" style={stickyTh}>
              <SortableHeader column="incorrect_details_name" label="Students with Incorrect Choice" title="Students with Incorrect Choice" description="Names of students grouped by the incorrect choice they selected." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((q) => (
            <tr
              key={q.question_id}
              className="border-b align-top"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              <PaginatedQuestionRowCells
                row={q}
                showStandardsColumn
                showStudentsColumn
              />
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollableTableContainer>
  );
}
