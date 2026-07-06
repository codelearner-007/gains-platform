export interface AssessmentMeta {
  item_id: string;
  item_name: string;
  course_name: string;
  course_code: string;
  section_nid: string;
  section_name: string;
  section_code: string;
  section_instructors: string;
  school_id: string;
  school_name: string;
  school_logo_url: string | null;
  subject: string;
  grade: string;
  session: string;
  assessment_type: string;
  assessment_date: string | null;
  first_access: string;
  latest_attempt: string;
}

export interface QuestionOverall {
  question_id: string;
  question_no: string;
  position_number: string;
  question: string;
  question_type: string;
  correct_answer: string;
  total_possible_point: number;
  total_score: number;
  grade_average: number;
  percentage_incorrect: number;
  incorrect_choice_details: string;
  incorrect_details_name: string;
  standards: string;
  // First/primary raw standard code (e.g. "MA.912.AR.3.1") — NOT a strand.
  standard_raw: string;
  description: string;
}

export interface KPIs {
  instructors: string[];
  grade_average: number;
  grade_average_pct: string;
  total_questions: number;
  total_standards: number;
  total_students: number;
  grade_min: number;
  grade_max: number;
  grade_min_pct: string;
  grade_max_pct: string;
  total_possible_point: number;
  total_score: number;
}

// ─── Standards Deep Dive interactive (per-assessment) ────────────────────

export interface SddKpis {
  instructors: string[];
  total_students: number;
  total_questions: number;
  total_standards: number;
  grade_average: number;
  grade_average_pct: string;
}

export interface SddStrandRow {
  strand: string;
  num_standards: number;
  num_questions: number;
  // null + empty pct for an unassessed strand — rendered BLANK, not 0.0%.
  grade_average: number | null;
  grade_average_pct: string;
}

export interface SddStandardRow {
  schoology_standard: string;
  strand: string;
  num_questions: number;
  // null + empty pct for an unassessed Schoology alias — rendered BLANK.
  grade_average: number | null;
  grade_average_pct: string;
}

/**
 * One Schoology-standard bucket within a performance band (high/mid/low).
 *
 * The 3 × 100%-stacked bar charts on the SDD page are keyed on the
 * Schoology canonical standard code (one bar per standard), not per strand.
 * `strand` is carried alongside for tooltip context.
 */
export interface SddBandStandardRow {
  schoology_standard: string;
  strand: string;
  num_questions: number;
  grade_average: number;
}

/**
 * Refines a `"missing"` / `"partial"` `alignment_status` with the
 * underlying reason so the UI can render a tailored empty-state message
 * instead of the same generic copy for every empty report.
 *
 *   - `no_standards_in_source`    — Schoology export had zero `Standards{N}`
 *                                   columns (teacher never aligned)
 *   - `labels_not_mapped`         — teacher entered text labels that don't
 *                                   match the CPALMS catalog (e.g. "Social
 *                                   Studies"); see `unmatched_labels`
 *   - `partial_teacher_alignment` — some questions aligned, others not
 *   - `full_alignment`            — normal case (kept for symmetry)
 *   - `no_questions`              — item has no question rows at all
 */
export type AlignmentCause =
  | "no_standards_in_source"
  | "labels_not_mapped"
  | "partial_teacher_alignment"
  | "full_alignment"
  | "no_questions";

/**
 * Standards-alignment coverage for a report payload.
 *
 * Populated when the underlying Schoology Test/Quiz CSV ships fewer
 * `Standards{N}` columns than there are questions — typically because
 * instructors never aligned the questions to learning objectives in
 * Schoology. The page renders an explanatory empty-state card when
 * `alignment_status === "missing"`.
 *
 * The optional `cause` / `unmatched_labels` fields were added so the UI
 * can distinguish between teacher non-alignment, unrecognized labels,
 * and other root causes. Both are nullable for backward-compat with
 * older API responses; consumers should fall back to generic copy when
 * absent.
 */
export interface AlignmentDataQuality {
  alignment_status: "full" | "partial" | "missing";
  questions_total: number;
  questions_with_alignment: number;
  items_total: number;
  items_with_alignment: number;
  remediation_hint: string;
  cause?: AlignmentCause | null;
  unmatched_labels?: string[] | null;
}

export interface StandardsDeepDivePayload {
  assessment: AssessmentMeta;
  kpis: SddKpis;
  strands_rollup: SddStrandRow[];
  standards_rollup: SddStandardRow[];
  band_high: SddBandStandardRow[];
  band_mid: SddBandStandardRow[];
  band_low: SddBandStandardRow[];
  data_quality?: AlignmentDataQuality | null;
}

