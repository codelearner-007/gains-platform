'use client';

import { Fragment, useMemo } from 'react';
import type {
  QuestionSummaryMatrixPayload,
  QsmQuestionColumn,
  QsmTeacherGroup,
} from '@/lib/reports/types';
import {
  HEADER_BAR_BG,
  IAD_GREEN,
  IAD_RED,
  LAYOUT_BORDER,
  PBIX_ACCENT_LIGHT_BLUE,
  PBIX_ACCENT_NAVY,
  performanceColor,
} from '@/lib/reports/colors';
import { sanitizeShortAnswer } from '@/lib/reports/format';

interface Props {
  payload: QuestionSummaryMatrixPayload;
  /** Add a per-teacher subtotal row at the foot of each teacher group. */
  showTeacherSubtotal?: boolean;
  /** Color the per-standard column-group header by performance band. */
  highlightStandardHeader?: boolean;
}

function pct(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
}

interface StandardSpan {
  standard: string;
  cpalms: string;
  span: number;
  questions: QsmQuestionColumn[];
}

function buildStandardSpans(questions: QsmQuestionColumn[]): StandardSpan[] {
  const spans: StandardSpan[] = [];
  for (const q of questions) {
    const code = q.cpalms_standard || q.standard || 'Other';
    const last = spans[spans.length - 1];
    if (last && last.cpalms === code) {
      last.span += 1;
      last.questions.push(q);
    } else {
      spans.push({
        standard: q.standard,
        cpalms: code,
        span: 1,
        questions: [q],
      });
    }
  }
  return spans;
}

