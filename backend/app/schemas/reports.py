"""Pydantic schemas for the reports endpoints.

These shapes are the contract consumed by the Next.js reports pages
(``frontend/src/lib/reports/types.ts``). Field names + types must match
the TypeScript interfaces exactly.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AssessmentMeta(BaseModel):
    item_id: str
    item_name: str
    course_name: str
    course_code: str
    section_nid: str
    section_name: str
    section_code: str
    section_instructors: str
    school_id: str
    school_name: str
    school_logo_url: Optional[str] = None
    subject: str
    grade: str
    session: str
    assessment_type: str
    first_access: str
    latest_attempt: str

    model_config = ConfigDict(from_attributes=True)


class KPIs(BaseModel):
    instructors: List[str]
    grade_average: float
    grade_average_pct: str
    total_questions: int
    total_standards: int
    total_students: int
    grade_min: float
    grade_max: float
    grade_min_pct: str
    grade_max_pct: str
    total_possible_point: float
    total_score: float


class Student(BaseModel):
    user_uid: str
    username: str
    first_name: str
    last_name: str
    user_role_id: str

    model_config = ConfigDict(from_attributes=True)


class QuestionOverall(BaseModel):
    question_id: str
    question_no: str
    position_number: str
    question: str
    question_type: str
    correct_answer: str
    total_possible_point: float
    total_score: float
    grade_average: float
    percentage_incorrect: float
    incorrect_choice_details: str
    incorrect_details_name: str
    standards: str
    strand: str
    description: str


class IncorrectChoice(BaseModel):
    question_id: str
    answer_submission: str
    is_correct: bool
    students_count: int
    attempt_count_for_choice: int
    total_attempts_for_question: int
    share_of_attempts: float
    total_score: float
    total_possible_point: float
    grade_average: float
    students: List[str]


class RawQuestionOption(BaseModel):
    item_id: str
    item_name: str
    question_id: str
    associated_question_id: str
    total_points: float
    question_type: str
    question: str
    position_number: str
    sub_question: str
    answer_option: str
    answer_breakdown_count: float
    answer_breakdown_pct: float
    correct_answer: str
    correctly_answered: float
    most_points_earned: float
    least_points_earned: float
    average_points_earned: float


class StandardSummaryRow(BaseModel):
    """One row of cube_standard_summary joined to dim_standard for an assessment."""

    item_id: Optional[str] = None
    strand_id: Optional[str] = None
    identifier: Optional[str] = None
    strand: Optional[str] = None
    schoology_standard: Optional[str] = None
    description: Optional[str] = None
    total_questions: int
    total_standards: int
    total_possible_point: float
    total_score: float
    grade_average: float
    percentage_incorrect_answers: float


# ─── Standards Deep Dive (per-assessment) ──────────────────────────────────


class SddKpis(BaseModel):
    """Five KPI values rendered at the top of the SDD page."""

    instructors: List[str]
    total_students: int
    total_questions: int
    total_standards: int
    grade_average: float
    grade_average_pct: str


class SddStrandRow(BaseModel):
    """One row in the Strands rollup table / treemap."""

    strand: str
    num_standards: int
    num_questions: int
    grade_average: float
    grade_average_pct: str


class SddStandardRow(BaseModel):
    """One row in the Standards rollup table."""

    cpalms_standard: str
    schoology_standard: str
    strand: str
    num_questions: int
    grade_average: float
    grade_average_pct: str


class SddBandStrandRow(BaseModel):
    """One strand bucket within a performance band (high/mid/low)."""

    strand: str
    num_standards: int
    num_questions: int
    grade_average: float


class StandardsDeepDivePayload(BaseModel):
    """Standards Deep Dive endpoint — per-assessment rollup."""

    assessment: AssessmentMeta
    kpis: SddKpis
    strands_rollup: List[SddStrandRow]
    standards_rollup: List[SddStandardRow]
    band_high: List[SddBandStrandRow]
    band_mid: List[SddBandStrandRow]
    band_low: List[SddBandStrandRow]


class QuestionResponseAnalysisPayload(BaseModel):
    """Composed payload for the QRA report.

    The ``strands_rollup`` and ``standards_rollup`` arrays use the same
    shape as Standards Deep Dive so a single helper computes both.
    """

    assessment: AssessmentMeta
    kpis: KPIs
    students: List[Student]
    questions_overall: List[QuestionOverall]
    incorrect_choices: List[IncorrectChoice]
    raw_question_options: List[RawQuestionOption]
    strands_rollup: List[SddStrandRow] = []
    standards_rollup: List[SddStandardRow] = []


# ─── Year-To-Date Performance ──────────────────────────────────────────────


class YTDSchoolInfo(BaseModel):
    name: str
    logo_url: Optional[str] = None
    current_session: str


class YTDPeriodInfo(BaseModel):
    date_from: str
    date_to: str


class YTDStudentSummary(BaseModel):
    user_uid: str
    user_name: str
    delta: float


class YTDKpis(BaseModel):
    total_students: int
    total_assessments: int
    total_questions_answered: int
    overall_avg_pct: str
    students_improving: int
    students_declining: int
    most_improved: List[YTDStudentSummary]
    biggest_drops: List[YTDStudentSummary]


class YTDTimelinePoint(BaseModel):
    date: str
    overall_avg: float
    per_subject: dict[str, float]
    assessments_count: int


class YTDGradeDistribution(BaseModel):
    date: str
    band_high: int
    band_mid: int
    band_low: int


class YTDStudentScatter(BaseModel):
    user_uid: str
    user_name: str
    first_avg: float
    latest_avg: float
    delta: float
    assessments_taken: int


class YTDHeatmapCell(BaseModel):
    strand: str
    date: str
    grade_average: float


class YearToDatePerformancePayload(BaseModel):
    school: YTDSchoolInfo
    period: YTDPeriodInfo
    kpis: YTDKpis
    timeline: List[YTDTimelinePoint]
    grade_distribution: List[YTDGradeDistribution]
    student_progression: List[YTDStudentScatter]
    strand_heatmap: List[YTDHeatmapCell]


# ─── Incorrect Answer Details (drill-through from QRA) ─────────────────────


class IadQuestionContext(BaseModel):
    """The single question being analysed on the IAD page."""

    question_id: str
    question_no: str
    position_number: str
    question: str
    question_type: str
    correct_answer: str
    standards: str
    strand: str
    description: str
    grade_average: float
    grade_average_pct: str
    total_possible_point: float
    total_score: float


class IadKpis(BaseModel):
    """Compact KPI strip for one question."""

    total_attempts: int
    correct_count: int
    incorrect_count: int
    correct_pct: str
    incorrect_pct: str
    distinct_answers: int
    top_wrong_answer: str
    top_wrong_count: int
    top_wrong_pct: str


class IadDistractorRow(BaseModel):
    """One row of the per-answer-choice distractor breakdown table."""

    answer_submission: str
    students_count: int
    share_of_attempts: float
    share_pct: str
    is_correct: bool


class IadStudentAttempt(BaseModel):
    """One student × this question row."""

    user_uid: str
    user_name: str
    answer_submission: str
    correct_answer: str
    is_correct: bool
    points_received: float
    points_possible: float
    score_pct: float
    latest_attempt: str


class IncorrectAnswerDetailsPayload(BaseModel):
    """Drill-through endpoint payload for the IAD page (one question)."""

    assessment: AssessmentMeta
    question: IadQuestionContext
    kpis: IadKpis
    distractors: List[IadDistractorRow]
    student_attempts: List[IadStudentAttempt]
