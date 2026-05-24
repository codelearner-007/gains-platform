"""Pydantic schemas for the reports endpoints.

These shapes are the contract consumed by the Next.js reports pages
(``frontend/src/lib/reports/types.ts``). Field names + types must match
the TypeScript interfaces exactly.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class AlignmentDataQuality(BaseModel):
    """Standards-alignment coverage for a report payload.

    Surfaces when the underlying Schoology Test/Quiz CSV ships fewer
    ``Standards{N}`` columns than there are questions — e.g. when teachers
    haven't aligned questions to learning objectives in Schoology. Attached
    to SDD / Strand Summary / Standard Summary payloads so the UI can
    render an explanatory empty state instead of blank charts.

    ``alignment_status`` semantics:
      * ``"full"``    — every question has at least one resolvable alignment
      * ``"partial"`` — some aligned, some missing; reports may render
        partial charts plus a banner
      * ``"missing"`` — zero alignments resolved; reports should render
        an empty-state card

    ``cause`` refines a ``"missing"`` / ``"partial"`` status with the
    underlying reason so the UI can render a tailored empty-state message
    instead of the same generic copy for every empty report:

      * ``"full_alignment"``           — every question aligned
      * ``"partial_teacher_alignment"`` — some aligned, some not
      * ``"no_standards_in_source"``   — source CSV had zero Standards
        columns (Category A in the empty-state RCA)
      * ``"labels_not_mapped"``        — source had labels but none
        matched a CPALMS code (Category B)
      * ``"no_questions"``             — item has no question rows at all

    ``unmatched_labels`` is populated only when ``cause ==
    "labels_not_mapped"`` and lists up to five distinct raw labels that
    failed to map (e.g. ``["Social Studies"]``). ``None`` otherwise.

    Both fields are optional / nullable so existing clients that don't
    consume them keep working — they are purely additive.

    ``items_total`` / ``items_with_alignment`` are populated for school-wide
    reports (Standard / Strand Summary). For per-assessment payloads
    (SDD) they equal ``1`` / ``0`` or ``1`` respectively.
    """

    alignment_status: Literal["full", "partial", "missing"]
    questions_total: int
    questions_with_alignment: int
    items_total: int
    items_with_alignment: int
    remediation_hint: str
    cause: Optional[
        Literal[
            "full_alignment",
            "partial_teacher_alignment",
            "no_standards_in_source",
            "labels_not_mapped",
            "no_questions",
        ]
    ] = None
    unmatched_labels: Optional[List[str]] = None


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


# ─── Standards Deep Dive interactive (per-assessment) ─────────────────────


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
    """One row in the Standards rollup table, keyed by the Schoology
    canonical long-form code (e.g. ``MA.9-12.MAFS.912.N-Q.1.3``)."""

    schoology_standard: str
    strand: str
    num_questions: int
    grade_average: float
    grade_average_pct: str


class SddBandStandardRow(BaseModel):
    """One Schoology-standard bucket within a performance band
    (high/mid/low). The 3 × 100%-stacked bar charts are keyed on the
    Schoology canonical standard code. ``strand`` is carried alongside
    for tooltip context.
    """

    schoology_standard: str
    strand: str
    num_questions: int
    grade_average: float


class StandardsDeepDivePayload(BaseModel):
    """Standards Deep Dive interactive endpoint — per-assessment rollup."""

    assessment: AssessmentMeta
    kpis: SddKpis
    strands_rollup: List[SddStrandRow]
    standards_rollup: List[SddStandardRow]
    band_high: List[SddBandStandardRow]
    band_mid: List[SddBandStandardRow]
    band_low: List[SddBandStandardRow]
    data_quality: Optional[AlignmentDataQuality] = None


class QuestionResponseAnalysisPayload(BaseModel):
    """Composed payload for the QRA report.

    The ``strands_rollup`` and ``standards_rollup`` arrays use the same
    shape as Standards Deep Dive interactive so a single helper computes both.

    ``data_quality`` is the standards-alignment block; the QRA page gates
    on ``alignment_status === "missing"`` to render the explanatory
    empty-state card (mirrors SDD page behaviour).
    """

    assessment: AssessmentMeta
    kpis: KPIs
    questions_overall: List[QuestionOverall]
    strands_rollup: List[SddStrandRow] = []
    standards_rollup: List[SddStandardRow] = []
    data_quality: Optional[AlignmentDataQuality] = None


# ─── Year To Date - Longitudinal Report ────────────────────────────────────


class YTDSchoolInfo(BaseModel):
    name: str
    logo_url: Optional[str] = None
    current_session: str
    course_unit: str = ""
    assessment_types: List[str] = []


class YTDPeriodInfo(BaseModel):
    date_from: str
    date_to: str


class YTDStudentSummary(BaseModel):
    user_uid: str
    user_name: str
    delta: float


class YTDFilters(BaseModel):
    session: Optional[str] = None
    category: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    section: Optional[str] = None


class YTDKpis(BaseModel):
    """PBIX "Key Measures" card plus derived counters used by the
    Additional Insights zone."""

    total_questions: int
    total_students: int
    total_points_earned: float
    total_points_possible: float
    overall_avg_pct: str
    total_assessments: int
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
    # Legacy PBIX's `Total Incorrect Choices` (DISTINCTCOUNT of wrong answers).
    total_incorrect_choices: int
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


# ─── Standard Summary (school-wide, per-cPalms_Standard grain) ─────────────


class StandardSummaryFilters(BaseModel):
    """Echo of the query params applied so the client can re-render chips."""

    session: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    category: Optional[str] = None
    section: Optional[str] = None


class StandardSummaryKpis(BaseModel):
    """Five KPI cards rendered at the top of the Standard Summary page."""

    total_standards: int
    total_questions: int
    total_students: int
    at_target_pct: float
    at_target_pct_str: str
    grade_average: float
    grade_average_pct: str


class StandardSummaryRollupRow(BaseModel):
    """One card per Schoology canonical standard aggregated across the
    filter scope."""

    schoology_standard: str
    strand: str
    cluster: str
    cognitive_complexity: str
    description: str
    subject: str
    grades: List[str] = []
    num_questions: int
    num_assessments: int
    grade_average: float
    grade_average_pct: str
    last_change_date_time: Optional[str] = None


class StandardSummaryStrandCount(BaseModel):
    """Auxiliary distribution: # of standards per strand for the bar chart."""

    strand: str
    num_standards: int
    num_questions: int
    grade_average: float


