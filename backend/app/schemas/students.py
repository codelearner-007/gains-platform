"""Pydantic schemas for the per-student reporting endpoints.

Two surfaces:

* ``GET /students/browse``  → :class:`StudentBrowsePage` — the dashboard "By
  Students" roster: one summary row per student in the current filter scope.
* ``GET /students/{uid}/report`` → :class:`PerStudentReportPayload` — a single
  student's full, multi-subject report.

All percentages are 0–100 floats (one-ish decimal) for direct display, paired
with a server-computed ``band`` string (``green`` / ``yellow`` / ``pink`` /
``na``) so the frontend maps band→colour via ``lib/reports/colors.ts`` without
duplicating the 70/80 thresholds. Every number is derived from the canonical
grain-B fact collapse (see ``student_repository``), so a student's figures
reconcile with the assessment/dashboard reports.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ─────────────────────────── shared ────────────────────────────


class MasteryDist(BaseModel):
    """Count of a student's standards falling in each performance band."""

    green: int = 0
    yellow: int = 0
    pink: int = 0
    total: int = 0


# ─────────────────────── browse (roster) ───────────────────────


class StudentSubjectStat(BaseModel):
    """One (subject, grade) chip in a roster row."""

    subject: str
    grade: Optional[str] = None
    pct: Optional[float] = None
    band: str = "na"


class StudentBrowseRow(BaseModel):
    """One student in the dashboard "By Students" roster."""

    uid: str
    name: str
    grades: List[str] = []
    overall_pct: Optional[float] = None
    overall_band: str = "na"
    n_subjects: int = 0
    n_assessments: int = 0
    subjects: List[StudentSubjectStat] = []
    mastery: MasteryDist = MasteryDist()

    model_config = ConfigDict(from_attributes=True)


class StudentBrowsePage(BaseModel):
    """One server-paginated page of the roster plus the full scoped total."""

    rows: List[StudentBrowseRow]
    total: int
    limit: int
    offset: int


# ─────────────────────── full report ───────────────────────────


class StudentIdentity(BaseModel):
    uid: str
    name: str
    first: Optional[str] = None
    last: Optional[str] = None
    grad_year: Optional[str] = None
    gender: Optional[str] = None


class ReportSchoolInfo(BaseModel):
    name: str = ""
    logo_url: Optional[str] = None
    current_session: str = ""


class StudentAssessmentRow(BaseModel):
    """One assessment the student sat, within a subject (merged identity)."""

    item_id: str  # carries subject_id (merged, section-agnostic assessment id)
    name: str
    date: Optional[str] = None
    n_questions: int = 0
    score: Optional[float] = None
    possible: Optional[float] = None
    pct: Optional[float] = None
    band: str = "na"
    class_pct: Optional[float] = None


class StudentStandardRow(BaseModel):
    """Per-standard mastery for the student (all-attribution grain)."""

    identifier: str
    code: str
    description: Optional[str] = None
    strand: Optional[str] = None
    cluster: Optional[str] = None
    complexity: Optional[str] = None
    direct_link: Optional[str] = None
    n_questions: int = 0
    pct: Optional[float] = None
    band: str = "na"


class StudentStrandRow(BaseModel):
    strand: str
    n_questions: int = 0
    pct: Optional[float] = None
    band: str = "na"


class StudentSubjectReport(BaseModel):
    subject: str
    grade: Optional[str] = None
    assessment_types: Optional[str] = None
    pct: Optional[float] = None
    band: str = "na"
    score: Optional[float] = None
    possible: Optional[float] = None
    n_questions: int = 0
    n_assessments: int = 0
    class_pct: Optional[float] = None
    class_n_students: Optional[int] = None
    mastery: MasteryDist = MasteryDist()
    assessments: List[StudentAssessmentRow] = []
    standards: List[StudentStandardRow] = []
    strands: List[StudentStrandRow] = []


class StudentOverall(BaseModel):
    pct: Optional[float] = None
    band: str = "na"
    score: Optional[float] = None
    possible: Optional[float] = None
    n_subjects: int = 0
    n_assessments: int = 0
    n_standards: int = 0
    class_pct: Optional[float] = None
    class_n_students: Optional[int] = None
    mastery: MasteryDist = MasteryDist()


class PerStudentReportPayload(BaseModel):
    """The full per-student, multi-subject report."""

    student: StudentIdentity
    school: ReportSchoolInfo
    session: str = ""
    grades: List[str] = []
    overall: StudentOverall
    subjects: List[StudentSubjectReport] = []
    has_data: bool = True
