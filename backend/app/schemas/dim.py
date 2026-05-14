"""Pydantic schemas for the dimension lookup endpoints."""

from __future__ import annotations

from typing import Optional

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
    section_nid: str
    section_code: Optional[str] = None
    section_name: Optional[str] = None
    section_instructors: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SessionRow(BaseModel):
    session_id: str
    session: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
