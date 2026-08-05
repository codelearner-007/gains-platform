// Client-side CSV export for GAINS reports — ZERO new dependencies.
//
// `reportToCsv(kind, payload)` is a typed registry of pure flatteners, one per
// report kind, each producing rows at the SAME visible grain the report shows
// on screen (plan §3.2). The serialized string is RFC-4180 quoted, prefixed
// with a UTF-8 BOM (so Excel detects UTF-8), and uses CRLF line endings.
//
// HTML/LaTeX answer cells are reduced to plain text via the shared
// `format.ts` helpers (`sanitizeShortAnswer` collapses image URLs to
// `[image]`); images are otherwise dropped. Download is a Blob + a temporary
// `<a download>` anchor — no file-saver dependency.

import {
  formatPercent,
  sanitizeShortAnswer,
  splitStandards,
} from './format';
import type {
  ForwardViewPayload,
  IncorrectAnswerDetailsPayload,
  PaginatedQuestionRow,
  QraByStandardTeacherPayload,
  QraByTeacherPayload,
  QraPaginatedPayload,
  QuestionResponseAnalysisPayload,
  QuestionSummaryMatrixPayload,
  StandardSummaryPayload,
  StandardsDeepDivePayload,
  StrandSummaryPayload,
  YearToDatePerformancePayload,
} from './types';

/** Report kinds that have a CSV flattener. Matches the report endpoints. */
export type ReportKind =
  | 'qra'
  | 'qra-paginated'
  | 'qra-by-teacher'
  | 'qra-by-standard-teacher'
  | 'qsr'
  | 'ytd'
  | 'standard-summary'
  | 'strand-summary'
  | 'forward-view'
  | 'sdd'
  | 'iad';

// ─── Plain-text helpers ─────────────────────────────────────────────────────

const HTML_ENTITIES: Record<string, string> = {
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&nbsp;': ' ',
};

/**
 * Reduce an HTML/rich cell (question text, descriptions) to plain text:
 * collapse `<br>` to spaces, strip every tag, decode common entities, and
 * route any embedded image URLs through `sanitizeShortAnswer` so they become
 * `[image]` rather than a raw link.
 */
function htmlToPlainText(raw: string | null | undefined): string {
  if (!raw) return '';
  // Collapse Schoology image tokens (bare or angle-bracketed URLs) to
  // `[image]` BEFORE tag-stripping — the `<https://…>` token format would
  // otherwise be eaten by the `<...>` tag regex below.
  const withImageTokens = sanitizeShortAnswer(String(raw));
  const withBreaks = withImageTokens
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<\/p>/gi, ' ');
  const stripped = withBreaks.replace(/<[^>]+>/g, ' ');
  const decoded = stripped.replace(
    /&amp;|&lt;|&gt;|&quot;|&#39;|&nbsp;/g,
    (m) => HTML_ENTITIES[m] ?? m,
  );
  return decoded.replace(/\s+/g, ' ').trim();
}

/** Multi-line standards joined onto one cell, "; "-separated. */
function joinStandards(raw: string | null | undefined): string {
  return splitStandards(raw).join('; ');
}

/** Percent from a 0–1 fraction; blank when not finite. */
function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return '';
  }
  return formatPercent(value, digits);
}

/** Numeric → string, blank for null/undefined/NaN. */
function num(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return '';
  }
  return String(value);
}

// ─── RFC-4180 serialization ─────────────────────────────────────────────────

const BOM = '﻿';
const CRLF = '\r\n';

