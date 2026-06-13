"""Pydantic schemas for the assessments endpoints."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AssessmentListRow(BaseModel):
    """One row in the assessment list. dim_item joined with dim_subject."""

    item_id: str
    item_name: Optional[str] = None
    item_type: Optional[str] = None
    subject_id: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    session: Optional[str] = None
    assessment_type: Optional[str] = None
    section_name: Optional[str] = None
    section_instructors: Optional[str] = None
    assessment_date: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


class AssessmentSummaryListRow(AssessmentListRow):
    """List row enriched with the per-assessment grade average + student count
    for the dashboard "Assessments Summary — By Assessment" grade-average bars.
    Both are nullable: fact-less items or items absent from the cube resolve to
    ``None`` (rendered as an em-dash, never zero)."""

    grade_average: Optional[float] = None
    total_students: Optional[int] = None


class AssessmentDetail(BaseModel):
    """A single dim_item record with metadata."""

    item_id: str
    item_name: Optional[str] = None
    item_type: Optional[str] = None
    subject_id: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    session: Optional[str] = None
    assessment_type: Optional[str] = None
    section_name: Optional[str] = None
    section_instructors: Optional[str] = None
    assessment_date: Optional[date] = None
    school_id: str

    model_config = ConfigDict(from_attributes=True)


class AssessmentSummary(BaseModel):
    """cube_school_summary + cube_grade_summary slice for one assessment."""

    item_id: str
    total_questions: int
    total_standards: int
    total_students: int
    total_possible_point: float
    total_score: float
    grade_average: float
    percentage_incorrect_answers: float
    grade_min: Optional[float] = None
    grade_max: Optional[float] = None
