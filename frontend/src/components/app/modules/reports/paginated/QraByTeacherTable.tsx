'use client';

import { Fragment } from 'react';
import type { QraTeacherGroup } from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  GROUP_HEADER_CYAN,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import PaginatedQuestionRowCells from './PaginatedQuestionRow';

interface Props {
  teacherGroups: QraTeacherGroup[];
}

export default function QraByTeacherTable({ teacherGroups }: Props) {
  return (
    <div
      className="w-full bg-white border overflow-x-auto print:overflow-visible"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <table className="min-w-full text-[11px] border-collapse">
        <thead>
          <tr className="font-semibold" style={{ backgroundColor: HEADER_BAR_BG }}>
            <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>No.</th>
            <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>Question</th>
            <th scope="col" className="border-r border-b px-2 py-1 text-right" style={{ borderColor: LAYOUT_BORDER }}>% Correct</th>
            <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>Correct Answer</th>
            <th scope="col" className="border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>Incorrect Choice Details</th>
          </tr>
        </thead>
        <tbody>
          {teacherGroups.map((group, idx) => (
            <Fragment key={group.section_instructor}>
              <tr
                className={`font-semibold border-b border-t-2 ${idx > 0 ? 'print:break-before-page' : ''}`}
                style={{
                  borderColor: LAYOUT_BORDER,
                  backgroundColor: GROUP_HEADER_CYAN,
                }}
              >
                <td colSpan={2} className="px-2 py-1">
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
              {group.questions.map((q) => (
                <tr
                  key={`${group.section_instructor}-${q.question_id}`}
                  className="border-b align-top"
                  style={{ borderColor: LAYOUT_BORDER }}
                >
                  <PaginatedQuestionRowCells row={q} />
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
