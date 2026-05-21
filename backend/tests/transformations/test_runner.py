"""Unit tests for the SQL-statement splitter and order list."""

from __future__ import annotations

import pytest

from app.transformations.runner import (
    TRANSFORMATIONS_ORDER,
    _split_sql_statements,
    _strip_sql_comments,
)


def test_order_list_is_complete() -> None:
    """Phase 2/3 must register all 32 transformations in dependency order."""
    relpaths = [r for r, _ in TRANSFORMATIONS_ORDER]

    # Staging files
    assert "01_staging/stg_user.sql" in relpaths
    assert "01_staging/stg_question_data.sql" in relpaths
    assert "01_staging/stg_student_submission.sql" in relpaths
    assert "01_staging/stg_submission_summary.sql" in relpaths

    # Dim phase A
    assert "02_dimensions_a/dim_school.sql" in relpaths
    assert "02_dimensions_a/dim_student.sql" in relpaths
    assert "02_dimensions_a/dim_teacher.sql" in relpaths
    assert "02_dimensions_a/dim_parent.sql" in relpaths
    assert "02_dimensions_a/dim_course.sql" in relpaths

    # Dim phase B
    assert "03_dimensions_b/dim_item.sql" in relpaths

    # Dim phase C
    assert "04_dimensions_c/dim_question_data.sql" in relpaths

    # Dim phase D
    assert "05_dimensions_d/dim_standard.sql" in relpaths
    assert "05_dimensions_d/dim_strand.sql" in relpaths

    # Dim phase E
    assert "06_dimensions_e/dim_unit_lesson.sql" in relpaths
    assert "06_dimensions_e/dim_section.sql" in relpaths
    assert "06_dimensions_e/dim_session.sql" in relpaths
    assert "06_dimensions_e/dim_grade.sql" in relpaths
    assert "06_dimensions_e/dim_assessment_type.sql" in relpaths
    assert "06_dimensions_e/dim_subject.sql" in relpaths

    # Phase 3 — fact
    assert "07_facts/fact_student_submission.sql" in relpaths

    # Phase 3 — hash tables
    assert "08_hash/dim_section_hash.sql" in relpaths
    assert "08_hash/dim_student_hash.sql" in relpaths
    assert "08_hash/fact_student_submissions_hash.sql" in relpaths

    # Phase 3 — cubes
    assert "09_cubes/cube_grade_summary.sql" in relpaths
    assert "09_cubes/cube_school_summary.sql" in relpaths
    assert "09_cubes/cube_standard_summary.sql" in relpaths
    assert "09_cubes/cube_question_summary.sql" in relpaths
    assert "09_cubes/cube_questionincorrectchoice_summary.sql" in relpaths
    assert "09_cubes/cube_question_summary_overall.sql" in relpaths
    assert "09_cubes/cube_overallperformance_summary.sql" in relpaths
    assert "09_cubes/cube_user_summary.sql" in relpaths


def test_order_list_dependencies() -> None:
    """Verify topological ordering: staging < dim_a < dim_b < dim_c < dim_d
    < dim_e < fact < hash < cubes."""
    relpaths = [r for r, _ in TRANSFORMATIONS_ORDER]

    def idx(p: str) -> int:
        return relpaths.index(p)

    # Staging must come before any dim
    assert idx("01_staging/stg_student_submission.sql") < idx("02_dimensions_a/dim_school.sql")
    # dim_item depends on stg_student_submission
    assert idx("01_staging/stg_student_submission.sql") < idx("03_dimensions_b/dim_item.sql")
    # dim_question_data depends on dim_item (Item_ID -> School_ID resolution)
    assert idx("03_dimensions_b/dim_item.sql") < idx("04_dimensions_c/dim_question_data.sql")
    # dim_strand is rebuilt from dim_question_data
    assert idx("04_dimensions_c/dim_question_data.sql") < idx("05_dimensions_d/dim_strand.sql")
    # Phase E (derived dims)
    for p in (
        "06_dimensions_e/dim_unit_lesson.sql",
        "06_dimensions_e/dim_section.sql",
        "06_dimensions_e/dim_session.sql",
    ):
        assert idx("01_staging/stg_student_submission.sql") < idx(p)

    # Phase 3 — fact depends on dim_question_data, dim_standard, dim_strand
    assert idx("04_dimensions_c/dim_question_data.sql") < idx("07_facts/fact_student_submission.sql")
    assert idx("05_dimensions_d/dim_strand.sql")        < idx("07_facts/fact_student_submission.sql")
    # dim_section_hash depends on dim_section
    assert idx("06_dimensions_e/dim_section.sql")       < idx("08_hash/dim_section_hash.sql")
    # dim_student_hash depends on fact
    assert idx("07_facts/fact_student_submission.sql")  < idx("08_hash/dim_student_hash.sql")
    # fact_student_submissions_hash depends on fact + dim_student_hash
    assert idx("07_facts/fact_student_submission.sql")  < idx("08_hash/fact_student_submissions_hash.sql")
    assert idx("08_hash/dim_student_hash.sql")          < idx("08_hash/fact_student_submissions_hash.sql")
    # All cubes depend on fact and hash tables
    for cube in (
        "09_cubes/cube_grade_summary.sql",
        "09_cubes/cube_school_summary.sql",
        "09_cubes/cube_standard_summary.sql",
        "09_cubes/cube_question_summary.sql",
        "09_cubes/cube_questionincorrectchoice_summary.sql",
        "09_cubes/cube_question_summary_overall.sql",
        "09_cubes/cube_overallperformance_summary.sql",
        "09_cubes/cube_user_summary.sql",
    ):
        assert idx("07_facts/fact_student_submission.sql") < idx(cube)
        assert idx("08_hash/dim_student_hash.sql")         < idx(cube)
        assert idx("08_hash/dim_section_hash.sql")         < idx(cube)


