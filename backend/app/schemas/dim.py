"""Pydantic schemas for the dimension lookup endpoints."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class StandardRow(BaseModel):
    """dim_standard row (global lookup)."""

    uniques_id: str
    identifier: str
    schoology_standard: Optional[str] = None
    standard_new: Optional[str] = None
    strand: Optional[str] = None
    subject: Optional[str] = None
    cluster: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StrandRow(BaseModel):
    """dim_strand row (global lookup)."""

    identifier: Optional[str] = None
    strand: Optional[str] = None
    strand_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SubjectRow(BaseModel):
    """dim_subject row (per-school)."""

    subject_id: str
    subject: Optional[str] = None
    grade: Optional[str] = None
    session: Optional[str] = None
    assessment_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GradeRow(BaseModel):
    grade_id: str
    grade: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SectionRow(BaseModel):
    """Scoped section option: one classroom (``section_name`` +
    ``section_instructors``) whose split Schoology shells are collapsed into
    ``section_nids`` (the comma-joined nid list is the filter value)."""

    section_nids: List[str]
    section_name: Optional[str] = None
    section_instructors: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SessionRow(BaseModel):
    session_id: str
    session: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AssessmentTypeRow(BaseModel):
    """Distinct ``dim_subject.assessment_type`` (per-school)."""

    assessment_type: str

    model_config = ConfigDict(from_attributes=True)


class InstructorRow(BaseModel):
    """Distinct classroom instructor parsed from ``section_instructors``."""

    instructor: str

    model_config = ConfigDict(from_attributes=True)