export default function QuestionSummaryMatrix({
  payload,
  showTeacherSubtotal = false,
  highlightStandardHeader = false,
}: Props) {
  const { questions, teacher_groups: teacherGroups, grand_total: grandTotal } =
    payload;

  const spans = useMemo(() => buildStandardSpans(questions), [questions]);
  const stdPctByCpalms = useMemo(() => {
    const map = new Map<string, { possible: number; correct: number }>();
    for (const q of questions) {
      const code = q.cpalms_standard || q.standard || 'Other';
      const possible = grandTotal.per_question_possible[q.question_id] ?? 0;
      const correct = grandTotal.per_question_correct[q.question_id] ?? 0;
      const acc = map.get(code) ?? { possible: 0, correct: 0 };
      acc.possible += possible;
      acc.correct += correct;
      map.set(code, acc);
    }
    const out = new Map<string, number>();
    for (const [code, { possible, correct }] of map) {
      out.set(code, possible > 0 ? correct / possible : 0);
    }
    return out;
  }, [questions, grandTotal]);

  return (
    <div
      className="w-full overflow-x-auto bg-white border print:overflow-visible"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <table className="min-w-full text-[11px] border-collapse">
        <thead>
          {/* Standard code row */}
          <tr>
            <th
              colSpan={3}
              className="border-r border-b text-left text-white px-2 py-1 sticky left-0 z-10"
              style={{ backgroundColor: PBIX_ACCENT_NAVY, borderColor: LAYOUT_BORDER }}
            >
              Standards
            </th>
            {spans.map((s, i) => {
              const stdPct = stdPctByCpalms.get(s.cpalms) ?? 0;
              const bg = highlightStandardHeader
                ? performanceColor(stdPct)
                : PBIX_ACCENT_NAVY;
              const fg = highlightStandardHeader ? '#000' : '#fff';
              return (
                <th
                  key={`${s.cpalms}-${i}`}
                  colSpan={s.span}
                  className="border-r border-b text-center font-semibold px-2 py-1"
                  style={{ backgroundColor: bg, color: fg, borderColor: LAYOUT_BORDER }}
                  title={
                    highlightStandardHeader
                      ? `${s.cpalms} · ${pct(stdPct)}`
                      : s.cpalms
                  }
                >
                  {s.cpalms}
                </th>
              );
            })}
            <th
              colSpan={2}
              className="border-l border-b text-white px-2 py-1 text-center"
              style={{ backgroundColor: PBIX_ACCENT_NAVY, borderColor: LAYOUT_BORDER }}
            >
              Totals
            </th>
          </tr>
          {/* Question No row */}
          <tr>
            <th
              scope="col"
              className="border-r border-b text-left px-2 py-1 sticky left-0 z-10"
              style={{ backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER }}
            >
              Classroom Instructors
            </th>
            <th
              scope="col"
              className="border-r border-b text-left px-2 py-1"
              style={{ backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER }}
            >
              Student Name
            </th>
            <th
              scope="col"
              className="border-r border-b text-right px-2 py-1"
              style={{ backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER }}
            >
              Score %
            </th>
            {questions.map((q) => (
              <th
                key={q.question_id}
                scope="col"
                className="border-r border-b text-center px-1 py-1 font-semibold"
                style={{ backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER }}
                title={`${q.question_no}: ${sanitizeShortAnswer(q.correct_answer) || 'n/a'}`}
              >
                {q.question_no}
              </th>
            ))}
            <th
              scope="col"
              className="border-r border-b text-right px-2 py-1"
              style={{ backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER }}
            >
              Possible Points
            </th>
            <th
              scope="col"
              className="border-b text-right px-2 py-1"
              style={{ backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER }}
            >
              # Correct Answers
            </th>
          </tr>
        </thead>
        <tbody>
          {teacherGroups.map((group: QsmTeacherGroup) => (
            <Fragment key={group.section_instructor}>
              {group.students.map((student, idx) => (
                <tr
                  key={student.user_uid}
                  className="border-b"
                  style={{ borderColor: LAYOUT_BORDER }}
                >
                  {idx === 0 ? (
                    <td
                      rowSpan={
                        group.students.length + (showTeacherSubtotal ? 1 : 0)
                      }
                      className="border-r px-2 py-1 align-top font-semibold"
                      style={{
                        borderColor: LAYOUT_BORDER,
                        backgroundColor: HEADER_BAR_BG,
                      }}
                    >
                      <div>{group.section_instructor}</div>
                      <div className="text-[10px] text-neutral-700">
                        {pct(group.teacher_score_pct)}
                      </div>
                    </td>
                  ) : null}
                  <th
                    scope="row"
                    className="border-r px-2 py-1 truncate max-w-[180px] text-left font-normal"
                    style={{ borderColor: LAYOUT_BORDER }}
                  >
                    {student.user_name}
                  </th>
                  <td
                    className="border-r px-2 py-1 text-right tabular-nums font-semibold"
                    style={{
                      borderColor: LAYOUT_BORDER,
                      backgroundColor: performanceColor(student.score_pct),
                    }}
                  >
                    {pct(student.score_pct)}
                  </td>
                  {questions.map((q) => {
                    const cell = student.cells[q.question_id];
                    let bg = '#fff';
                    let label = '';
                    let aria = 'not attempted';
                    if (cell === 1) {
                      bg = IAD_GREEN;
                      label = '1';
                      aria = 'correct';
                    } else if (cell === 0) {
                      bg = IAD_RED;
                      label = '0';
                      aria = 'incorrect';
                    }
                    return (
                      <td
                        key={q.question_id}
                        className="border-r px-1 py-0.5 text-center font-semibold tabular-nums"
                        style={{
                          backgroundColor: bg,
                          color: '#000',
                          borderColor: LAYOUT_BORDER,
                        }}
                        aria-label={`${q.question_no} ${aria}`}
                      >
                        {label || (cell === null ? '—' : '')}
                      </td>
                    );
                  })}
                  <td
                    className="border-r px-2 py-1 text-right tabular-nums"
                    style={{ borderColor: LAYOUT_BORDER }}
                  >
                    {student.possible_points}
                  </td>
                  <td
                    className="px-2 py-1 text-right tabular-nums"
                    style={{ borderColor: LAYOUT_BORDER }}
                  >
                    {student.correct_count}
                  </td>
                </tr>
              ))}
              {showTeacherSubtotal && (
                <tr
                  className="border-b font-semibold"
                  style={{
                    borderColor: LAYOUT_BORDER,
                    backgroundColor: HEADER_BAR_BG,
                  }}
                >
                  <td
                    className="border-r px-2 py-1 italic"
                    style={{ borderColor: LAYOUT_BORDER }}
                  >
                    Teacher Subtotal
                  </td>
                  <td
                    className="border-r px-2 py-1 text-right tabular-nums"
                    style={{
                      borderColor: LAYOUT_BORDER,
                      backgroundColor: performanceColor(group.teacher_score_pct),
                    }}
                  >
                    {pct(group.teacher_score_pct)}
                  </td>
                  {questions.map((q) => {
                    const pos = group.students.reduce(
                      (acc, s) => acc + (s.cells[q.question_id] === 1 ? 1 : 0),
                      0,
                    );
                    const att = group.students.reduce(
                      (acc, s) =>
                        acc + (s.cells[q.question_id] === null ? 0 : 1),
                      0,
                    );
                    return (
                      <td
                        key={`sub-${q.question_id}`}
                        className="border-r px-1 py-0.5 text-center tabular-nums"
                        style={{ borderColor: LAYOUT_BORDER }}
                      >
                        {att > 0 ? `${pos}/${att}` : '—'}
                      </td>
                    );
                  })}
                  <td
                    className="border-r px-2 py-1 text-right tabular-nums"
                    style={{ borderColor: LAYOUT_BORDER }}
                  >
                    {group.students.reduce((acc, s) => acc + s.possible_points, 0)}
                  </td>
                  <td
                    className="px-2 py-1 text-right tabular-nums"
                    style={{ borderColor: LAYOUT_BORDER }}
                  >
                    {group.students.reduce((acc, s) => acc + s.correct_count, 0)}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}

          {/* Grand totals */}
          <tr
            className="border-t-2 font-semibold"
            style={{
              borderColor: LAYOUT_BORDER,
              backgroundColor: HEADER_BAR_BG,
            }}
          >
            <td
              className="border-r px-2 py-1"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              Possible Points
            </td>
            <td className="border-r" style={{ borderColor: LAYOUT_BORDER }} />
            <td
              className="border-r px-2 py-1 text-right tabular-nums"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              {grandTotal.possible_points}
            </td>
            {questions.map((q) => (
              <td
                key={`pp-${q.question_id}`}
                className="border-r px-1 py-1 text-center tabular-nums"
                style={{ borderColor: LAYOUT_BORDER }}
              >
                {grandTotal.per_question_possible[q.question_id] ?? 0}
              </td>
            ))}
            <td
              className="border-r px-2 py-1 text-right tabular-nums"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              {grandTotal.possible_points}
            </td>
            <td
              className="px-2 py-1 text-right tabular-nums"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              {grandTotal.correct_count}
            </td>
          </tr>
          <tr
            className="border-b font-semibold"
            style={{
              borderColor: LAYOUT_BORDER,
              backgroundColor: HEADER_BAR_BG,
            }}
          >
            <td
              className="border-r px-2 py-1"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              # Correct Answers
            </td>
            <td className="border-r" style={{ borderColor: LAYOUT_BORDER }} />
            <td
              className="border-r px-2 py-1 text-right tabular-nums"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              {grandTotal.correct_count}
            </td>
            {questions.map((q) => (
              <td
                key={`cc-${q.question_id}`}
                className="border-r px-1 py-1 text-center tabular-nums"
                style={{ borderColor: LAYOUT_BORDER }}
              >
                {grandTotal.per_question_correct[q.question_id] ?? 0}
              </td>
            ))}
            <td className="border-r" style={{ borderColor: LAYOUT_BORDER }} />
            <td style={{ borderColor: LAYOUT_BORDER }} />
          </tr>
          <tr
            className="font-semibold"
            style={{ backgroundColor: HEADER_BAR_BG }}
          >
            <td
              className="border-r px-2 py-1"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              Score %
            </td>
            <td className="border-r" style={{ borderColor: LAYOUT_BORDER }} />
            <td
              className="border-r px-2 py-1 text-right tabular-nums"
              style={{
                borderColor: LAYOUT_BORDER,
                backgroundColor: performanceColor(grandTotal.score_pct),
              }}
            >
              {pct(grandTotal.score_pct)}
            </td>
            {questions.map((q) => {
              const p = grandTotal.per_question_pct[q.question_id] ?? 0;
              return (
                <td
                  key={`pct-${q.question_id}`}
                  className="border-r px-1 py-1 text-center tabular-nums"
                  style={{
                    borderColor: LAYOUT_BORDER,
                    backgroundColor: performanceColor(p),
                  }}
                >
                  {pct(p)}
                </td>
              );
            })}
            <td className="border-r" style={{ borderColor: LAYOUT_BORDER }} />
            <td style={{ borderColor: LAYOUT_BORDER }} />
          </tr>
        </tbody>
      </table>
    </div>
  );
}
