'use client';

import { Fragment, useMemo } from 'react';
import type {
  QuestionSummaryMatrixPayload,
  QsmQuestionColumn,
  QsmStudentRow,
  QsmTeacherGroup,
} from '@/lib/reports/types';
import {
  EMPTY_TABLE_FG,
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  PBIX_ACCENT_LIGHT_BLUE,
  PBIX_ACCENT_NAVY,
  qsrCellColor,
  qsrPerformanceColor,
} from '@/lib/reports/colors';
import { sanitizeShortAnswer } from '@/lib/reports/format';
import {
  SortableHeader,
  sortRowsBy,
  useSharedSort,
} from '@/lib/reports/useTableSort';

interface Props {
  payload: QuestionSummaryMatrixPayload;
  /**
   * Render the legacy "- Teacher" two-row subtotal block (# Correct Answers
   * + Score %) at the foot of each teacher group (PBIX ord 7 / PAG-4).
   */
  showTeacherSubtotal?: boolean;
  /**
   * PAG-5 (redacted, PBIX ord 17): anonymize student / teacher names so the
   * matrix can be shared without PII. This is a client-side deterministic
   * redaction; the cube's canonical `*_name_hash` columns (cube_user_summary)
   * are not yet joined into the QSR matrix query — exact legacy-hash parity is
   * a documented follow-up (there is no sample redacted PDF to diff against).
   */
  redacted?: boolean;
}

function pct(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
}

/**
 * Format a partial-credit points value (cell, total, subtotal). Integers
 * render bare (1, 0, 318); fractionals keep up to two decimals (0.5, 0.33).
 */
function pts(v: number | null | undefined): string {
  if (v === null || v === undefined) return '';
  return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(2)));
}

/**
 * Deterministic, stable anonymization for the redacted QSR variant. Same input
 * always yields the same label so a reader can still track a row across pages.
 */
