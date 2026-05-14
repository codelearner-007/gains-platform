"""Tests for app.jobs.parsers.submission_summary using the real Athenian Quiz #5 file."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.jobs.parsers import submission_summary as parser


SAMPLE = Path(__file__).resolve().parents[3] / "data" / "Athenian" / "2025-26" / \
    "1 - Lesson  Assessments" / "Mathematics" / "Grade 5" / "Sec 1" / \
    "Submission-Summary-Weekly-Math-quiz--5-volume-of-composite-figures-exponents-interpret-remainders-add-subtract-multiply-divide-decimals-2026-05-05-062438.csv"


def test_sample_file_exists() -> None:
    """Bail early if the test corpus is missing."""
    if not SAMPLE.exists():
        pytest.skip(f"Sample file not present: {SAMPLE}")


def test_row_count_19_students_x_10_questions() -> None:
    """The Quiz #5 sample has 19 students, 10 Question-N columns -> 190 melted rows."""
    if not SAMPLE.exists():
        pytest.skip("sample file missing")
    school_id = uuid4()
    run_id = uuid4()

    rows = parser.parse(
        csv_bytes=SAMPLE.read_bytes(),
        school_id=school_id,
        ingestion_run_id=run_id,
        source_file_path="2025-26/1 - Lesson  Assessments/Mathematics/Grade 5/Sec 1/" + SAMPLE.name,
        source_file_hash="dummyhash",
    )
    assert len(rows) == 190


def test_first_row_fields() -> None:
    if not SAMPLE.exists():
        pytest.skip("sample file missing")
    school_id = uuid4()
    run_id = uuid4()

    rows = parser.parse(
        csv_bytes=SAMPLE.read_bytes(),
        school_id=school_id,
        ingestion_run_id=run_id,
        source_file_path="x",
        source_file_hash="h",
    )
    r = rows[0]
    # The first student in the CSV is Isabel Biedler / Schoology ID 85649679
    assert r.schoology_id == "85649679"
    assert r.first_name == "Isabel"
    assert r.last_name == "Biedler"
    assert r.submission_no == 1
    assert r.submission_score == 7.0
    assert r.question_label == "Question 1"
    # Question 1 score for Isabel is 0
    assert r.question_score == 0.0


def test_unique_key_distinct_per_question_for_one_student() -> None:
    if not SAMPLE.exists():
        pytest.skip("sample file missing")
    rows = parser.parse(
        csv_bytes=SAMPLE.read_bytes(),
        school_id=uuid4(),
        ingestion_run_id=uuid4(),
        source_file_path="x",
        source_file_hash="h",
    )
    one_student = [r for r in rows if r.schoology_id == "85649679"]
    assert len(one_student) == 10
    keys = {r.unique_key for r in one_student}
    assert len(keys) == 10  # all distinct