export interface QuestionResponseAnalysisPayload {
  assessment: AssessmentMeta;
  kpis: KPIs;
  questions_overall: QuestionOverall[];
  strands_rollup: SddStrandRow[];
  standards_rollup: SddStandardRow[];
  data_quality?: AlignmentDataQuality | null;
}

export interface AssessmentListRow {
  item_id: string;
  item_name: string | null;
  item_type: string | null;
  subject_id: string | null;
  subject: string | null;
  grade: string | null;
  session: string | null;
  assessment_type: string | null;
  section_name: string | null;
  section_instructors: string | null;
  assessment_date: string | null;
}

export interface AssessmentFilters {
  session?: string;
  category?: string;
  subject?: string;
  grade?: string;
  section?: string;
  instructor?: string;
  school_id?: string;
}

/** Assessment list row enriched with the per-item grade average + student
 *  count, for the dashboard "Assessments Summary — By Assessment" data bars.
 *  Both nullable: fact-less / cube-absent items resolve to null (em-dash). */
export interface AssessmentSummaryListRow extends AssessmentListRow {
  grade_average: number | null;
  total_students: number | null;
}

/** One server-paginated page of the dashboard By-Assessment grid. */
export interface AssessmentSummaryPage {
  rows: AssessmentSummaryListRow[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Multi-tenant — accessible schools (school switcher) ─────────────────

export interface AccessibleSchool {
  school_id: string;
  name: string;
  short_name: string;
  is_active: boolean;
}

export interface SubjectRow {
  subject_id: string;
  subject: string | null;
  grade: string | null;
  session: string | null;
  assessment_type: string | null;
}

export interface GradeRow {
  grade_id: string;
  grade: string | null;
}

export interface SectionRow {
  section_nid: string;
  section_code: string | null;
  section_name: string | null;
  section_instructors: string | null;
}

export interface SessionRow {
  session_id: string;
  session: string | null;
}

export interface AssessmentTypeRow {
  assessment_type: string;
}

export interface InstructorRow {
  instructor: string;
}

// ─── Dashboard front-filter aggregates ───────────────────────────────────

/** One subject KPI card on the dashboard (subject grade-average %). */
export interface DashboardSubjectCard {
  subject: string;
  grade_average: number | null;
  grade_average_pct: string;
}

export interface DashboardOverviewPayload {
  subjects: DashboardSubjectCard[];
  refreshed_at: string | null;
}

/** One per-(assessment × strand) row of the legacy Performance-by-Strand grid. */
export interface DashboardStrandRow {
  item_id: string;
  grade: string | null;
  strand: string;
  total_standards: number;
  total_questions: number;
  grade_average: number | null;
  grade_average_pct: string;
  assessment_date: string | null;
  assessment: string | null;
}

export interface DashboardStrandRowsPage {
  rows: DashboardStrandRow[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Year To Date - Longitudinal Report ─────────────────────────────────

export interface YTDSchoolInfo {
  name: string;
  logo_url: string | null;
  current_session: string;
  course_unit: string;
  assessment_types: string[];
}

// ─── YTD Longitudinal paginated matrix (PBIX ord 8 / 9 / 10) ─────────────────
// The three legacy "Longitudinal Report - Year To Date" reports (1/2/3) are
// the same POINTS-based matrix; the variants differ only in what this client
// renders:
//   • variant 1 — Tests Taken column + per-standard Score AND %
//   • variant 2 — no Tests Taken, per-standard % only
//   • variant 3 — Tests Taken + Score AND % + assessment/unit name under code

export interface YtdStandardColumn {
  standard_label: string;
  schoology_standard: string;
  unit_names: string;
}

export interface YtdCell {
  points_received: number;
  points_possible: number;
  score_pct: number;
}

export interface YtdStudentRow {
  user_uid: string;
  user_name: string;
  score_pct: number;
  tests_taken: number;
  points_received: number;
  points_possible: number;
  cells: Record<string, YtdCell>;
}

export interface YtdStandardTotal {
  points_received: number;
  points_possible: number;
  score_pct: number;
}

export interface YtdTeacherGroup {
  section_instructor: string;
  teacher_score_pct: number;
  students: YtdStudentRow[];
  standard_subtotals: Record<string, YtdStandardTotal>;
}

export interface YtdGrandTotal {
  points_received: number;
  points_possible: number;
  score_pct: number;
  standard_totals: Record<string, YtdStandardTotal>;
}

export interface YearToDatePerformancePayload {
  school: YTDSchoolInfo;
  subject: string;
  grade: string;
  session: string;
  assessment_type: string;
  standards: YtdStandardColumn[];
  teacher_groups: YtdTeacherGroup[];
  grand_total: YtdGrandTotal;
}

// ─── Incorrect Answer Details (drill-through from QRA) ───────────────────

export interface IadQuestionContext {
  question_id: string;
  question_no: string;
  position_number: string;
  question: string;
  question_type: string;
  correct_answer: string;
  standards: string;
  strand: string;
  description: string;
  grade_average: number;
  grade_average_pct: string;
  total_possible_point: number;
  total_score: number;
}

export interface IadKpis {
  total_attempts: number;
  correct_count: number;
  incorrect_count: number;
  correct_pct: string;
  incorrect_pct: string;
  distinct_answers: number;
  top_wrong_answer: string;
  top_wrong_count: number;
  top_wrong_pct: string;
}

export interface IadDistractorRow {
  answer_submission: string;
  students_count: number;
  share_of_attempts: number;
  share_pct: string;
  is_correct: boolean;
}

export interface IadStudentAttempt {
  user_uid: string;
  user_name: string;
  answer_submission: string;
  correct_answer: string;
  is_correct: boolean;
  points_received: number;
  points_possible: number;
  score_pct: number;
  latest_attempt: string;
}

export interface IncorrectAnswerDetailsPayload {
  assessment: AssessmentMeta;
  question: IadQuestionContext;
  kpis: IadKpis;
  distractors: IadDistractorRow[];
  student_attempts: IadStudentAttempt[];
}

// ─── Standard Summary (school-wide, per-cPalms_Standard grain) ───────────

export interface StandardSummaryFilters {
  session?: string;
  subject?: string;
  grade?: string;
  category?: string;
  section?: string;
  school_id?: string;
}

export interface StandardSummaryKpis {
  total_standards: number;
  total_questions: number;
  total_students: number;
  at_target_pct: number;
  at_target_pct_str: string;
  grade_average: number;
  grade_average_pct: string;
}

export interface StandardSummaryRollupRow {
  schoology_standard: string;
  // CPALMS code shown in the card banner (legacy multiRowCard #3).
  cpalms_standard: string;
  strand: string;
  cluster: string;
  cognitive_complexity: string;
  description: string;
  subject: string;
  grades: string[];
  num_questions: number;
  num_assessments: number;
  grade_average: number;
  grade_average_pct: string;
  last_change_date_time: string | null;
}

export interface StandardSummaryPayload {
  school: YTDSchoolInfo;
  filters_applied: StandardSummaryFilters;
  // Not rendered on the report (removed for parity); read by the dashboard.
  kpis: StandardSummaryKpis;
  standards: StandardSummaryRollupRow[];
  data_quality?: AlignmentDataQuality | null;
}

// ─── Strand Summary (school-wide, per-Strand grain) ──────────────────────

export interface StrandSummaryFilters {
  session?: string;
  subject?: string;
  grade?: string;
  category?: string;
  section?: string;
  strand?: string;
  school_id?: string;
}

export interface StrandSummaryKpis {
  total_strands: number;
  total_standards: number;
  total_questions: number;
  total_assessments: number;
  total_students: number;
  grade_average: number;
  grade_average_pct: string;
  worst_strand: string;
  worst_strand_pct: string;
}

export interface StrandSummaryRollupRow {
  strand: string;
  num_standards: number;
  num_questions: number;
  num_assessments: number;
  grade_average: number;
  grade_average_pct: string;
  incorrect_pct: number;
  subjects: string[];
}

export interface StrandSummaryStandardRow {
  strand: string;
  schoology_standard: string;
  cluster: string;
  num_questions: number;
  num_assessments: number;
  grade_average: number;
  grade_average_pct: string;
}

export interface StrandSummaryBandRow {
  strand: string;
  num_standards: number;
  num_questions: number;
  grade_average: number;
}

export interface StrandSummaryPayload {
  school: YTDSchoolInfo;
  filters_applied: StrandSummaryFilters;
  kpis: StrandSummaryKpis;
  strands_rollup: StrandSummaryRollupRow[];
  standards_rollup: StrandSummaryStandardRow[];
  band_high: StrandSummaryBandRow[];
  band_mid: StrandSummaryBandRow[];
  band_low: StrandSummaryBandRow[];
  data_quality?: AlignmentDataQuality | null;
  data_refreshed_at?: string;
}

// ─── Data Quality — Standards alignment (admin) ──────────────────────────

export interface AlignmentItemRow {
  item_id: string;
  item_name: string;
  item_type?: string | null;
  subject?: string | null;
  grade?: string | null;
  questions_total: number;
  questions_with_alignment: number;
  pct_aligned: number;
  alignment_status: "full" | "partial" | "missing";
}

export interface AlignmentDataQualityReport {
  school_id: string;
  school_name: string;
  items_total: number;
  items_with_alignment: number;
  items_missing_alignment: number;
  items_partial_alignment: number;
  items: AlignmentItemRow[];
}

// ─── Paginated reports (PBIX ord 6/7/16, 11, 12, 13) ────────────────────

export interface PaginatedKpis {
  total_questions: number;
  total_students: number;
  score: number;
  total_possible_point: number;
  grade_average: number;
  grade_average_pct: string;
}

export interface QsmQuestionColumn {
  question_id: string;
  question_no: string;
  sorting_question_no: number;
  standard: string;
  cpalms_standard: string;
  position_number: string;
  correct_answer: string;
}

// QSR is partial-credit (legacy SSRS / xlsx / grade-average-KPI parity): each
// (student × question) cell is `points_received` (may be fractional, e.g.
// 0 / 0.5 / 1); "# Correct Answers" is SUM(points_received) and every Score% is
// SUM(received)/SUM(possible). The web matrix and the xlsx export consume this
// SAME payload so they cannot diverge.

/** A contiguous CPALMS column band (one or more leaf question columns). */
export interface QspStandardBand {
  cpalms_standard: string;
  question_ids: string[];
}

export interface QsmStudentRow {
  user_uid: string;
  user_name: string;
  score_pct: number;
  // SUM(points_possible) / SUM(points_received) across the student's cells.
  possible_points: number;
  correct_count: number;
  // qid → points_received (may be fractional); null = not attempted.
  cells: Record<string, number | null>;
  // cpalms_standard → band Score% (SUM received / SUM possible in the band).
  band_pct: Record<string, number | null>;
}

export interface QsmTeacherGroup {
  section_instructor: string;
  teacher_score_pct: number;
  students: QsmStudentRow[];
  // Per-leaf-question teacher subtotals (partial credit) for the "- Teacher"
  // subtotal block: correct = SUM(received), possible = SUM(possible).
  per_question_correct: Record<string, number>;
  per_question_possible: Record<string, number>;
  per_question_pct: Record<string, number>;
}

export interface QsmGrandTotal {
  possible_points: number;
  correct_count: number;
  score_pct: number;
  // Per-leaf-question footer rows (summed points; pct = received/possible).
  per_question_possible: Record<string, number>;
  per_question_correct: Record<string, number>;
  per_question_pct: Record<string, number>;
  // Per-band footer Score% sub-columns.
  band_possible: Record<string, number>;
  band_correct: Record<string, number>;
  band_pct: Record<string, number>;
}

export interface QuestionSummaryMatrixPayload {
  assessment: AssessmentMeta;
  kpis?: PaginatedKpis | null;
  questions: QsmQuestionColumn[];
  bands: QspStandardBand[];
  teacher_groups: QsmTeacherGroup[];
  grand_total: QsmGrandTotal;
  // False for cube-only (parquet-loaded) schools with no fact_student_submission
  // rows: questions / teacher_groups are empty by design but grand_total is
  // still cube-derived. The frontend renders an explicit empty-state with the
  // assessment-level totals instead of an all-zero per-student matrix.
  per_student_available?: boolean;
}

export interface PaginatedQuestionRow {
  question_id: string;
  question_no: string;
  sorting_question_no: number;
  position_number: string;
  question: string;
  correct_answer: string;
  grade_average: number;
  grade_average_pct: string;
  incorrect_choice_details: string;
  incorrect_details_name: string;
  standards: string;
  cpalms_standard: string;
}

export interface QraPaginatedPayload {
  assessment: AssessmentMeta;
  kpis: PaginatedKpis;
  questions: PaginatedQuestionRow[];
}

export interface QraTeacherGroup {
  section_instructor: string;
  teacher_grade_average: number;
  teacher_grade_average_pct: string;
  questions: PaginatedQuestionRow[];
}

export interface QraByTeacherPayload {
  assessment: AssessmentMeta;
  kpis: PaginatedKpis;
  teacher_groups: QraTeacherGroup[];
}

export interface QraStandardTeacherGroup {
  section_instructor: string;
  teacher_standard_average: number;
  teacher_standard_average_pct: string;
  questions: PaginatedQuestionRow[];
}

export interface QraStandardGroup {
  cpalms_standard: string;
  standard_description: string;
  standard_average: number;
  standard_average_pct: string;
  teacher_groups: QraStandardTeacherGroup[];
}

export interface QraByStandardTeacherPayload {
  assessment: AssessmentMeta;
  kpis: PaginatedKpis;
  standard_groups: QraStandardGroup[];
}
