"""Contract test: the scraper's storage key must stay parseable by the backend.

WHY
---
The scraper and the ingestion backend are separate programs in different
languages that agree on ONE thing: the Supabase Storage object key.

    scraper/schoology-exporter.js  builds  <short_name>/<session>/<category>/
                                           <subject>/<grade>/<section>/<filename>
    backend/app/jobs/blob_client.py        strips the <short_name> root
    backend/app/jobs/file_path_parser.py   parses the remainder POSITIONALLY

Nothing else enforces that agreement. The parser does not validate — it splits on
"/" and indexes, so a key with one extra or one missing component does not fail
loudly; it silently yields a WRONG subject/grade/section and lands mislabelled
rows in ``raw_*``. Several columns here are load-bearing in non-obvious ways:

  * ``"1 - Lesson  Assessments"`` contains TWO spaces after "Lesson". The parser
    strips only the ``"<digit> - "`` prefix, so the double space survives into
    ``assessment_type`` and every downstream dimension key. Normalising it (an
    easy "tidy-up") silently forks the assessment-type dimension.
  * subject/grade/section are END-anchored (parts[-4:-1]), which is what lets an
    interposed category folder pass through harmlessly.
  * file routing is by FILENAME PREFIX only, so renaming an export breaks
    ingestion with a PathParseError.

These tests exercise the real keys the scraper emits for the three live schools,
so a change on either side of the contract fails here rather than in production.

DB-FREE: pure parsing, no database, no network.
"""

from __future__ import annotations

import pytest

from app.jobs.file_path_parser import (
    ParsedPath,
    PathParseError,
    classify_file_type,
    parse_relative_path,
)

# The exact category literal seeded as schools.category_folder_override for all
# three live schools (verified against prod). NOTE THE DOUBLE SPACE.
CATEGORY = "1 - Lesson  Assessments"
ASSESSMENT_TYPE = "Lesson  Assessments"


def _key(session="2025-26", category=CATEGORY, subject="Mathematics",
         grade="Grade 5", section="Sec MATH-05A",
         filename="Question-Data-Weekly-Quiz-2-2026-05-05-063712.csv") -> str:
    """A storage key as the scraper builds it, RELATIVE to the school root.

    Mirrors schoology-exporter.js: `${assignmentId}:${session}/${categoryFolder}/
    ${subjectName}/${gradeName}/${sectionName}/` + original filename.
    """
    return f"{session}/{category}/{subject}/{grade}/{section}/{filename}"


# ── The canonical 6-part key ───────────────────────────────────────────────


def test_canonical_key_parses_to_the_expected_fields() -> None:
    parsed = parse_relative_path(_key())
    assert isinstance(parsed, ParsedPath)
    assert parsed.session == "2025-26"
    assert parsed.assessment_type == ASSESSMENT_TYPE
    assert parsed.subject == "Mathematics"
    assert parsed.grade == "Grade 5"
    assert parsed.section == "Sec MATH-05A"
    assert parsed.file_name.startswith("Question-Data-")


def test_double_space_in_assessment_type_is_preserved() -> None:
    """The single most fragile character in the contract."""
    parsed = parse_relative_path(_key())
    assert parsed.assessment_type == "Lesson  Assessments"
    assert "  " in parsed.assessment_type, "double space collapsed — dimension keys will fork"
    assert parsed.assessment_type != "Lesson Assessments"


def test_numeric_prefix_is_stripped_from_the_category_folder() -> None:
    assert parse_relative_path(_key(category="1 - Lesson  Assessments")).assessment_type == ASSESSMENT_TYPE
    assert parse_relative_path(_key(category="2 - Chapter Assessments")).assessment_type == "Chapter Assessments"


# ── Per-school reality check ───────────────────────────────────────────────