class StandardSummaryPayload(BaseModel):
    """School-wide standards rollup (mirrors PBIX page #14)."""

    school: YTDSchoolInfo
    filters_applied: StandardSummaryFilters
    kpis: StandardSummaryKpis
    standards: List[StandardSummaryRollupRow]
    strand_counts: List[StandardSummaryStrandCount]
    data_quality: Optional[AlignmentDataQuality] = None


# ─── Strand Summary (school-wide, per-Strand grain) ────────────────────────


class StrandSummaryFilters(BaseModel):
    """Echo of the query params applied so the client can re-render chips."""

    session: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    category: Optional[str] = None
    section: Optional[str] = None
    strand: Optional[str] = None


class StrandSummaryKpis(BaseModel):
    """Top-of-page KPIs for the Strand Summary."""

    total_strands: int
    total_standards: int
    total_questions: int
    total_assessments: int
    total_students: int
    grade_average: float
    grade_average_pct: str
    worst_strand: str
    worst_strand_pct: str


class StrandSummaryRollupRow(BaseModel):
    """One row per Strand for the school-wide rollup."""

    strand: str
    num_standards: int
    num_questions: int
    num_assessments: int
    grade_average: float
    grade_average_pct: str
    incorrect_pct: float
    subjects: List[str]


class StrandSummaryStandardRow(BaseModel):
    """One row per (strand, Schoology standard) for the drill table."""

    strand: str
    schoology_standard: str
    cluster: str
    num_questions: int
    num_assessments: int
    grade_average: float
    grade_average_pct: str


class StrandSummaryBandRow(BaseModel):
    """Band-shaped row for the 100%-stacked-bars panels."""

    strand: str
    num_standards: int
    num_questions: int
    grade_average: float


class StrandSummaryPayload(BaseModel):
    """School-wide strand rollup (mirrors PBIX page #15)."""

    school: YTDSchoolInfo
    filters_applied: StrandSummaryFilters
    kpis: StrandSummaryKpis
    strands_rollup: List[StrandSummaryRollupRow]
    standards_rollup: List[StrandSummaryStandardRow]
    band_high: List[StrandSummaryBandRow]
    band_mid: List[StrandSummaryBandRow]
    band_low: List[StrandSummaryBandRow]
    data_quality: Optional[AlignmentDataQuality] = None
    data_refreshed_at: str = ""


# ─── Standards-alignment Data Quality (admin) ──────────────────────────────


class AlignmentItemRow(BaseModel):
    """Per-assessment alignment-coverage row for the admin DQ list.

    Built from ``dim_question_data`` joined to ``dim_item``: counts how
    many distinct questions on the assessment do / do not resolve to a
    ``dim_standard.identifier`` through the substring join in
    ``dim_question_data.sql``. The ratio drives the admin DQ dashboard.
    """

    item_id: str
    item_name: str
    item_type: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    questions_total: int
    questions_with_alignment: int
    pct_aligned: float
    alignment_status: Literal["full", "partial", "missing"]


class AlignmentDataQualityReport(BaseModel):
    """Tenant-scoped alignment-coverage report."""

    school_id: str
    school_name: str
    items_total: int
    items_with_alignment: int
    items_missing_alignment: int
    items_partial_alignment: int
    items: List[AlignmentItemRow]