function redactName(seed: string, prefix: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return `${prefix} ${h.toString(36).toUpperCase().slice(0, 6)}`;
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

type QsmSortKey = 'instructor' | 'student' | 'score';

const STUDENT_ACCESSORS: Record<
  Extract<QsmSortKey, 'student' | 'score'>,
  (s: QsmStudentRow) => string | number | null
> = {
  student: (s) => (s.user_name || '').toLowerCase(),
  score: (s) => s.score_pct ?? null,
};

export default function QuestionSummaryMatrix({
  payload,
  showTeacherSubtotal = false,
  redacted = false,
}: Props) {
  const {
    questions,
    teacher_groups: teacherGroups,
    grand_total: grandTotal,
    per_student_available: perStudentAvailable = true,
  } = payload;

  const spans = useMemo(() => buildStandardSpans(questions), [questions]);

  // The fixed row-label columns are click-to-sortable (the legacy tableEx
  // matrix sorted on its row headers). Default keeps the server/legacy row
  // order. "Classroom Instructors" reorders the teacher groups; "Student
  // Name"/"Score %" reorder students WITHIN each group (rowSpan + subtotal
  // blocks stay intact). The per-question matrix columns are not row-sortable.
  const { sortColumn, sortDirection, onHeaderClick } = useSharedSort<QsmSortKey>(
    'instructor',
    'asc',
  );

  const orderedGroups = useMemo(() => {
    if (sortColumn !== 'instructor') return teacherGroups;
    return sortRowsBy(
      teacherGroups,
      (g) => (g.section_instructor || '').toLowerCase(),
      sortDirection,
    );
  }, [teacherGroups, sortColumn, sortDirection]);

  const orderStudents = (students: QsmStudentRow[]): QsmStudentRow[] => {
    if (sortColumn === 'instructor') return students;
    return sortRowsBy(students, STUDENT_ACCESSORS[sortColumn], sortDirection);
  };

  // Cube-only (parquet-loaded) schools carry no per-student fact rows, so the
  // matrix body / question columns / teacher groups are empty by design. The
  // grand_total is still cube-derived, so we render the assessment-level totals
  // plus an explicit note instead of a misleading all-zero 0% matrix.
  if (!perStudentAvailable) {
    return (
      <div
        className="w-full bg-white border print:overflow-visible"
        style={{ borderColor: LAYOUT_BORDER }}
      >
        <table className="min-w-full text-[11px] border-collapse">
          <thead>
            <tr>
              <th
                colSpan={2}
                className="border-r border-b text-left text-white px-2 py-1"
                style={{
                  backgroundColor: PBIX_ACCENT_NAVY,
                  borderColor: LAYOUT_BORDER,
                }}
              >
                Assessment Total
              </th>
              <th
                className="border-b text-white px-2 py-1 text-center"
                style={{
                  backgroundColor: PBIX_ACCENT_NAVY,
                  borderColor: LAYOUT_BORDER,
                }}
              >
                Score %
              </th>
            </tr>
            <tr>
              <th
                scope="col"
                className="border-r border-b text-right px-2 py-1"
                style={{
                  backgroundColor: PBIX_ACCENT_LIGHT_BLUE,
                  borderColor: LAYOUT_BORDER,
                }}
              >
                Possible Points
              </th>
              <th
                scope="col"
                className="border-r border-b text-right px-2 py-1"
                style={{
                  backgroundColor: PBIX_ACCENT_LIGHT_BLUE,
                  borderColor: LAYOUT_BORDER,
                }}
              >
                # Correct Answers
              </th>
              <th
                scope="col"
                className="border-b text-right px-2 py-1"
                style={{
                  backgroundColor: PBIX_ACCENT_LIGHT_BLUE,
                  borderColor: LAYOUT_BORDER,
                }}
              >
                Score %
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              className="border-b font-semibold"
              style={{
                borderColor: LAYOUT_BORDER,
                backgroundColor: HEADER_BAR_BG,
              }}
            >
              <td
                className="border-r px-2 py-1 text-right tabular-nums"
                style={{ borderColor: LAYOUT_BORDER }}
              >
                {pts(grandTotal.possible_points)}
              </td>
              <td
                className="border-r px-2 py-1 text-right tabular-nums"
                style={{ borderColor: LAYOUT_BORDER }}
              >
                {pts(grandTotal.correct_count)}
              </td>
              <td
                className="px-2 py-1 text-right tabular-nums"
                style={{
                  borderColor: LAYOUT_BORDER,
                  backgroundColor: qsrPerformanceColor(grandTotal.score_pct),
                }}
              >
                {pct(grandTotal.score_pct)}
              </td>
            </tr>
          </tbody>
        </table>
        <p
          className="px-3 py-2 text-[11px]"
          style={{ color: EMPTY_TABLE_FG }}
        >
          Per-student detail isn&rsquo;t available for this school — showing
          assessment-level totals from the cube.
        </p>
      </div>
    );
  }

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
            {spans.map((s, i) => (
              <th
                key={`${s.cpalms}-${i}`}
                colSpan={s.span}
                className="border-r border-b text-center font-semibold px-2 py-1"
                style={{
                  backgroundColor: PBIX_ACCENT_NAVY,
                  color: '#fff',
                  borderColor: LAYOUT_BORDER,
                }}
                title={s.cpalms}
              >
                {s.cpalms}
              </th>
            ))}
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
              <SortableHeader column="instructor" label="Classroom Instructors" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th
              scope="col"
              className="border-r border-b text-left px-2 py-1"
              style={{ backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER }}
            >
              <SortableHeader column="student" label="Student Name" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th
              scope="col"
              className="border-r border-b text-right px-2 py-1"
              style={{ backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER }}
            >
              <SortableHeader column="score" label="Score %" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="right" />
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
          {orderedGroups.map((group: QsmTeacherGroup) => {
            const students = orderStudents(group.students);
            return (
            <Fragment key={group.section_instructor}>
              {students.map((student, idx) => (
                <tr
                  key={student.user_uid}
                  className="border-b"
                  style={{ borderColor: LAYOUT_BORDER }}
                >
                  {idx === 0 ? (
                    <td
                      rowSpan={
                        group.students.length + (showTeacherSubtotal ? 2 : 0)
                      }
                      className="border-r px-2 py-1 align-top font-semibold"
                      style={{
                        borderColor: LAYOUT_BORDER,
                        backgroundColor: HEADER_BAR_BG,
                      }}
                    >
                      <div>
                        {redacted
                          ? redactName(group.section_instructor, 'Instructor')
                          : group.section_instructor}
                      </div>
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
                    {redacted
                      ? redactName(student.user_uid, 'Student')
                      : student.user_name}
                  </th>
                  <td
                    className="border-r px-2 py-1 text-right tabular-nums font-semibold"
                    style={{
                      borderColor: LAYOUT_BORDER,
                      backgroundColor: qsrPerformanceColor(student.score_pct),
                    }}
                  >
                    {pct(student.score_pct)}
                  </td>
                  {questions.map((q) => {
                    const cell = student.cells[q.question_id] ?? null;
                    const bg = cell === null ? '#fff' : qsrCellColor(cell);
                    const aria =
                      cell === null
                        ? 'not attempted'
                        : cell >= 0.5
                          ? 'correct'
                          : 'incorrect';
                    return (
                      <td
                        key={q.question_id}
                        className="border-r px-1 py-0.5 text-center font-semibold tabular-nums"
                        style={{
                          backgroundColor: bg ?? '#fff',
                          color: '#000',
                          borderColor: LAYOUT_BORDER,
                        }}
                        aria-label={`${q.question_no} ${aria}`}
                      >
                        {cell === null ? '—' : pts(cell)}
                      </td>
                    );
                  })}
                  <td
                    className="border-r px-2 py-1 text-right tabular-nums"
                    style={{ borderColor: LAYOUT_BORDER }}
                  >
                    {pts(student.possible_points)}
                  </td>
                  <td
                    className="px-2 py-1 text-right tabular-nums"
                    style={{ borderColor: LAYOUT_BORDER }}
                  >
                    {pts(student.correct_count)}
                  </td>
                </tr>
              ))}
              {showTeacherSubtotal &&
                (() => {
                  // Legacy "- Teacher" two-row subtotal block (PBIX ord 7):
                  // a "# Correct Answers" row (per-question SUM(points_received))
                  // and a "Score %" row (per-question SUM(recv)/SUM(poss),
                  // 3-band colored), both nested inside the teacher group before
                  // the next teacher. Partial-credit, matching the legacy SSRS.
                  const teacherCorrect = group.students.reduce(
                    (acc, s) => acc + s.correct_count,
                    0,
                  );
                  const perQ = questions.map((q) => {
                    const possible =
                      group.per_question_possible[q.question_id] ?? 0;
                    const correct =
                      group.per_question_correct[q.question_id] ?? 0;
                    return {
                      qid: q.question_id,
                      correct,
                      attempted: possible,
                      pct: group.per_question_pct[q.question_id] ?? 0,
                    };
                  });
                  return (
                    <Fragment key={`${group.section_instructor}-subtotal`}>
                      <tr
                        className="border-b font-semibold"
                        style={{
                          borderColor: LAYOUT_BORDER,
                          backgroundColor: PBIX_ACCENT_LIGHT_BLUE,
                        }}
                      >
                        <td
                          className="border-r px-2 py-1"
                          style={{ borderColor: LAYOUT_BORDER }}
                        >
                          # Correct Answers
                        </td>
                        <td
                          className="border-r px-2 py-1 text-right tabular-nums"
                          style={{ borderColor: LAYOUT_BORDER }}
                        >
                          {pts(teacherCorrect)}
                        </td>
                        {perQ.map((p) => (
                          <td
                            key={`sub-cc-${p.qid}`}
                            className="border-r px-1 py-0.5 text-center tabular-nums"
                            style={{ borderColor: LAYOUT_BORDER }}
                          >
                            {p.attempted > 0 ? pts(p.correct) : '—'}
                          </td>
                        ))}
                        <td
                          className="border-r"
                          style={{ borderColor: LAYOUT_BORDER }}
                        />
                        <td style={{ borderColor: LAYOUT_BORDER }} />
                      </tr>
                      <tr
                        className="border-b font-semibold"
                        style={{
                          borderColor: LAYOUT_BORDER,
                          backgroundColor: PBIX_ACCENT_LIGHT_BLUE,
                        }}
                      >
                        <td
                          className="border-r px-2 py-1"
                          style={{ borderColor: LAYOUT_BORDER }}
                        >
                          Score %
                        </td>
                        <td
                          className="border-r px-2 py-1 text-right tabular-nums"
                          style={{
                            borderColor: LAYOUT_BORDER,
                            backgroundColor: qsrPerformanceColor(
                              group.teacher_score_pct,
                            ),
                          }}
                        >
                          {pct(group.teacher_score_pct)}
                        </td>
                        {perQ.map((p) => (
                          <td
                            key={`sub-pct-${p.qid}`}
                            className="border-r px-1 py-0.5 text-center tabular-nums"
                            style={{
                              borderColor: LAYOUT_BORDER,
                              backgroundColor:
                                p.attempted > 0
                                  ? qsrPerformanceColor(p.pct)
                                  : undefined,
                            }}
                          >
                            {p.attempted > 0 ? pct(p.pct) : '—'}
                          </td>
                        ))}
                        <td
                          className="border-r"
                          style={{ borderColor: LAYOUT_BORDER }}
                        />
                        <td style={{ borderColor: LAYOUT_BORDER }} />
                      </tr>
                    </Fragment>
                  );
                })()}
            </Fragment>
            );
          })}

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
              {pts(grandTotal.possible_points)}
            </td>
            {questions.map((q) => (
              <td
                key={`pp-${q.question_id}`}
                className="border-r px-1 py-1 text-center tabular-nums"
                style={{ borderColor: LAYOUT_BORDER }}
              >
                {pts(grandTotal.per_question_possible[q.question_id] ?? 0)}
              </td>
            ))}
            <td
              className="border-r px-2 py-1 text-right tabular-nums"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              {pts(grandTotal.possible_points)}
            </td>
            <td
              className="px-2 py-1 text-right tabular-nums"
              style={{ borderColor: LAYOUT_BORDER }}
            >
              {pts(grandTotal.correct_count)}
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
              {pts(grandTotal.correct_count)}
            </td>
            {questions.map((q) => (
              <td
                key={`cc-${q.question_id}`}
                className="border-r px-1 py-1 text-center tabular-nums"
                style={{ borderColor: LAYOUT_BORDER }}
              >
                {pts(grandTotal.per_question_correct[q.question_id] ?? 0)}
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
                backgroundColor: qsrPerformanceColor(grandTotal.score_pct),
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
                    backgroundColor: qsrPerformanceColor(p),
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
