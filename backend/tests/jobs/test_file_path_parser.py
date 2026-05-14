"""Tests for app.jobs.file_path_parser."""

from __future__ import annotations

import pytest

from app.jobs.file_path_parser import (
    ParsedPath,
    PathParseError,
    classify_file_type,
    make_relative,
    parse_relative_path,
)


class TestParseRelativePath:
    def test_athenian_canonical(self) -> None:
        """The Athenian Quiz #5 path used as the pilot."""
        rel = "2025-26/1 - Lesson  Assessments/Mathematics/Grade 5/Sec 1/Question-Data-Foo.csv"
        p = parse_relative_path(rel)
        assert p == ParsedPath(
            session="2025-26",
            assessment_type="Lesson  Assessments",  # double-space PRESERVED
            subject="Mathematics",
            grade="Grade 5",
            section="Sec 1",
            file_name="Question-Data-Foo.csv",
        )

    def test_double_space_preserved(self) -> None:
        """Notebook + scraper convention: '1 - Lesson  Assessments' has TWO spaces."""
        p = parse_relative_path(
            "2025-26/1 - Lesson  Assessments/Math/Grade K/Sec 1/Student-Submissions-X.csv"
        )
        assert p.assessment_type == "Lesson  Assessments"
        assert "  " in p.assessment_type  # exactly two spaces between Lesson and Assessments

    def test_non_numeric_section(self) -> None:
        """Section names like 'Sec 1st Grade Team' must be accepted as-is."""
        p = parse_relative_path(
            "2025-26/1 - Lesson  Assessments/Other/Grade K/Sec 1st Grade Team/X.csv"
        )
        assert p.section == "Sec 1st Grade Team"

    def test_assessment_type_no_dash(self) -> None:
        """If the assessment-type folder has no '-', use it as-is (trimmed)."""
        p = parse_relative_path(
            "2025-26/Pop Quiz/Math/Grade 5/Sec 1/Submission-Summary-A.csv"
        )
        assert p.assessment_type == "Pop Quiz"

    def test_assessment_type_strips_only_first_dash(self) -> None:
        """Notebook line 219: split on FIRST '-'; preserve subsequent dashes."""
        p = parse_relative_path(
            "2025-26/2 - Mid-Year Test/Math/Grade 5/Sec 1/Question-Data-A.csv"
        )
        # everything after the first '-' is taken; leading/trailing spaces stripped
        assert p.assessment_type == "Mid-Year Test"

    def test_strips_subject_grade_section_whitespace(self) -> None:
        p = parse_relative_path(
            "2025-26/1 - Lesson  Assessments/  Math  /  Grade 5  /  Sec 1  /Q-X.csv"
        )
        assert p.subject == "Math"
        assert p.grade == "Grade 5"
        assert p.section == "Sec 1"

    def test_backslashes_normalized(self) -> None:
        """Windows-style path inputs are accepted."""
        p = parse_relative_path(
            r"2025-26\1 - Lesson  Assessments\Math\Grade 5\Sec 1\Submission-Summary-A.csv"
        )
        assert p.session == "2025-26"
        assert p.subject == "Math"
        assert p.section == "Sec 1"

    def test_too_few_parts_raises(self) -> None:
        with pytest.raises(PathParseError):
            parse_relative_path("2025-26/Math/Grade 5/X.csv")

    def test_too_many_parts_raises(self) -> None:
        with pytest.raises(PathParseError):
            parse_relative_path(
                "2025-26/A/B/C/D/E/F/Question-Data-X.csv"
            )

    def test_file_type_routing(self) -> None:
        p = parse_relative_path(
            "2025-26/1 - Lesson  Assessments/Math/Grade 5/Sec 1/Question-Data-X.csv"
        )
        assert p.file_type == "question_data"

        p = parse_relative_path(
            "2025-26/1 - Lesson  Assessments/Math/Grade 5/Sec 1/Submission-Summary-X.csv"
        )
        assert p.file_type == "submission_summary"

        p = parse_relative_path(
            "2025-26/1 - Lesson  Assessments/Math/Grade 5/Sec 1/Student-Submissions-X.csv"
        )
        assert p.file_type == "student_submissions"


class TestClassifyFileType:
    def test_question_data(self) -> None:
        assert classify_file_type("Question-Data-Foo.csv") == "question_data"

    def test_submission_summary(self) -> None:
        assert classify_file_type("Submission-Summary-Bar.csv") == "submission_summary"

    def test_student_submissions(self) -> None:
        assert classify_file_type("Student-Submissions-Baz.csv") == "student_submissions"

    def test_unknown_raises(self) -> None:
        with pytest.raises(PathParseError):
            classify_file_type("Random-File.csv")


class TestMakeRelative:
    def test_unix_paths(self) -> None:
        rel = make_relative("/data/Athenian/2025-26/A/B/C/D/X.csv", "/data/Athenian")
        assert rel == ("2025-26", "A", "B", "C", "D", "X.csv")

    def test_mixed_separators(self) -> None:
        rel = make_relative(
            r"E:\data\Athenian\2025-26\A\B\C\D\X.csv",
            r"E:\data\Athenian",
        )
        assert rel == ("2025-26", "A", "B", "C", "D", "X.csv")

    def test_root_not_prefix_raises(self) -> None:
        with pytest.raises(PathParseError):
            make_relative("/data/foo/X.csv", "/data/bar")
