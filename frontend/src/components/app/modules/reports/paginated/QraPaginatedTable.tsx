'use client';

import type { PaginatedQuestionRow } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import PaginatedQuestionRowCells from './PaginatedQuestionRow';

interface Props {
  questions: PaginatedQuestionRow[];
}

export default function QraPaginatedTable({ questions }: Props) {
  return (
    <div
      className="w-full bg-white border overflow-x-auto print:overflow-visible"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <table className="min-w-full text-[11px] border-collapse">
        <thead>
          <tr className="font-semibold" style={{ backgroundColor: HEADER_BAR_BG }}>
            <th scope="col" className="border-r border-b px-2 py-1 text-left w-[44px]" style={{ borderColor: LAYOUT_BORDER }}>No.</th>
            <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>Question</th>
            <th scope="col" className="border-r border-b px-2 py-1 text-left w-[140px]" style={{ borderColor: LAYOUT_BORDER }}>Standards</th>
            <th scope="col" className="border-r border-b px-2 py-1 text-right w-[80px]" style={{ borderColor: LAYOUT_BORDER }}>% Correct</th>
            <th scope="col" className="border-r border-b px-2 py-1 text-left w-[160px]" style={{ borderColor: LAYOUT_BORDER }}>Correct Answer</th>
            <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>Incorrect Choice Details</th>
            <th scope="col" className="border-b px-2 py-1 text-left w-[220px]" style={{ borderColor: LAYOUT_BORDER }}>Students with Incorrect Choice</th>
          </tr>
        </thead>
        <tbody>
          {questions.map((q) => (
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
    </div>
  );
}
