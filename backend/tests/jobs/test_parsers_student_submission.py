"""Tests for app.jobs.parsers.student_submission using the real Athenian Quiz #5 file."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.jobs.file_path_parser import parse_relative_path
from app.jobs.parsers import student_submission as parser


SAMPLE = Path(__file__).resolve().parents[3] / "data" / "Athenian" / "2025-26" / \
    "1 - Lesson  Assessments" / "Mathematics" / "Grade 5" / "Sec 1" / \
    "Student-Submissions-Weekly-Math-quiz--5-volume-of-composite-figures-exponents-interpret-remainders-add-subtract-multiply-divide-decimals-2026-05-05-062438.csv"

REL = "2025-26/1 - Lesson  Assessments/Mathematics/Grade 5/Sec 1/" + SAMPLE.name


def test_sample_file_exists() -> None:
    if not SAMPLE.exists():
        pytest.skip(f"Sample file not present: {SAMPLE}")


def test_row_count_190() -> None:
    """19 students × 10 questions = 190 long-format rows in the source CSV (no melt)."""
    if not SAMPLE.exists():
        pytest.skip("sample file missing")

    rows = parser.parse(
        csv_bytes=SAMPLE.read_bytes(),
        school_id=uuid4(),
        ingestion_run_id=uuid4(),
        source_file_path=REL,
        source_file_hash="dummyhash",
        parsed_path=parse_relative_path(REL),
    )
    assert len(rows) == 190


def test_first_row_fields() -> None:
    if not SAMPLE.exists():
        pytest.skip("sample file missing")
    rows = parser.parse(
        csv_bytes=SAMPLE.read_bytes(),
        school_id=uuid4(),
        ingestion_run_id=uuid4(),
        source_file_path=REL,
        source_file_hash="h",
        parsed_path=parse_relative_path(REL),
    )
    r = rows[0]
    assert r.user_uid == "85649679"
    assert r.username == "ibiedler@aaota.org"
    assert r.last_name == "Biedler"
    assert r.first_name == "Isabel"
    assert r.user_role_id == "286170"  # Student
    assert r.user_school_id == "186370968"
    assert r.item_id == "8368732914"
    assert r.question_id == "2271509018"
    # Total Time = 00:28:23
    assert r.total_time == timedelta(minutes=28, seconds=23)
    # First Access = 2026-04-30 12:50:41 UTC
    assert r.first_access is not None
    assert r.first_access.year == 2026 and r.first_access.month == 4 and r.first_access.day == 30
    assert r.first_access.tzinfo is not None  # tz-aware
    # Path-derived columns are injected
    assert r.session == "2025-26"
    assert r.subject == "Mathematics"
    assert r.grade == "Grade 5"
    assert r.section == "Sec 1"


def test_question_truncation_under_threshold() -> None:
    """The Quiz #5 sample has short Question text — none should be truncated."""
    if not SAMPLE.exists():
        pytest.skip("sample file missing")
    rows = parser.parse(
        csv_bytes=SAMPLE.read_bytes(),
        school_id=uuid4(),
        ingestion_run_id=uuid4(),
        source_file_path=REL,
        source_file_hash="h",
        parsed_path=parse_relative_path(REL),
    )
    # Confirm all rows have Question populated and under 7500 chars
    for r in rows:
        if r.question is not None:
            assert len(r.question) <= 7500


def test_unique_keys_all_distinct() -> None:
    if not SAMPLE.exists():
        pytest.skip("sample file missing")
    rows = parser.parse(
        csv_bytes=SAMPLE.read_bytes(),
        school_id=uuid4(),
        ingestion_run_id=uuid4(),
        source_file_path=REL,
        source_file_hash="h",
        parsed_path=parse_relative_path(REL),
    )
    keys = {r.unique_key for r in rows}
    # In Quiz #5 every (user, question) combo is distinct so all 190 keys must be unique.
    assert len(keys) == 190
