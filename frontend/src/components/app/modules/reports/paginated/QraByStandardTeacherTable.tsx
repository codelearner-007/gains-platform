'use client';

import { Fragment } from 'react';
import type { QraStandardGroup } from '@/lib/reports/types';
import {
  GROUP_HEADER_CYAN,
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  PBIX_ACCENT_NAVY,
  performanceColor,
} from '@/lib/reports/colors';
import PaginatedQuestionRowCells from './PaginatedQuestionRow';

interface Props {
  standardGroups: QraStandardGroup[];
}

export default function QraByStandardTeacherTable({ standardGroups }: Props) {
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
                <div className="text-[11px] text-white/85 leading-snug">
                  {sg.standard_description}
                </div>
              )}
            </div>
          </div>
          <table className="min-w-full text-[11px] border-collapse">
            <thead>
              <tr
                className="font-semibold"
                style={{ backgroundColor: HEADER_BAR_BG }}
              >
                <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>No.</th>
                <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>Question</th>
                <th scope="col" className="border-r border-b px-2 py-1 text-right" style={{ borderColor: LAYOUT_BORDER }}>% Correct</th>
                <th scope="col" className="border-r border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>Correct Answer</th>
                <th scope="col" className="border-b px-2 py-1 text-left" style={{ borderColor: LAYOUT_BORDER }}>Incorrect Choice Details</th>
              </tr>
            </thead>
            <tbody>
              {sg.teacher_groups.map((tg, ti) => (
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
                  {tg.questions.map((q, qi) => (
                    <tr
                      key={`${tg.section_instructor}-${q.question_id}-${qi}`}
                      className="border-b align-top"
                      style={{ borderColor: LAYOUT_BORDER }}
                    >
                      <PaginatedQuestionRowCells row={q} />
                    </tr>
                  ))}
                </Fragment>
              ))}
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
