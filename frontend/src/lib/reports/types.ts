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
  strand: string;
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
  grade_average: number;
  grade_average_pct: string;
}

export interface SddStandardRow {
  schoology_standard: string;
  strand: string;
  num_questions: number;
  grade_average: number;
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

// ─── Year To Date - Longitudinal Report ─────────────────────────────────

export interface YTDSchoolInfo {
  name: string;
  logo_url: string | null;
  current_session: string;
  course_unit: string;
  assessment_types: string[];
}

export interface YTDPeriodInfo {
  date_from: string;
  date_to: string;
}

export interface YTDStudentSummary {
  user_uid: string;
  user_name: string;
  delta: number;
}

export interface YTDKpis {
  total_questions: number;
  total_students: number;
  total_points_earned: number;
  total_points_possible: number;
  overall_avg_pct: string;
  total_assessments: number;
  students_improving: number;
  students_declining: number;
  most_improved: YTDStudentSummary[];
  biggest_drops: YTDStudentSummary[];
}

export interface YTDTimelinePoint {
  date: string;
  overall_avg: number;
  per_subject: Record<string, number>;
  assessments_count: number;
}

export interface YTDGradeDistribution {
  date: string;
  band_high: number;
  band_mid: number;
  band_low: number;
}

export interface YTDStudentScatter {
  user_uid: string;
  user_name: string;
  first_avg: number;
  latest_avg: number;
  delta: number;
  assessments_taken: number;
}

export interface YTDHeatmapCell {
  strand: string;
  date: string;
  grade_average: number;
}

export interface YearToDatePerformancePayload {
  school: YTDSchoolInfo;
  period: YTDPeriodInfo;
  kpis: YTDKpis;
  timeline: YTDTimelinePoint[];
  grade_distribution: YTDGradeDistribution[];
  student_progression: YTDStudentScatter[];
  strand_heatmap: YTDHeatmapCell[];
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
  /** Legacy PBIX's `Total Incorrect Choices` — DISTINCTCOUNT of wrong answers. */
  total_incorrect_choices: number;
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

export interface StandardSummaryStrandCount {
  strand: string;
  num_standards: number;
  num_questions: number;
  grade_average: number;
}

export interface StandardSummaryPayload {
  school: YTDSchoolInfo;
  filters_applied: StandardSummaryFilters;
  kpis: StandardSummaryKpis;
  standards: StandardSummaryRollupRow[];
  strand_counts: StandardSummaryStrandCount[];
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

export interface QsmStudentRow {
  user_uid: string;
  user_name: string;
  score_pct: number;
  possible_points: number;
  correct_count: number;
  cells: Record<string, 0 | 1 | null>;
}

export interface QsmTeacherGroup {
  section_instructor: string;
  teacher_score_pct: number;
  students: QsmStudentRow[];
}

export interface QsmGrandTotal {
  possible_points: number;
  correct_count: number;
  score_pct: number;
  per_question_possible: Record<string, number>;
  per_question_correct: Record<string, number>;
  per_question_pct: Record<string, number>;
}

export interface QuestionSummaryMatrixPayload {
  assessment: AssessmentMeta;
  kpis: PaginatedKpis;
  questions: QsmQuestionColumn[];
  teacher_groups: QsmTeacherGroup[];
  grand_total: QsmGrandTotal;
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
