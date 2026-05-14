"""Pydantic models matching the raw_* table schemas (supabase/migrations/20260507000040_raw_tables.sql).

Used by parsers to typed-validate every CSV row before INSERT. The DB columns
of type INTEGER, NUMERIC, TIMESTAMPTZ, INTERVAL are validated here rather than
falling through to the database for cleaner errors.

Column names match the DB columns 1:1 (snake_case).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# Numeric values are floats here; asyncpg converts Python floats to Postgres NUMERIC(10,4).
# We could also use Decimal, but float is simpler and accurate enough for our 4 decimal places.


class RawSubmissionSummaryRow(BaseModel):
    """One melted row of Submission-Summary-*.csv (one student × one Question N column)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    school_id: UUID
    ingestion_run_id: UUID
    source_file_path: str
    source_file_hash: str
    unique_key: str

    schoology_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    unique_id_csv: Optional[str] = None
    job_title: Optional[str] = None
    gradebook_grade: Optional[str] = None
    submission_no: Optional[int] = None
    submission_score: Optional[float] = None
    question_label: Optional[str] = None
    question_score: Optional[float] = None


class RawStudentSubmissionRow(BaseModel):
    """One row of Student-Submissions-*.csv (already long-format; no melt)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    school_id: UUID
    ingestion_run_id: UUID
    source_file_path: str
    source_file_hash: str
    unique_key: str

    user_uid: Optional[str] = None
    username: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    user_role_id: Optional[str] = None
    user_school_id: Optional[str] = None
    user_school_name: Optional[str] = None
    course_nid: Optional[str] = None
    course_name: Optional[str] = None
    course_code: Optional[str] = None
    section_nid: Optional[str] = None
    section_name: Optional[str] = None
    section_code: Optional[str] = None
    section_instructors: Optional[str] = None
    item_type: Optional[str] = None
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    first_access: Optional[datetime] = None
    latest_attempt: Optional[datetime] = None
    total_time: Optional[timedelta] = None
    submission_grade: Optional[float] = None
    submission: Optional[int] = None
    question_id: Optional[str] = None
    associated_question_id: Optional[str] = None
    question_type: Optional[str] = None
    question: Optional[str] = None
    position_number: Optional[str] = None
    sub_question: Optional[str] = None
    answer_submission: Optional[str] = None
    correct_answer: Optional[str] = None
    points_received: Optional[float] = None
    points_possible: Optional[float] = None
    session: Optional[str] = None
    assessment_type: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    section: Optional[str] = None
    file_name: Optional[str] = None


class RawQuestionDataRow(BaseModel):
    """One melted row of Question-Data-*.csv (Standards*, Answer_Breakdown* unpivoted)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    school_id: UUID
    ingestion_run_id: UUID
    source_file_path: str
    source_file_hash: str
    unique_key: str

    item_id: Optional[str] = None
    item_name: Optional[str] = None
    question_id: Optional[str] = None
    associated_question_id: Optional[str] = None
    total_points: Optional[float] = None
    question_type: Optional[str] = None
    question: Optional[str] = None
    position_number: Optional[str] = None
    sub_question: Optional[str] = None
    answer_option: Optional[str] = None
    answer_breakdown_count: Optional[int] = None
    answer_breakdown_pct: Optional[float] = None
    correct_answer: Optional[str] = None
    correctly_answered: Optional[float] = None
    most_points_earned: Optional[float] = None
    least_points_earned: Optional[float] = None
    average_points_earned: Optional[float] = None
    standards_val: Optional[str] = None
    session: Optional[str] = None
    assessment_type: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    section: Optional[str] = None
    file_name: Optional[str] = None
    question_no: Optional[str] = None
