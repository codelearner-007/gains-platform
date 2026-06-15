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
        # 4 parts (or fewer) cannot be unambiguously mapped — subject/grade
        # would collide with session/assessment_type.
        with pytest.raises(PathParseError):
            parse_relative_path("2025-26/Math/Grade 5/X.csv")

    def test_extra_subject_category_absorbed_7_part(self) -> None:
        """7-part backup variant: an interposed subject-category folder is
        absorbed; subject/grade/section anchor to the deepest canonical levels
        (e.g. Crestwell's Summative/Science exports)."""
        p = parse_relative_path(
            "2025-26/Summative/Science/3 - Science/1 - Grade 1/Sec 01 SCI - C/"
            "Student-Submissions-Unit-4-Benchmark.csv"
        )
        assert p.session == "2025-26"
        assert p.assessment_type == "Summative"
        assert p.subject == "3 - Science"  # deepest subject, not the "Science" category
        assert p.grade == "1 - Grade 1"
        assert p.section == "Sec 01 SCI - C"
        assert p.file_name == "Student-Submissions-Unit-4-Benchmark.csv"

    def test_sectionless_5_part(self) -> None:
        """5-part backup variant: file directly under the grade folder with no
        section subfolder — section is left empty (not skipped)."""
        p = parse_relative_path(
            "2024-25/1 - Lesson  Assessments/4 - ELA/3 - Grade 3/"
            "Student-Submissions-Module-Assessment.csv"
        )
        assert p.assessment_type == "Lesson  Assessments"
        assert p.subject == "4 - ELA"
        assert p.grade == "3 - Grade 3"
        assert p.section == ""

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
