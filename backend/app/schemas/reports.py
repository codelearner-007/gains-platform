"""Pydantic schemas for the reports endpoints.

These shapes are the contract consumed by the Next.js reports pages
(``frontend/src/lib/reports/types.ts``). Field names + types must match
the TypeScript interfaces exactly.
"""

from __future__ import annotations

from datetime import date
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
    assessment_date: Optional[str] = None
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
    # The first/primary raw standard code for the question (e.g.
    # "MA.912.AR.3.1"). Carries a standard code, NOT a strand — renamed
    # from the misleading ``strand`` (MASTER_PLAN §6, QRA-RENAME-1).
    standard_raw: str
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
    """One row in the Strands rollup table / treemap.

    ``grade_average`` is ``None`` (and ``grade_average_pct`` an empty
    string) for an unassessed strand — legacy renders BLANK, not 0.0%
    (MASTER_PLAN §6, Decision 3).
    """

    strand: str
    num_standards: int
    num_questions: int
    grade_average: Optional[float] = None
    grade_average_pct: str


class SddStandardRow(BaseModel):
    """One row in the Standards rollup table, keyed by the Schoology
    canonical long-form code (e.g. ``MA.9-12.MAFS.912.N-Q.1.3``).

    ``grade_average`` is ``None`` (and ``grade_average_pct`` an empty
    string) for an unassessed Schoology alias standard — legacy renders
    BLANK, not 0.0% (MASTER_PLAN §6, Decision 3).
    """

    schoology_standard: str
    strand: str
    num_questions: int
    grade_average: Optional[float] = None
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


class YTDFilters(BaseModel):
    session: Optional[str] = None
    category: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    section: Optional[str] = None


# ─── YTD Longitudinal paginated matrix (PBIX ord 8 / 9 / 10 rdlVisual) ────────
#
# The three legacy "Longitudinal Report - Year To Date" reports (1/2/3) are the
# same POINTS-based matrix — rows grouped Classroom Instructor → Student, one
# column per standard assessed YTD (Score = earned/possible, % = SUM/SUM), with
# per-teacher subtotal rows and grand-total rows. The three variants differ only
# in client rendering (see frontend types.ts):
#   • 1 — Tests Taken column + per-standard Score AND %
#   • 2 — no Tests Taken, per-standard % only
#   • 3 — Tests Taken + Score AND % + assessment/unit name under each standard
# The payload below is variant-agnostic; the page selects what to show.


class YtdStandardColumn(BaseModel):
    """One per-standard column in the YTD matrix."""

    standard_label: str
    schoology_standard: str
    # Newline/' / '-joined assessment names that touched this standard YTD;
    # rendered under the code in variant 3 only.
    unit_names: str = ""


class YtdCell(BaseModel):
    points_received: float
    points_possible: float
    score_pct: float


class YtdStudentRow(BaseModel):
    """One per-student row inside a Classroom-Instructor group."""

    user_uid: str
    user_name: str
    score_pct: float
    tests_taken: int
    points_received: float
    points_possible: float
    # Per-standard cells keyed by ``standard_label``. Absent key ⇒ "-" (the
    # standard was not assessed for this student); legacy prints a dash.
    cells: dict[str, YtdCell]


class YtdStandardTotal(BaseModel):
    """Per-standard footer values (teacher subtotal + grand total)."""

    points_received: float
    points_possible: float
    score_pct: float


class YtdTeacherGroup(BaseModel):
    section_instructor: str
    teacher_score_pct: float
    students: List[YtdStudentRow]
    # Per-standard subtotal: # Correct Answers (points_received) + Score %.
    standard_subtotals: dict[str, YtdStandardTotal]


class YtdGrandTotal(BaseModel):
    points_received: float
    points_possible: float
    score_pct: float
    # Per-standard grand totals (Possible Points / # Correct / Score %).
    standard_totals: dict[str, YtdStandardTotal]