function csvField(value: string | number | null | undefined): string {
  const s =
    value === null || value === undefined ? '' : String(value);
  // Quote when the field contains a comma, double-quote, CR, or LF.
  if (/[",\r\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/** Serialize a matrix of rows to an RFC-4180 CSV string with BOM + CRLF. */
export function rowsToCsv(rows: (string | number | null | undefined)[][]): string {
  const body = rows
    .map((row) => row.map(csvField).join(','))
    .join(CRLF);
  return `${BOM}${body}${CRLF}`;
}

// ─── Per-report flatteners (visible grain) ──────────────────────────────────

type CsvRow = (string | number | null | undefined)[];

/**
 * QRA interactive / QRA-paginated share the on-screen question grain:
 * one row per question. Both carry `incorrect_choice_details` +
 * `incorrect_details_name`; the paginated payload's column names match.
 */
function questionRowsToCsv(
  questions: {
    question_no: string;
    question: string;
    standards: string;
    correct_answer: string;
    grade_average: number;
    incorrect_choice_details: string;
    incorrect_details_name: string;
    percentage_incorrect?: number;
  }[],
): string {
  const header: CsvRow = [
    'Question No',
    'Question',
    'Standards',
    'Correct Answer',
    'Grade Average %',
    '% Incorrect',
    'Incorrect Choices',
    'Incorrect Choice Students',
  ];
  const rows: CsvRow[] = [header];
  for (const q of questions) {
    const incorrectPct =
      q.percentage_incorrect !== undefined
        ? pct(q.percentage_incorrect)
        : q.grade_average >= 1
          ? pct(0)
          : pct(1 - q.grade_average);
    rows.push([
      q.question_no,
      htmlToPlainText(q.question),
      joinStandards(q.standards),
      htmlToPlainText(q.correct_answer),
      pct(q.grade_average),
      incorrectPct,
      q.grade_average >= 1 ? '' : htmlToPlainText(q.incorrect_choice_details),
      q.grade_average >= 1 ? '' : htmlToPlainText(q.incorrect_details_name),
    ]);
  }
  return rowsToCsv(rows);
}

function qraToCsv(p: QuestionResponseAnalysisPayload): string {
  return questionRowsToCsv(p.questions_overall);
}

function qraPaginatedToCsv(p: QraPaginatedPayload): string {
  return paginatedQuestionRowsToCsv(p.questions);
}

/** Paginated question rows carry the same fields under matching names. */
function paginatedQuestionRowsToCsv(rows: PaginatedQuestionRow[]): string {
  return questionRowsToCsv(
    rows.map((r) => ({
      question_no: r.question_no,
      question: r.question,
      standards: r.standards,
      correct_answer: r.correct_answer,
      grade_average: r.grade_average,
      incorrect_choice_details: r.incorrect_choice_details,
      incorrect_details_name: r.incorrect_details_name,
    })),
  );
}

/**
 * QRA-by-teacher: group-header rows (instructor + teacher average) followed by
 * that group's question member rows, mirroring on-screen grouping.
 */
function qraByTeacherToCsv(p: QraByTeacherPayload): string {
  const header: CsvRow = [
    'Group',
    'Question No',
    'Question',
    'Standards',
    'Correct Answer',
    'Grade Average %',
  ];
  const rows: CsvRow[] = [header];
  for (const g of p.teacher_groups) {
    rows.push([
      `Teacher: ${g.section_instructor}`,
      '',
      '',
      '',
      '',
      g.teacher_grade_average_pct || pct(g.teacher_grade_average),
    ]);
    for (const q of g.questions) {
      rows.push([
        '',
        q.question_no,
        htmlToPlainText(q.question),
        joinStandards(q.standards),
        htmlToPlainText(q.correct_answer),
        pct(q.grade_average),
      ]);
    }
  }
  return rowsToCsv(rows);
}

/**
 * QRA-by-standard-and-teacher: standard-group header → nested teacher-group
 * header → question member rows.
 */
function qraByStandardTeacherToCsv(p: QraByStandardTeacherPayload): string {
  const header: CsvRow = [
    'Group',
    'Question No',
    'Question',
    'Standards',
    'Correct Answer',
    'Grade Average %',
  ];
  const rows: CsvRow[] = [header];
  for (const sg of p.standard_groups) {
    rows.push([
      `Standard: ${sg.cpalms_standard}`,
      '',
      htmlToPlainText(sg.standard_description),
      '',
      '',
      sg.standard_average_pct || pct(sg.standard_average),
    ]);
    for (const tg of sg.teacher_groups) {
      rows.push([
        `Teacher: ${tg.section_instructor}`,
        '',
        '',
        '',
        '',
        tg.teacher_standard_average_pct || pct(tg.teacher_standard_average),
      ]);
      for (const q of tg.questions) {
        rows.push([
          '',
          q.question_no,
          htmlToPlainText(q.question),
          joinStandards(q.standards),
          htmlToPlainText(q.correct_answer),
          pct(q.grade_average),
        ]);
      }
    }
  }
  return rowsToCsv(rows);
}

/**
 * QSR matrix: student × question wide matrix of partial-credit cells
 * (points_received, may be fractional), with a per-student total column,
 * per-teacher subtotal rows, and a grand-total row. Mirrors the legacy SSRS:
 * every Score% is SUM(received)/SUM(possible).
 */
function qsrToCsv(p: QuestionSummaryMatrixPayload): string {
  const header: CsvRow = ['Student', ...p.questions.map((q) => q.question_no), 'Total %'];
  const rows: CsvRow[] = [header];

  for (const g of p.teacher_groups) {
    rows.push([`Teacher: ${g.section_instructor}`]);
    for (const s of g.students) {
      const cells = p.questions.map((q) => {
        const v = s.cells[q.question_id];
        return v === null || v === undefined ? '' : num(v);
      });
      rows.push([s.user_name, ...cells, pct(s.score_pct)]);
    }
    rows.push([
      `Subtotal: ${g.section_instructor}`,
      ...p.questions.map((q) => pct(g.per_question_pct[q.question_id])),
      pct(g.teacher_score_pct),
    ]);
  }

  rows.push([
    'Grand Total',
    ...p.questions.map((q) => pct(p.grand_total.per_question_pct[q.question_id])),
    pct(p.grand_total.score_pct),
  ]);
  return rowsToCsv(rows);
}

/**
 * YTD longitudinal: student rows × standard columns (points received), with a
 * per-student total, per-teacher subtotal rows, and a grand-total row.
 */
function ytdToCsv(p: YearToDatePerformancePayload): string {
  const stdLabels = p.standards.map((s) => s.standard_label);
  const stdKeys = p.standards.map((s) => s.schoology_standard);
  const header: CsvRow = ['Student', 'Tests Taken', ...stdLabels, 'Total %'];
  const rows: CsvRow[] = [header];

  for (const g of p.teacher_groups) {
    rows.push([`Teacher: ${g.section_instructor}`]);
    for (const s of g.students) {
      const cells = stdKeys.map((k) => {
        const cell = s.cells[k];
        return cell ? num(cell.points_received) : '';
      });
      rows.push([s.user_name, num(s.tests_taken), ...cells, pct(s.score_pct)]);
    }
    const subtotals = stdKeys.map((k) => {
      const sub = g.standard_subtotals[k];
      return sub ? num(sub.points_received) : '';
    });
    rows.push([
      `Subtotal: ${g.section_instructor}`,
      '',
      ...subtotals,
      pct(g.teacher_score_pct),
    ]);
  }

  const grandCells = stdKeys.map((k) => {
    const t = p.grand_total.standard_totals[k];
    return t ? num(t.points_received) : '';
  });
  rows.push([
    'Grand Total',
    '',
    ...grandCells,
    pct(p.grand_total.score_pct),
  ]);
  return rowsToCsv(rows);
}

/** Standard Summary: one row per standard. */
function standardSummaryToCsv(p: StandardSummaryPayload): string {
  const header: CsvRow = [
    'Standard',
    'CPALMS Standard',
    'Strand',
    'Description',
    'Total Questions',
    'Grade Average %',
    '% Incorrect',
  ];
  const rows: CsvRow[] = [header];
  for (const s of p.standards) {
    rows.push([
      s.schoology_standard,
      s.cpalms_standard,
      s.strand,
      htmlToPlainText(s.description),
      num(s.num_questions),
      pct(s.grade_average),
      pct(1 - s.grade_average),
    ]);
  }
  return rowsToCsv(rows);
}

/** Strand Summary: one row per strand. */
function strandSummaryToCsv(p: StrandSummaryPayload): string {
  const header: CsvRow = [
    'Strand',
    'Standards',
    'Questions',
    'Grade Average %',
    '% Incorrect',
  ];
  const rows: CsvRow[] = [header];
  for (const s of p.strands_rollup) {
    rows.push([
      s.strand,
      num(s.num_standards),
      num(s.num_questions),
      pct(s.grade_average),
      pct(s.incorrect_pct),
    ]);
  }
  return rowsToCsv(rows);
}

/**
 * Forward View: one row per (period, unit, standard) — the exact visible grain
 * of the period → unit → standards body. Points columns expose the pooled math
 * behind each %; `Flagged` echoes the server-side `is_troublesome` flag so the
 * CSV can never disagree with the on-screen "Focus" pill.
 */
function forwardViewToCsv(p: ForwardViewPayload): string {
  const header: CsvRow = [
    'Period',
    'Unit',
    'Assessment Date',
    'Standard',
    'CPALMS Standard',
    'Strand',
    'Description',
    'Questions',
    'Points Earned',
    'Points Possible',
    '% Correct',
    'Flagged',
  ];
  const rows: CsvRow[] = [header];
  for (const period of p.periods) {
    for (const unit of period.units) {
      for (const s of unit.standards) {
        rows.push([
          period.period,
          unit.unit,
          unit.assessment_date ?? '',
          s.schoology_standard,
          s.cpalms_standard,
          s.strand,
          htmlToPlainText(s.description),
          num(s.num_questions),
          num(s.total_score),
          num(s.total_possible_point),
          // null grade_average renders BLANK (unassessed / 0 possible points).
          s.grade_average === null ? '' : pct(s.grade_average),
          s.is_troublesome ? 'Yes' : 'No',
        ]);
      }
    }
  }
  return rowsToCsv(rows);
}

/** SDD: standards_rollup grain — one row per Schoology standard. */
function sddToCsv(p: StandardsDeepDivePayload): string {
  const header: CsvRow = [
    'Standard',
    'Strand',
    'Questions',
    'Grade Average %',
  ];
  const rows: CsvRow[] = [header];
  for (const s of p.standards_rollup) {
    rows.push([
      s.schoology_standard,
      s.strand,
      num(s.num_questions),
      // null grade_average renders BLANK (unassessed), per SddStandardRow.
      s.grade_average === null ? '' : pct(s.grade_average),
    ]);
  }
  return rowsToCsv(rows);
}

/**
 * IAD: two labeled blocks — the distractor breakdown, then the per-student
 * attempt rows — mirroring the on-screen drill-through layout.
 */
function iadToCsv(p: IncorrectAnswerDetailsPayload): string {
  const rows: CsvRow[] = [];

  rows.push(['Distractors']);
  rows.push(['Answer', '# Students', '% of Attempts', 'Correct?']);
  for (const d of p.distractors) {
    rows.push([
      sanitizeShortAnswer(d.answer_submission),
      num(d.students_count),
      d.share_pct || pct(d.share_of_attempts),
      d.is_correct ? 'Yes' : 'No',
    ]);
  }

  rows.push([]);
  rows.push(['Student Attempts']);
  rows.push(['Student', 'Answer', 'Correct Answer', 'Correct?', 'Score %']);
  for (const a of p.student_attempts) {
    rows.push([
      a.user_name,
      sanitizeShortAnswer(a.answer_submission),
      sanitizeShortAnswer(a.correct_answer),
      a.is_correct ? 'Yes' : 'No',
      pct(a.score_pct),
    ]);
  }
  return rowsToCsv(rows);
}

// ─── Registry + dispatch ────────────────────────────────────────────────────

/**
 * Payload union by kind. Each entry is the exact react-query payload type the
 * matching report page already has in memory; `reportToCsv` narrows on `kind`.
 */
export interface ReportPayloadByKind {
  qra: QuestionResponseAnalysisPayload;
  'qra-paginated': QraPaginatedPayload;
  'qra-by-teacher': QraByTeacherPayload;
  'qra-by-standard-teacher': QraByStandardTeacherPayload;
  qsr: QuestionSummaryMatrixPayload;
  ytd: YearToDatePerformancePayload;
  'standard-summary': StandardSummaryPayload;
  'strand-summary': StrandSummaryPayload;
  'forward-view': ForwardViewPayload;
  sdd: StandardsDeepDivePayload;
  iad: IncorrectAnswerDetailsPayload;
}

/** Flatten a cached report payload into a CSV string for its visible grain. */
export function reportToCsv<K extends ReportKind>(
  kind: K,
  payload: ReportPayloadByKind[K],
): string {
  switch (kind) {
    case 'qra':
      return qraToCsv(payload as QuestionResponseAnalysisPayload);
    case 'qra-paginated':
      return qraPaginatedToCsv(payload as QraPaginatedPayload);
    case 'qra-by-teacher':
      return qraByTeacherToCsv(payload as QraByTeacherPayload);
    case 'qra-by-standard-teacher':
      return qraByStandardTeacherToCsv(payload as QraByStandardTeacherPayload);
    case 'qsr':
      return qsrToCsv(payload as QuestionSummaryMatrixPayload);
    case 'ytd':
      return ytdToCsv(payload as YearToDatePerformancePayload);
    case 'standard-summary':
      return standardSummaryToCsv(payload as StandardSummaryPayload);
    case 'strand-summary':
      return strandSummaryToCsv(payload as StrandSummaryPayload);
    case 'forward-view':
      return forwardViewToCsv(payload as ForwardViewPayload);
    case 'sdd':
      return sddToCsv(payload as StandardsDeepDivePayload);
    case 'iad':
      return iadToCsv(payload as IncorrectAnswerDetailsPayload);
    default: {
      // Exhaustiveness guard — every ReportKind must have a flattener.
      const _exhaustive: never = kind;
      throw new Error(`Unsupported report kind: ${String(_exhaustive)}`);
    }
  }
}

// ─── Filename + download ────────────────────────────────────────────────────

/** Sanitize a filename segment: keep word chars / dash, collapse the rest. */
export function sanitizeFilenameSegment(raw: string): string {
  return (
    raw
      .normalize('NFKD')
      .replace(/[^\w-]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 80) || 'report'
  );
}

/** `YYYYMMDD` for the local date. */
function todayStamp(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}${m}${day}`;
}

/** Build `<report>-<item|program>-<YYYYMMDD>.csv`, fully sanitized. */
export function buildCsvFilename(
  kind: ReportKind,
  itemOrProgram: string | null | undefined,
  date = new Date(),
): string {
  const report = sanitizeFilenameSegment(kind);
  const subject = sanitizeFilenameSegment(itemOrProgram || kind);
  return `${report}-${subject}-${todayStamp(date)}.csv`;
}

/**
 * Trigger a browser download of `csv` as `filename` via a Blob + temporary
 * anchor. No-op outside the browser (SSR / tests).
 */
export function downloadCsv(csv: string, filename: string): void {
  if (typeof document === 'undefined' || typeof URL === 'undefined') return;
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke on the next tick so the click has time to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
