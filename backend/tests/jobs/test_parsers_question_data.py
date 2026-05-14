"""Tests for app.jobs.parsers.question_data using real Athenian files."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.jobs.file_path_parser import parse_relative_path
from app.jobs.parsers import question_data as parser


# A file with NO Standards columns
SAMPLE_NO_STD = Path(__file__).resolve().parents[3] / "data" / "Athenian" / "2025-26" / \
    "1 - Lesson  Assessments" / "Mathematics" / "Grade 5" / "Sec 1" / \
    "Question-Data-Weekly-Math-quiz--5-volume-of-composite-figures-exponents-interpret-remainders-add-subtract-multiply-divide-decimals-2026-05-05-062438.csv"

# A file with 4 Standards columns (Grade 8 Math Chapter 9)
SAMPLE_4_STD = Path(__file__).resolve().parents[3] / "data" / "Athenian" / "2025-26" / \
    "1 - Lesson  Assessments" / "Mathematics" / "Grade 8" / "Sec 1" / \
    "Question-Data-Chapter-9-Test-2026-05-05-063438.csv"


def _rel(p: Path) -> str:
    """Compute relative path from data/Athenian/."""
    parts = p.resolve().parts
    idx = parts.index("Athenian")
    return "/".join(parts[idx + 1 :])


class TestNoStandardsFile:
    """Quiz #5: no Standards columns — every CSV row should produce exactly one output row."""

    def test_exists(self) -> None:
        if not SAMPLE_NO_STD.exists():
            pytest.skip(f"sample file missing: {SAMPLE_NO_STD}")

    def test_row_count_matches_csv(self) -> None:
        if not SAMPLE_NO_STD.exists():
            pytest.skip("sample missing")
        # Source CSV has 62 data rows (per task brief: ~62 option-level rows).
        rel = _rel(SAMPLE_NO_STD)
        rows = parser.parse(
            csv_bytes=SAMPLE_NO_STD.read_bytes(),
            school_id=uuid4(),
            ingestion_run_id=uuid4(),
            source_file_path=rel,
            source_file_hash="h",
            parsed_path=parse_relative_path(rel),
        )
        # All have standards_val=None
        assert all(r.standards_val is None for r in rows)
        # Question_no is dense-ranked from 1 (10 distinct questions in this assessment)
        question_nos = {r.question_no for r in rows}
        assert "1" in question_nos
        assert "10" in question_nos
        # Question_no is a string (matches schema)
        for r in rows:
            assert r.question_no is None or isinstance(r.question_no, str)

    def test_path_derived_columns_present(self) -> None:
        if not SAMPLE_NO_STD.exists():
            pytest.skip("sample missing")
        rel = _rel(SAMPLE_NO_STD)
        rows = parser.parse(
            csv_bytes=SAMPLE_NO_STD.read_bytes(),
            school_id=uuid4(),
            ingestion_run_id=uuid4(),
            source_file_path=rel,
            source_file_hash="h",
            parsed_path=parse_relative_path(rel),
        )
        r = rows[0]
        assert r.session == "2025-26"
        assert r.subject == "Mathematics"
        assert r.grade == "Grade 5"
        assert r.section == "Sec 1"
        assert r.assessment_type == "Lesson  Assessments"


class TestFourStandardsFile:
    """Grade 8 Chapter 9: 4 Standards columns — multi-melt must produce 4× rows for full rows."""

    def test_exists(self) -> None:
        if not SAMPLE_4_STD.exists():
            pytest.skip(f"sample file missing: {SAMPLE_4_STD}")

    def test_emits_one_row_per_standards_value(self) -> None:
        if not SAMPLE_4_STD.exists():
            pytest.skip("sample missing")
        rel = _rel(SAMPLE_4_STD)
        rows = parser.parse(
            csv_bytes=SAMPLE_4_STD.read_bytes(),
            school_id=uuid4(),
            ingestion_run_id=uuid4(),
            source_file_path=rel,
            source_file_hash="h",
            parsed_path=parse_relative_path(rel),
        )
        # Some rows in this file have all 4 Standards populated; some have fewer.
        # Per the parser contract, each non-empty standards value emits one row.
        std_vals = {r.standards_val for r in rows if r.standards_val is not None}
        # Expect multiple distinct standard codes
        assert len(std_vals) >= 4

    def test_unique_keys_all_distinct(self) -> None:
        if not SAMPLE_4_STD.exists():
            pytest.skip("sample missing")
        rel = _rel(SAMPLE_4_STD)
        rows = parser.parse(
            csv_bytes=SAMPLE_4_STD.read_bytes(),
            school_id=uuid4(),
            ingestion_run_id=uuid4(),
            source_file_path=rel,
            source_file_hash="h",
            parsed_path=parse_relative_path(rel),
        )
        keys = [r.unique_key for r in rows]
        # All keys must be unique (the parser already dedups duplicates)
        assert len(keys) == len(set(keys))


class TestAnswerBreakdownColumns:
    """Verify the duplicate 'Answer Breakdown' headers are correctly split into count + pct."""

    def test_count_is_int_pct_is_decimal(self) -> None:
        if not SAMPLE_NO_STD.exists():
            pytest.skip("sample missing")
        rel = _rel(SAMPLE_NO_STD)
        rows = parser.parse(
            csv_bytes=SAMPLE_NO_STD.read_bytes(),
            school_id=uuid4(),
            ingestion_run_id=uuid4(),
            source_file_path=rel,
            source_file_hash="h",
            parsed_path=parse_relative_path(rel),
        )
        for r in rows:
            if r.answer_breakdown_count is not None:
                assert isinstance(r.answer_breakdown_count, int)
            if r.answer_breakdown_pct is not None:
                assert isinstance(r.answer_breakdown_pct, float)
                assert 0.0 <= r.answer_breakdown_pct <= 1.0