class YearToDatePerformancePayload(BaseModel):
    """Legacy YTD Longitudinal matrix (replaces the prior analytics dashboard).

    Faithful clone of the three legacy paginated matrices. ``standards`` are the
    column order; ``teacher_groups`` carry the row data + per-teacher subtotals;
    ``grand_total`` carries the report footer rows.
    """

    school: YTDSchoolInfo
    subject: str
    grade: str
    session: str
    assessment_type: str
    standards: List[YtdStandardColumn]
    teacher_groups: List[YtdTeacherGroup]
    grand_total: YtdGrandTotal


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
    # Legacy PBIX's `Total Incorrect Choices` =
    # DISTINCTCOUNT(fact_student_submission[Answer_Submission]) — counts ALL
    # distinct answer submissions for the question, including the correct
    # answer (no Score=0 filter). Equals `distinct_answers`.
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
    filter scope.

    ``cpalms_standard`` is the CPALMS code the legacy PBIX renders in the
    card banner (multiRowCard #3, ``dim_standard.cPalms_Standard``;
    55_standard_summary_spec.md §4); ``schoology_standard`` is the longer
    canonical alias retained for keys/filters.
    """

    schoology_standard: str
    cpalms_standard: str
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


# ─── Dashboard overview + Performance-by-Strand grid ───────────────────────


class DashboardSubjectCard(BaseModel):
    """One subject KPI card on the dashboard (subject grade-average %)."""

    subject: str
    grade_average: Optional[float] = None
    grade_average_pct: str = "—"


class DashboardOverviewPayload(BaseModel):
    """Subject cards + dataset-refresh timestamp for the dashboard front filters."""

    subjects: List[DashboardSubjectCard]
    refreshed_at: Optional[str] = None


class DashboardStrandRow(BaseModel):
    """One per-(assessment × strand) row of the legacy Performance-by-Strand grid."""

    item_id: str
    grade: Optional[str] = None
    strand: str
    total_standards: int = 0
    total_questions: int = 0
    grade_average: Optional[float] = None
    grade_average_pct: str = "—"
    assessment_date: Optional[date] = None
    assessment: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DashboardStrandRowsPage(BaseModel):
    """Server-paginated page of the Performance-by-Strand grid."""

    rows: List[DashboardStrandRow]
    total: int
    limit: int
    offset: int


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


# ─── Paginated reports (ord 6/7/16, 11, 12, 13) ───────────────────────────


class PaginatedKpis(BaseModel):
    """5-cell KPI strip shared by every paginated report."""

    total_questions: int
    total_students: int
    score: float
    total_possible_point: float
    grade_average: float
    grade_average_pct: str


class QsmQuestionColumn(BaseModel):
    """One leaf column header in the QSR matrix."""

    question_id: str
    question_no: str
    sorting_question_no: int
    standard: str
    cpalms_standard: str
    position_number: str
    correct_answer: str


# ── QSR partial-credit model (web JSON + xlsx / SSRS parity) ─────────────────
# The legacy SSRS QSR .xlsx AND the color/teacher PDFs both render *partial
# credit*: each (student × question) cell carries ``points_received`` (which
# may be fractional, e.g. 0.5 / 0.25 / 0.33), "Possible Points" is
# SUM(points_possible), "# Correct Answers" is SUM(points_received), and every
# Score% is SUM(received)/SUM(possible). This is verified cell-for-cell against
# both legacy artifacts for Chapter 9 Test 8359960427 (grand 318 / 486 = 65.4%,
# matching the grade-average KPI) and Central FL Prep 8244629174 (grand 255.55
# correct). The web/JSON QSR matrix and the xlsx export BOTH consume this single
# partial-credit payload (``QuestionSummaryPointsPayload``) so they cannot
# diverge. The legacy binary count-of-green model is retired.


class QspStandardBand(BaseModel):
    """A contiguous CPALMS column band (one or more leaf question columns)."""

    cpalms_standard: str
    question_ids: List[str]


class QspStudentRow(BaseModel):
    """One per-student row with fractional point cells."""

    user_uid: str
    user_name: str
    score_pct: float
    possible_points: float
    correct_count: float
    # qid → points_received (may be fractional); None = not attempted.
    cells: dict[str, Optional[float]]
    # cpalms_standard → band Score% (SUM received / SUM possible in the band).
    band_pct: dict[str, Optional[float]]


class QspTeacherGroup(BaseModel):
    section_instructor: str
    teacher_score_pct: float
    students: List[QspStudentRow]
    # Per-leaf-question teacher subtotals, used by the web "- Teacher" subtotal
    # block (PBIX ord 7). Partial-credit: correct = SUM(points_received),
    # possible = SUM(points_possible), pct = correct/possible.
    per_question_correct: dict[str, float] = {}
    per_question_possible: dict[str, float] = {}
    per_question_pct: dict[str, float] = {}


class QspGrandTotal(BaseModel):
    possible_points: float
    correct_count: float
    score_pct: float
    # Per-leaf-question footer rows (SSRS "Possible Points" / "# Correct
    # Answers" / "Score %"). per_question_pct = received/possible per question.
    per_question_possible: dict[str, float]
    per_question_correct: dict[str, float]
    per_question_pct: dict[str, float]
    # Per-band footer Score% sub-columns (grey C0C0C0, not perf-banded).
    band_possible: dict[str, float]
    band_correct: dict[str, float]
    band_pct: dict[str, float]


class QuestionSummaryPointsPayload(BaseModel):
    """Partial-credit QSR matrix — single source of truth for the web/JSON
    matrix AND the xlsx export.

    Mirrors the legacy SSRS .xlsx exactly: fractional cells, per-band Score%
    sub-columns, summed-points totals. ``kpis`` is populated for the web/JSON
    surface (the xlsx ignores it); the QSR page itself omits the KPI strip
    (PAG-3) but the field keeps the payload aligned with the other paginated
    reports and available to future consumers.
    """

    assessment: AssessmentMeta
    kpis: Optional[PaginatedKpis] = None
    questions: List[QsmQuestionColumn]
    bands: List[QspStandardBand]
    teacher_groups: List[QspTeacherGroup]
    grand_total: QspGrandTotal
    # False for cube-only (parquet-loaded) schools that have no
    # fact_student_submission rows: the per-student matrix body / question
    # columns / teacher groups are empty by design and the frontend should
    # render an explicit empty-state. The grand_total is still cube-derived
    # so the page is not self-contradictory (KPI strip vs all-0 matrix).
    per_student_available: bool = True


class PaginatedQuestionRow(BaseModel):
    """One detail-table row in the QRA paginated reports.

    ``question`` carries unsanitised HTML — the frontend runs it through
    ``formatQuestionHtml`` + ``RichReportHtml`` exactly like the interactive
    QRA, so embedded images and inline markup render identically across
    interactive and paginated views.
    """

    question_id: str
    question_no: str
    sorting_question_no: int
    position_number: str
    question: str
    correct_answer: str
    grade_average: float
    grade_average_pct: str
    incorrect_choice_details: str
    incorrect_details_name: str
    standards: str
    cpalms_standard: str


class QraPaginatedPayload(BaseModel):
    """PBIX ord 11 — Question Response Analysis paginated."""

    assessment: AssessmentMeta
    kpis: PaginatedKpis
    questions: List[PaginatedQuestionRow]


class QraTeacherGroup(BaseModel):
    section_instructor: str
    teacher_grade_average: float
    teacher_grade_average_pct: str
    questions: List[PaginatedQuestionRow]


class QraByTeacherPayload(BaseModel):
    """PBIX ord 12 — Question Response Analysis by Teacher."""

    assessment: AssessmentMeta
    kpis: PaginatedKpis
    teacher_groups: List[QraTeacherGroup]


class QraStandardTeacherGroup(BaseModel):
    section_instructor: str
    teacher_standard_average: float
    teacher_standard_average_pct: str
    questions: List[PaginatedQuestionRow]


class QraStandardGroup(BaseModel):
    cpalms_standard: str
    standard_description: str
    standard_average: float
    standard_average_pct: str
    teacher_groups: List[QraStandardTeacherGroup]


class QraByStandardTeacherPayload(BaseModel):
    """PBIX ord 13 — Question Response Analysis by Standard and Teacher."""

    assessment: AssessmentMeta
    kpis: PaginatedKpis
    standard_groups: List[QraStandardGroup]