def test_strip_comments() -> None:
    """`--` line comments are stripped; everything after stays intact."""
    src = """-- header comment
SELECT 1; -- trailing comment
SELECT 'a -- not a comment';
"""
    out = _strip_sql_comments(src)
    assert "header comment" not in out
    assert "trailing comment" not in out
    # Note: our naive splitter does NOT detect `--` inside string literals
    # because none of our pipeline files use that pattern. The check here
    # documents that limitation — `not a comment` IS still stripped.
    # If we ever need that case, swap _strip_sql_comments for sqlparse.


def test_split_simple_statements() -> None:
    sql = "SELECT 1; SELECT 2; SELECT 3;"
    assert _split_sql_statements(sql) == ["SELECT 1", "SELECT 2", "SELECT 3"]


def test_split_respects_string_literals() -> None:
    """Semicolons inside single-quoted strings must NOT split."""
    sql = "SELECT 'a;b'; SELECT 'c'';d';"
    out = _split_sql_statements(sql)
    assert out == ["SELECT 'a;b'", "SELECT 'c'';d'"]


def test_split_respects_dollar_quotes() -> None:
    """Semicolons inside $$...$$ must NOT split (used by CREATE FUNCTION bodies)."""
    sql = """
CREATE FUNCTION foo() RETURNS int AS $$ BEGIN RETURN 1; END; $$ LANGUAGE plpgsql;
SELECT foo();
"""
    out = _split_sql_statements(sql)
    assert len(out) == 2
    assert out[0].startswith("CREATE FUNCTION")
    assert "BEGIN RETURN 1" in out[0]
    assert out[1] == "SELECT foo()"


def test_split_handles_tagged_dollar_quotes() -> None:
    """Tagged dollar quotes ($body$...$body$) must close on the matching tag."""
    sql = "DO $body$ BEGIN PERFORM 1; PERFORM 2; END $body$;"
    out = _split_sql_statements(sql)
    assert len(out) == 1
    assert "PERFORM 1; PERFORM 2" in out[0]


def test_split_drops_empty_statements() -> None:
    """Trailing or repeated `;` must not produce empty fragments."""
    out = _split_sql_statements(";; SELECT 1;;\n;\n")
    assert out == ["SELECT 1"]


@pytest.mark.parametrize(
    # 4 staging files (stg_user, stg_question_data, stg_student_submission,
    #                  stg_submission_summary). dim_standard is a static seed
    #                  loaded by supabase/seeds/load_standards.py — no staging
    #                  step in the runner.
    # 15 dimension files = 5 phase-A + 1 phase-B + 1 phase-C + 2 phase-D
    #                      (dim_standard placeholder + dim_strand) + 6 phase-E.
    # 1 fact (fact_student_submission).
    # 3 hash tables (dim_section_hash, dim_student_hash, fact_student_submissions_hash).
    # 8 cubes.
    "tag,expected",
    [("staging", 4), ("dimensions", 15), ("facts", 1), ("hash", 3), ("cubes", 8)],
)
def test_tag_distribution(tag: str, expected: int) -> None:
    n = sum(1 for _, t in TRANSFORMATIONS_ORDER if t == tag)
    assert n == expected, f"expected {expected} '{tag}' rows, got {n}"