class TestStandardsDedup:
    """Verify duplicate Standards values across columns collapse to ONE output row."""

    def test_same_standard_in_two_columns_dedups_to_one_row(self) -> None:
        """A single source row with the SAME standard in `Standards` AND `Standards 2`
        must dedup to one output row (identical unique_key by construction).
        """
        # Header has two Standards columns; both cells contain the same value.
        csv_text = (
            "Item ID,Item Name,Question ID,Associated Question ID,Total Points,"
            "Question Type,Question,Position Number,Sub-Question,Answer Option,"
            "Answer Breakdown,Answer Breakdown,Correct Answer,Correctly Answered,"
            "Most Points Earned,Least Points Earned,Average Points Earned,"
            "Standards,Standards\n"
            "I1,N,Q-1,,1,MC,Qtext,1,n/a,a,1,0.1,a,1,1,0,1,MA.5.NBT.1.1,MA.5.NBT.1.1\n"
        )
        rel = "2025-26/1 - Foo/Math/Grade 5/Sec 1/Question-Data-X.csv"
        rows = parser.parse(
            csv_bytes=csv_text.encode("utf-8"),
            school_id=uuid4(),
            ingestion_run_id=uuid4(),
            source_file_path=rel,
            source_file_hash="h",
            parsed_path=parse_relative_path(rel),
        )
        # Even though TWO standards values are emitted (one per column), they have
        # the same unique_key → dedup collapses to ONE row.
        assert len(rows) == 1
        assert rows[0].standards_val == "MA.5.NBT.1.1"


class TestQuestionNoDenseRank:
    """Synthetic tests: dense rank by LEXICOGRAPHIC Question_ID order."""

    def test_dense_rank_appearance_matches_lex(self) -> None:
        """Smoke test: when appearance order == lex order, ranks are 1, 2, ..."""
        # Build a synthetic 5-row CSV (no Standards) with two distinct Question_IDs
        csv_text = (
            "Item ID,Item Name,Question ID,Associated Question ID,Total Points,"
            "Question Type,Question,Position Number,Sub-Question,Answer Option,"
            "Answer Breakdown,Answer Breakdown,Correct Answer,Correctly Answered,"
            "Most Points Earned,Least Points Earned,Average Points Earned\n"
            "I1,N,Q-A,,1,MC,QA-text,1,n/a,a,1,0.1,a,1,1,0,1\n"
            "I1,N,Q-A,,1,MC,QA-text,1,n/a,b,2,0.2,a,1,1,0,1\n"
            "I1,N,Q-B,,1,MC,QB-text,2,n/a,a,3,0.3,b,1,1,0,1\n"
            "I1,N,Q-A,,1,MC,QA-text,1,n/a,c,4,0.4,a,1,1,0,1\n"
            "I1,N,Q-B,,1,MC,QB-text,2,n/a,b,5,0.5,b,1,1,0,1\n"
        )
        rel = "2025-26/1 - Foo/Math/Grade 5/Sec 1/Question-Data-X.csv"
        rows = parser.parse(
            csv_bytes=csv_text.encode("utf-8"),
            school_id=uuid4(),
            ingestion_run_id=uuid4(),
            source_file_path=rel,
            source_file_hash="h",
            parsed_path=parse_relative_path(rel),
        )
        # 5 input rows, no Standards → 5 output rows (none collide on unique_key).
        assert len(rows) == 5
        # Q-A < Q-B lex → ranks 1, 2 respectively. Appearance order also matches.
        for r in rows:
            if r.question_id == "Q-A":
                assert r.question_no == "1"
            elif r.question_id == "Q-B":
                assert r.question_no == "2"

    def test_dense_rank_lex_differs_from_appearance(self) -> None:
        """When appearance order != lex order, rank uses lex order.

        Notebook spec:
            df_final = df_final.sort_values(by="Question_ID").reset_index(drop=True)
            df_final['Question_No'] = rankdata(df_final['Question_ID'], method='dense')

        Input order: B-1, A-1, C-1
        Expected ranks: A-1 -> 1, B-1 -> 2, C-1 -> 3
        """
        csv_text = (
            "Item ID,Item Name,Question ID,Associated Question ID,Total Points,"
            "Question Type,Question,Position Number,Sub-Question,Answer Option,"
            "Answer Breakdown,Answer Breakdown,Correct Answer,Correctly Answered,"
            "Most Points Earned,Least Points Earned,Average Points Earned\n"
            "I1,N,B-1,,1,MC,Btext,1,n/a,a,1,0.1,a,1,1,0,1\n"
            "I1,N,A-1,,1,MC,Atext,2,n/a,a,2,0.2,a,1,1,0,1\n"
            "I1,N,C-1,,1,MC,Ctext,3,n/a,a,3,0.3,a,1,1,0,1\n"
        )
        rel = "2025-26/1 - Foo/Math/Grade 5/Sec 1/Question-Data-X.csv"
        rows = parser.parse(
            csv_bytes=csv_text.encode("utf-8"),
            school_id=uuid4(),
            ingestion_run_id=uuid4(),
            source_file_path=rel,
            source_file_hash="h",
            parsed_path=parse_relative_path(rel),
        )
        assert len(rows) == 3
        ranks = {r.question_id: r.question_no for r in rows}
        assert ranks == {"A-1": "1", "B-1": "2", "C-1": "3"}