@pytest.mark.parametrize("short_name", ["Athenian", "CFP", "Crestwell"])
def test_school_root_is_stripped_before_parsing(short_name: str) -> None:
    """The blob client yields paths relative to the school root. If the root ever
    leaked into the parsed path, ``session`` would become the school name and
    every row would be stamped with a nonexistent session."""
    relative = _key()
    parsed = parse_relative_path(relative)
    assert parsed.session == "2025-26"
    # The full object key, for reference — must NOT be what the parser receives.
    full_key = f"{short_name}/{relative}"
    assert parse_relative_path(full_key).session == short_name, (
        "sanity: parsing the UNSTRIPPED key misreads session — this is why "
        "blob_client must strip the school root"
    )


# ── File-type routing (filename prefix only) ───────────────────────────────


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("Question-Data-World-History-Weekly-Quiz-2-2026-05-05-063712.csv", "question_data"),
        ("Student-Submissions-World-History-Weekly-Quiz-2-2026-05-05-063712.csv", "student_submissions"),
        ("Submission-Summary-World-History-Weekly-Quiz-2-2026-05-05-063712.csv", "submission_summary"),
    ],
)
def test_the_three_exported_types_route_to_a_parser(filename: str, expected: str) -> None:
    assert classify_file_type(filename) == expected
    assert parse_relative_path(_key(filename=filename)).file_type == expected


def test_an_unrecognised_filename_prefix_fails_loudly() -> None:
    """The scraper's export form ticks a fourth checkbox whose output has no
    parser. It must never be uploaded — and if it ever is, ingestion must raise
    rather than guess."""
    with pytest.raises((PathParseError, ValueError)):
        classify_file_type("Questions-Export-2026-05-05-063712.csv")


# ── Structural variants and failure modes ──────────────────────────────────


def test_five_part_key_treats_the_missing_component_as_an_absent_section() -> None:
    """A file sitting directly under <grade> (no section folder)."""
    parsed = parse_relative_path(
        f"2025-26/{CATEGORY}/Mathematics/Grade 5/Question-Data-x-2026-05-05-063712.csv"
    )
    assert parsed.section == ""
    assert parsed.grade == "Grade 5"
    assert parsed.subject == "Mathematics"


def test_subject_grade_section_are_end_anchored() -> None:
    """An interposed folder must not shift subject/grade/section, which is the
    property that makes the 7-part legacy variant safe."""
    parsed = parse_relative_path(
        f"2025-26/{CATEGORY}/Middle School/Mathematics/Grade 5/Sec 1/"
        "Question-Data-x-2026-05-05-063712.csv"
    )
    assert parsed.subject == "Mathematics"
    assert parsed.grade == "Grade 5"
    assert parsed.section == "Sec 1"


def test_too_few_components_raises_rather_than_misparsing() -> None:
    with pytest.raises(PathParseError):
        parse_relative_path("2025-26/Question-Data-x.csv")


def test_section_names_may_be_non_numeric() -> None:
    """Real Schoology section codes are free text; the parser must not validate.

    The "/"-bearing case belongs to the PRODUCER (a slash must never reach here)
    and is covered in scraper/tests/paths.test.js. Applying .replace() to both the
    input and the expectation here would only assert a tautology.
    """
    for section in ["Sec 1", "Sec MATH-05A", "Sec 1st Grade Team"]:
        assert parse_relative_path(_key(section=section)).section == section


def test_processed_prefix_is_reserved_and_must_not_collide_with_a_school() -> None:
    """The worker archives consumed files to ``processed/<short_name>/<run_id>/``.
    A school whose short_name were 'processed' would make archived files
    indistinguishable from live ones. The DB enforces this
    (20260723090000_ingestion_durability.sql); asserted here so the reservation
    is visible next to the key contract it protects."""
    parsed = parse_relative_path(_key())
    assert parsed.session != "processed"
    # An archived path parses "successfully" but with garbage fields — which is
    # exactly why re-ingesting the processed/ prefix must never be configured.
    archived = parse_relative_path(
        f"processed/Athenian/{'0' * 8}/2025-26/{CATEGORY}/Mathematics/Grade 5/Sec 1/"
        "Question-Data-x-2026-05-05-063712.csv"
    )
    assert archived.session == "processed", (
        "archived paths misparse by design — the blob client must never list "
        "the processed/ prefix as a school root"
    )
