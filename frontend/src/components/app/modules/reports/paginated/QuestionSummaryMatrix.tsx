'use client';

import { Fragment, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { MinusCircle, PlusCircle } from 'lucide-react';
import ScrollableTableContainer from '../shared/ScrollableTableContainer';
import {
  stickyHeaderStyle,
  stickyLeftStyle,
  QSM_LABEL_COLS,
  QSM_LEFT,
} from '../shared/tableStyles';
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
  QSR_HEADER_HILITE_FG,
  QSR_POINTS_GREY,
  QSR_TEACHER_BAND,
  qsrCellColor,
  qsrHeaderBandColor,
  qsrPerformanceColor,
} from '@/lib/reports/colors';
import { sanitizeShortAnswer } from '@/lib/reports/format';
import HeaderTooltip from '@/components/app/modules/reports/shared/HeaderTooltip';
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
  /**
   * Legacy "Header Highlights" variant (PBIX ord 16 / "...- color.rdl"). The
   * ONLY change vs base: the two header bands (standard-code row + Question-No
   * row) are performance-colored (3-band 0.6/0.8 pink/yellow/green, silver text)
   * instead of solid navy/blue. Data-cell coloring is identical to base.
   */
  headerHighlights?: boolean;
}

function pct(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
}

// The per-teacher group header shows ONE decimal (e.g. 77.8%) to match the
// legacy SSRS "Question Summary Report - Teacher" PDF, where the instructor
// subtotal beside the name is precise while the per-cell Score% row stays
// whole-number.
function pct1(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
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
  headerHighlights = false,
}: Props) {
  const {
    questions,
    teacher_groups: teacherGroups,
    grand_total: grandTotal,
    per_student_available: perStudentAvailable = true,
  } = payload;

  // The 2nd header row sticks below the 1st; its `top` offset must equal the
  // rendered height of row 1 (which varies with the +/- toggle / font / zoom),
  // so we measure it live instead of hardcoding.
  const row1Ref = useRef<HTMLTableRowElement>(null);
  const [row1H, setRow1H] = useState(25);
  useLayoutEffect(() => {
    const el = row1Ref.current;
    if (!el) return;
    setRow1H(el.offsetHeight);
    const ro = new ResizeObserver(() => setRow1H(el.offsetHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const spans = useMemo(() => buildStandardSpans(questions), [questions]);

  // Per-standard "Score %" drill: each standard-code header carries a +/-
  // toggle. When expanded, a per-standard Score% column is appended right after
  // that standard's question columns (the "summary of the questions within that
  // standard"). Default = collapsed (questions only), so the base layout is
  // unchanged. Every header/data/subtotal/footer row iterates the SAME `columns`
  // model below, which is the single invariant that keeps the columns aligned.
  const [expandedStandards, setExpandedStandards] = useState<Set<string>>(
    () => new Set(),
  );
  const toggleStandard = (code: string) =>
    setExpandedStandards((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });

  type MatrixCol =
    | { kind: 'q'; q: QsmQuestionColumn; code: string }
    | { kind: 'score'; code: string; span: StandardSpan };
  const columns = useMemo<MatrixCol[]>(() => {
    const out: MatrixCol[] = [];
    for (const s of spans) {
      for (const q of s.questions) out.push({ kind: 'q', q, code: s.cpalms });
      if (expandedStandards.has(s.cpalms)) {
        out.push({ kind: 'score', code: s.cpalms, span: s });
      }
    }
    return out;
  }, [spans, expandedStandards]);

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
                <HeaderTooltip title="Score Percent" description="Assessment-level percent score (points earned / points possible).">Score %</HeaderTooltip>
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
                <HeaderTooltip title="Possible Points" description="Maximum points obtainable for the assessment.">Possible Points</HeaderTooltip>
              </th>
              <th
                scope="col"
                className="border-r border-b text-right px-2 py-1"
                style={{
                  backgroundColor: PBIX_ACCENT_LIGHT_BLUE,
                  borderColor: LAYOUT_BORDER,
                }}
              >
                <HeaderTooltip title="Number of Correct Answers" description="Count of correct answers / points earned for the assessment."># Correct Answers</HeaderTooltip>
              </th>
              <th
                scope="col"
                className="border-b text-right px-2 py-1"
                style={{
                  backgroundColor: PBIX_ACCENT_LIGHT_BLUE,
                  borderColor: LAYOUT_BORDER,
                }}
              >
                <HeaderTooltip title="Score Percent" description="Assessment-level percent score (points earned / points possible).">Score %</HeaderTooltip>
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
    <ScrollableTableContainer
      className="bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <table className="report-wide-matrix min-w-full text-[11px] border-collapse">
        <colgroup>
          <col style={{ width: QSM_LABEL_COLS.instructor }} />
          <col style={{ width: QSM_LABEL_COLS.student }} />
          <col style={{ width: QSM_LABEL_COLS.score }} />
        </colgroup>
        <thead>
          {/* Standard code row */}
          <tr ref={row1Ref}>
            <th
              colSpan={3}
              className="border-r border-b text-left text-white px-2 py-1"
              style={stickyHeaderStyle(
                { backgroundColor: PBIX_ACCENT_NAVY, borderColor: LAYOUT_BORDER },
                { top: 0, left: 0, border: LAYOUT_BORDER },
              )}
            >
              Standards
            </th>
            {spans.map((s, i) => {
              // Header Highlights variant: color the standard-code band by the
              // standard's aggregate Score% (Total_Score / Total_Possible over
              // its questions) — legacy RDL `Standards1` 0.6/0.8 IIf.
              let bg = PBIX_ACCENT_NAVY;
              let fg = '#fff';
              if (headerHighlights) {
                const poss = s.questions.reduce(
                  (a, q) => a + (grandTotal.per_question_possible[q.question_id] ?? 0),
                  0,
                );
                const corr = s.questions.reduce(
                  (a, q) => a + (grandTotal.per_question_correct[q.question_id] ?? 0),
                  0,
                );
                const band = qsrHeaderBandColor(poss > 0 ? corr / poss : null);
                if (band) {
                  bg = band;
                  fg = QSR_HEADER_HILITE_FG;
                }
              }
              const isExp = expandedStandards.has(s.cpalms);
              return (
                <th
                  key={`${s.cpalms}-${i}`}
                  colSpan={s.span + (isExp ? 1 : 0)}
                  className="border-r border-b text-center font-semibold px-2 py-1"
                  style={stickyHeaderStyle(
                    { backgroundColor: bg, color: fg, borderColor: LAYOUT_BORDER },
                    { top: 0, border: LAYOUT_BORDER },
                  )}
                  title={s.cpalms}
                >
                  <span className="inline-flex items-center justify-center gap-1">
                    <span>{s.cpalms}</span>
                    <button
                      type="button"
                      onClick={() => toggleStandard(s.cpalms)}
                      aria-expanded={isExp}
                      aria-label={
                        isExp
                          ? `Hide Score % for ${s.cpalms}`
                          : `Show Score % for ${s.cpalms}`
                      }
                      title={isExp ? 'Hide standard Score %' : 'Show standard Score %'}
                      className="print:hidden inline-flex items-center justify-center rounded-full p-0.5 align-middle text-current opacity-70 transition hover:bg-current/20 hover:opacity-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-current cursor-pointer"
                    >
                      {isExp ? (
                        <MinusCircle className="h-3.5 w-3.5" aria-hidden="true" />
                      ) : (
                        <PlusCircle className="h-3.5 w-3.5" aria-hidden="true" />
                      )}
                    </button>
                  </span>
                </th>
              );
            })}
            <th
              colSpan={2}
              className="border-l border-b text-white px-2 py-1 text-center"
              style={stickyHeaderStyle(
                { backgroundColor: PBIX_ACCENT_NAVY, borderColor: LAYOUT_BORDER },
                { top: 0, border: LAYOUT_BORDER },
              )}
            >
              Totals
            </th>
          </tr>
          {/* Question No row */}
          <tr>
            <th
              scope="col"
              className="border-r border-b text-left px-2 py-1"
              style={stickyHeaderStyle(
                { backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER },
                { top: row1H, left: QSM_LEFT.instructor, border: LAYOUT_BORDER },
              )}
            >
              <SortableHeader column="instructor" label="Classroom Instructors" title="Classroom Instructors" description="Section instructor who taught the student; rows are grouped by this." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th
              scope="col"
              className="border-r border-b text-left px-2 py-1"
              style={stickyHeaderStyle(
                { backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER },
                { top: row1H, left: QSM_LEFT.student, border: LAYOUT_BORDER },
              )}
            >
              <SortableHeader column="student" label="Student Name" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} />
            </th>
            <th
              scope="col"
              className="border-r border-b text-right px-2 py-1"
              style={stickyHeaderStyle(
                { backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER },
                { top: row1H, left: QSM_LEFT.score, border: LAYOUT_BORDER },
              )}
            >
              <SortableHeader column="score" label="Score %" title="Score Percent" description="Student's overall percent score on the assessment (points earned / points possible)." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="right" />
            </th>
            {columns.map((col, ci) => {
              if (col.kind === 'q') {
                const q = col.q;
                // Header Highlights variant: color the Question-No header by the
                // question's Score% — legacy RDL `Question_No` 0.6/0.8 IIf.
                let bg = PBIX_ACCENT_LIGHT_BLUE;
                let fg: string | undefined;
                if (headerHighlights) {
                  const band = qsrHeaderBandColor(
                    grandTotal.per_question_pct[q.question_id] ?? null,
                  );
                  if (band) {
                    bg = band;
                    fg = QSR_HEADER_HILITE_FG;
                  }
                }
                return (
                  <th
                    key={q.question_id}
                    scope="col"
                    className="border-r border-b text-center px-1 py-1 font-semibold"
                    style={stickyHeaderStyle(
                      { backgroundColor: bg, color: fg, borderColor: LAYOUT_BORDER },
                      { top: row1H, border: LAYOUT_BORDER },
                    )}
                    title={`${q.question_no}: ${sanitizeShortAnswer(q.correct_answer) || 'n/a'}`}
                  >
                    {q.question_no}
                  </th>
                );
              }
              // Per-standard Score% sub-header (matches the standard band color
              // in the header-highlights variant).
              let bg = PBIX_ACCENT_LIGHT_BLUE;
              let fg: string | undefined;
              if (headerHighlights) {
                const band = qsrHeaderBandColor(grandTotal.band_pct[col.code] ?? null);
                if (band) {
                  bg = band;
                  fg = QSR_HEADER_HILITE_FG;
                }
              }
              return (
                <th
                  key={`hscore-${col.code}-${ci}`}
                  scope="col"
                  className="border-r border-b text-center px-1 py-1 font-semibold"
                  style={stickyHeaderStyle(
                    { backgroundColor: bg, color: fg, borderColor: LAYOUT_BORDER },
                    { top: row1H, border: LAYOUT_BORDER },
                  )}
                >
                  <HeaderTooltip
                    title="Score Percent"
                    description={`Score % across the ${col.code} questions (points earned / points possible).`}
                  >
                    Score %
                  </HeaderTooltip>
                </th>
              );
            })}
            <th
              scope="col"
              className="border-r border-b text-right px-2 py-1"
              style={stickyHeaderStyle(
                { backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER },
                { top: row1H, border: LAYOUT_BORDER },
              )}
            >
              <HeaderTooltip title="Possible Points" description="Maximum points obtainable across all questions for this student.">Possible Points</HeaderTooltip>
            </th>
            <th
              scope="col"
              className="border-b text-right px-2 py-1"
              style={stickyHeaderStyle(
                { backgroundColor: PBIX_ACCENT_LIGHT_BLUE, borderColor: LAYOUT_BORDER },
                { top: row1H, border: LAYOUT_BORDER },
              )}
            >
              <HeaderTooltip title="Number of Correct Answers" description="Count of points the student earned across all questions."># Correct Answers</HeaderTooltip>
            </th>
          </tr>
        </thead>
        <tbody>
          {orderedGroups.map((group: QsmTeacherGroup) => {
            const students = orderStudents(group.students);
            // Classroom Instructor group cell fill, per legacy SSRS variant:
            //  - "- Teacher" (subtotal) variant → light blue #d9ecff
            //  - "- color" (header-highlights) variant → 3-band by teacher score
            //  - base → white
            const instructorBg = showTeacherSubtotal
              ? QSR_TEACHER_BAND
              : headerHighlights
                ? qsrPerformanceColor(group.teacher_score_pct)
                : '#ffffff';
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
                      className="border-r px-2 py-1 align-top font-semibold overflow-hidden"
                      style={stickyLeftStyle(
                        {
                          borderColor: LAYOUT_BORDER,
                          backgroundColor: instructorBg,
                        },
                        {
                          left: QSM_LEFT.instructor,
                          background: instructorBg,
                          border: LAYOUT_BORDER,
                        },
                      )}
                    >
                      <div className="truncate">
                        {redacted
                          ? redactName(group.section_instructor, 'Instructor')
                          : group.section_instructor}
                      </div>
                      <div className="text-[10px] text-neutral-700">
                        {pct1(group.teacher_score_pct)}
                      </div>
                    </td>
                  ) : null}
                  <th
                    scope="row"
                    className="border-r px-2 py-1 truncate max-w-[170px] text-left font-normal"
                    style={stickyLeftStyle(
                      {
                        borderColor: LAYOUT_BORDER,
                        // Legacy SSRS bands the Student Name cell by the student's
                        // Score % (pink/yellow/green), same as the Score % column —
                        // not white. Verbatim from the legacy QSR PDFs.
                        backgroundColor: qsrPerformanceColor(student.score_pct),
                      },
                      {
                        left: QSM_LEFT.student,
                        background: qsrPerformanceColor(student.score_pct),
                        border: LAYOUT_BORDER,
                      },
                    )}
                  >
                    {redacted
                      ? redactName(student.user_uid, 'Student')
                      : student.user_name}
                  </th>
                  <td
                    className="border-r px-2 py-1 text-right tabular-nums font-semibold"
                    style={stickyLeftStyle(
                      {
                        borderColor: LAYOUT_BORDER,
                        backgroundColor: qsrPerformanceColor(student.score_pct),
                      },
                      {
                        left: QSM_LEFT.score,
                        background: qsrPerformanceColor(student.score_pct),
                        border: LAYOUT_BORDER,
                      },
                    )}
                  >
                    {pct(student.score_pct)}
                  </td>
                  {columns.map((col, ci) => {
                    if (col.kind === 'q') {
                      const q = col.q;
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
                    }
                    const sp = student.band_pct[col.code] ?? null;
                    return (
                      <td
                        key={`score-${col.code}-${ci}`}
                        className="border-r px-1 py-0.5 text-center font-semibold tabular-nums"
                        style={{
                          backgroundColor: sp === null ? '#fff' : qsrPerformanceColor(sp),
                          color: '#000',
                          borderColor: LAYOUT_BORDER,
                        }}
                        aria-label={`${col.code} score`}
                      >
                        {sp === null ? '—' : pct(sp)}
                      </td>
                    );
                  })}
                  <td
                    className="border-r px-2 py-1 text-right tabular-nums"
                    style={{
                      borderColor: LAYOUT_BORDER,
                      backgroundColor: QSR_POINTS_GREY,
                    }}
                  >
                    {pts(student.possible_points)}
                  </td>
                  <td
                    className="px-2 py-1 text-right tabular-nums"
                    style={{
                      borderColor: LAYOUT_BORDER,
                      backgroundColor: QSR_POINTS_GREY,
                    }}
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
                  const bandPoss = (span: StandardSpan) =>
                    span.questions.reduce(
                      (a, q) => a + (group.per_question_possible[q.question_id] ?? 0),
                      0,
                    );
                  const bandCorr = (span: StandardSpan) =>
                    span.questions.reduce(
                      (a, q) => a + (group.per_question_correct[q.question_id] ?? 0),
                      0,
                    );
                  return (
                    <Fragment key={`${group.section_instructor}-subtotal`}>
                      <tr
                        className="border-b font-semibold"
                        style={{
                          borderColor: LAYOUT_BORDER,
                          backgroundColor: QSR_TEACHER_BAND,
                        }}
                      >
                        <td
                          className="border-r px-2 py-1"
                          style={stickyLeftStyle(
                            { borderColor: LAYOUT_BORDER },
                            {
                              left: QSM_LEFT.student,
                              background: QSR_TEACHER_BAND,
                              border: LAYOUT_BORDER,
                            },
                          )}
                        >
                          # Correct Answers
                        </td>
                        <td
                          className="border-r px-2 py-1 text-right tabular-nums"
                          style={stickyLeftStyle(
                            { borderColor: LAYOUT_BORDER },
                            {
                              left: QSM_LEFT.score,
                              background: QSR_TEACHER_BAND,
                              border: LAYOUT_BORDER,
                            },
                          )}
                        >
                          {pts(teacherCorrect)}
                        </td>
                        {columns.map((col, ci) => {
                          if (col.kind === 'q') {
                            const possible =
                              group.per_question_possible[col.q.question_id] ?? 0;
                            const correct =
                              group.per_question_correct[col.q.question_id] ?? 0;
                            return (
                              <td
                                key={`sub-cc-${col.q.question_id}`}
                                className="border-r px-1 py-0.5 text-center tabular-nums"
                                style={{ borderColor: LAYOUT_BORDER }}
                              >
                                {possible > 0 ? pts(correct) : '—'}
                              </td>
                            );
                          }
                          const poss = bandPoss(col.span);
                          return (
                            <td
                              key={`sub-cc-score-${col.code}-${ci}`}
                              className="border-r px-1 py-0.5 text-center tabular-nums"
                              style={{ borderColor: LAYOUT_BORDER }}
                            >
                              {poss > 0 ? pts(bandCorr(col.span)) : '—'}
                            </td>
                          );
                        })}
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
                          backgroundColor: QSR_TEACHER_BAND,
                        }}
                      >
                        <td
                          className="border-r px-2 py-1"
                          style={stickyLeftStyle(
                            { borderColor: LAYOUT_BORDER },
                            {
                              left: QSM_LEFT.student,
                              background: QSR_TEACHER_BAND,
                              border: LAYOUT_BORDER,
                            },
                          )}
                        >
                          Score %
                        </td>
                        <td
                          className="border-r px-2 py-1 text-right tabular-nums"
                          style={stickyLeftStyle(
                            {
                              borderColor: LAYOUT_BORDER,
                              backgroundColor: qsrPerformanceColor(
                                group.teacher_score_pct,
                              ),
                            },
                            {
                              left: QSM_LEFT.score,
                              background: qsrPerformanceColor(
                                group.teacher_score_pct,
                              ),
                              border: LAYOUT_BORDER,
                            },
                          )}
                        >
                          {pct(group.teacher_score_pct)}
                        </td>
                        {columns.map((col, ci) => {
                          if (col.kind === 'q') {
                            const possible =
                              group.per_question_possible[col.q.question_id] ?? 0;
                            const p =
                              group.per_question_pct[col.q.question_id] ?? 0;
                            return (
                              <td
                                key={`sub-pct-${col.q.question_id}`}
                                className="border-r px-1 py-0.5 text-center tabular-nums"
                                style={{
                                  borderColor: LAYOUT_BORDER,
                                  backgroundColor:
                                    possible > 0 ? qsrPerformanceColor(p) : undefined,
                                }}
                              >
                                {possible > 0 ? pct(p) : '—'}
                              </td>
                            );
                          }
                          const poss = bandPoss(col.span);
                          const p = poss > 0 ? bandCorr(col.span) / poss : 0;
                          return (
                            <td
                              key={`sub-pct-score-${col.code}-${ci}`}
                              className="border-r px-1 py-0.5 text-center tabular-nums"
                              style={{
                                borderColor: LAYOUT_BORDER,
                                backgroundColor:
                                  poss > 0 ? qsrPerformanceColor(p) : undefined,
                              }}
                            >
                              {poss > 0 ? pct(p) : '—'}
                            </td>
                          );
                        })}
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
              backgroundColor: QSR_POINTS_GREY,
            }}
          >
            <td
              className="border-r px-2 py-1"
              style={stickyLeftStyle(
                { borderColor: LAYOUT_BORDER },
                {
                  left: QSM_LEFT.instructor,
                  background: QSR_POINTS_GREY,
                  border: LAYOUT_BORDER,
                },
              )}
            >
              Possible Points
            </td>
            <td
              className="border-r"
              style={stickyLeftStyle(
                { borderColor: LAYOUT_BORDER },
                {
                  left: QSM_LEFT.student,
                  background: QSR_POINTS_GREY,
                  border: LAYOUT_BORDER,
                },
              )}
            />
            <td
              className="border-r px-2 py-1 text-right tabular-nums"
              style={stickyLeftStyle(
                { borderColor: LAYOUT_BORDER },
                {
                  left: QSM_LEFT.score,
                  background: QSR_POINTS_GREY,
                  border: LAYOUT_BORDER,
                },
              )}
            >
              {pts(grandTotal.possible_points)}
            </td>
            {columns.map((col, ci) =>
              col.kind === 'q' ? (
                <td
                  key={`pp-${col.q.question_id}`}
                  className="border-r px-1 py-1 text-center tabular-nums"
                  style={{ borderColor: LAYOUT_BORDER }}
                >
                  {pts(grandTotal.per_question_possible[col.q.question_id] ?? 0)}
                </td>
              ) : (
                <td
                  key={`pp-score-${col.code}-${ci}`}
                  className="border-r px-1 py-1 text-center tabular-nums"
                  style={{ borderColor: LAYOUT_BORDER }}
                >
                  {pts(grandTotal.band_possible[col.code] ?? 0)}
                </td>
              ),
            )}
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
              backgroundColor: QSR_POINTS_GREY,
            }}
          >
            <td
              className="border-r px-2 py-1"
              style={stickyLeftStyle(
                { borderColor: LAYOUT_BORDER },
                {
                  left: QSM_LEFT.instructor,
                  background: QSR_POINTS_GREY,
                  border: LAYOUT_BORDER,
                },
              )}
            >
              # Correct Answers
            </td>
            <td
              className="border-r"
              style={stickyLeftStyle(
                { borderColor: LAYOUT_BORDER },
                {
                  left: QSM_LEFT.student,
                  background: QSR_POINTS_GREY,
                  border: LAYOUT_BORDER,
                },
              )}
            />
            <td
              className="border-r px-2 py-1 text-right tabular-nums"
              style={stickyLeftStyle(
                { borderColor: LAYOUT_BORDER },
                {
                  left: QSM_LEFT.score,
                  background: QSR_POINTS_GREY,
                  border: LAYOUT_BORDER,
                },
              )}
            >
              {pts(grandTotal.correct_count)}
            </td>
            {columns.map((col, ci) =>
              col.kind === 'q' ? (
                <td
                  key={`cc-${col.q.question_id}`}
                  className="border-r px-1 py-1 text-center tabular-nums"
                  style={{ borderColor: LAYOUT_BORDER }}
                >
                  {pts(grandTotal.per_question_correct[col.q.question_id] ?? 0)}
                </td>
              ) : (
                <td
                  key={`cc-score-${col.code}-${ci}`}
                  className="border-r px-1 py-1 text-center tabular-nums"
                  style={{ borderColor: LAYOUT_BORDER }}
                >
                  {pts(grandTotal.band_correct[col.code] ?? 0)}
                </td>
              ),
            )}
            <td className="border-r" style={{ borderColor: LAYOUT_BORDER }} />
            <td style={{ borderColor: LAYOUT_BORDER }} />
          </tr>
          <tr
            className="font-semibold"
            style={{ backgroundColor: QSR_POINTS_GREY }}
          >
            <td
              className="border-r px-2 py-1"
              style={stickyLeftStyle(
                { borderColor: LAYOUT_BORDER },
                {
                  left: QSM_LEFT.instructor,
                  background: QSR_POINTS_GREY,
                  border: LAYOUT_BORDER,
                },
              )}
            >
              Score %
            </td>
            <td
              className="border-r"
              style={stickyLeftStyle(
                { borderColor: LAYOUT_BORDER },
                {
                  left: QSM_LEFT.student,
                  background: QSR_POINTS_GREY,
                  border: LAYOUT_BORDER,
                },
              )}
            />
            <td
              className="border-r px-2 py-1 text-right tabular-nums"
              style={stickyLeftStyle(
                {
                  borderColor: LAYOUT_BORDER,
                  backgroundColor: qsrPerformanceColor(grandTotal.score_pct),
                },
                {
                  left: QSM_LEFT.score,
                  background: qsrPerformanceColor(grandTotal.score_pct),
                  border: LAYOUT_BORDER,
                },
              )}
            >
              {pct(grandTotal.score_pct)}
            </td>
            {columns.map((col, ci) => {
              const p =
                col.kind === 'q'
                  ? grandTotal.per_question_pct[col.q.question_id] ?? 0
                  : grandTotal.band_pct[col.code] ?? 0;
              return (
                <td
                  key={
                    col.kind === 'q'
                      ? `pct-${col.q.question_id}`
                      : `pct-score-${col.code}-${ci}`
                  }
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
    </ScrollableTableContainer>
  );
}
