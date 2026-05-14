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

export interface Student {
  user_uid: string;
  username: string;
  first_name: string;
  last_name: string;
  user_role_id: string;
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

export interface IncorrectChoice {
  question_id: string;
  answer_submission: string;
  is_correct: boolean;
  students_count: number;
  attempt_count_for_choice: number;
  total_attempts_for_question: number;
  share_of_attempts: number;
  total_score: number;
  total_possible_point: number;
  grade_average: number;
  students: string[];
}

export interface RawQuestionOption {
  item_id: string;
  item_name: string;
  question_id: string;
  associated_question_id: string;
  total_points: number;
  question_type: string;
  question: string;
  position_number: string;
  sub_question: string;
  answer_option: string;
  answer_breakdown_count: number;
  answer_breakdown_pct: number;
  correct_answer: string;
  correctly_answered: number;
  most_points_earned: number;
  least_points_earned: number;
  average_points_earned: number;
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

// ─── Standards Deep Dive (per-assessment) ────────────────────────────────

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
  cpalms_standard: string;
  schoology_standard: string;
  strand: string;
  num_questions: number;
  grade_average: number;
  grade_average_pct: string;
}

export interface SddBandStrandRow {
  strand: string;
  num_standards: number;
  num_questions: number;
  grade_average: number;
}

export interface StandardsDeepDivePayload {
  assessment: AssessmentMeta;
  kpis: SddKpis;
  strands_rollup: SddStrandRow[];
  standards_rollup: SddStandardRow[];
  band_high: SddBandStrandRow[];
  band_mid: SddBandStrandRow[];
  band_low: SddBandStrandRow[];
}

export interface QuestionResponseAnalysisPayload {
  assessment: AssessmentMeta;
  kpis: KPIs;
  students: Student[];
  questions_overall: QuestionOverall[];
  incorrect_choices: IncorrectChoice[];
  raw_question_options: RawQuestionOption[];
  strands_rollup: SddStrandRow[];
  standards_rollup: SddStandardRow[];
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

// ─── Year-To-Date Performance ───────────────────────────────────────────

export interface YTDSchoolInfo {
  name: string;
  logo_url: string | null;
  current_session: string;
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
  total_students: number;
  total_assessments: number;
  total_questions_answered: number;
  overall_avg_pct: string;
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
  cpalms_standard: string;
  schoology_standard: string;
  strand: string;
  cluster: string;
  cognitive_complexity: string;
  description: string;
  subject: string;
  num_questions: number;
  num_assessments: number;
  grade_average: number;
  grade_average_pct: string;
  perf_color: string;
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
}

// ─── Strand Summary (school-wide, per-Strand grain) ──────────────────────

export interface StrandSummaryFilters {
  session?: string;
  subject?: string;
  grade?: string;
  category?: string;
  section?: string;
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
  perf_color: string;
  subjects: string[];
}

export interface StrandSummaryStandardRow {
  strand: string;
  cpalms_standard: string;
  schoology_standard: string;
  cluster: string;
  num_questions: number;
  num_assessments: number;
  grade_average: number;
  grade_average_pct: string;
  perf_color: string;
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
}
