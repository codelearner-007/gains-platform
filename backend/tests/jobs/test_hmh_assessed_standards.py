"""DB-free unit tests for the HMH Assessed-Standards parser + classifier.

Run in isolation (never the broad tests/jobs suite, whose integration tests
TRUNCATE the dev DB):

    cd backend && ./venv/bin/python -m pytest tests/jobs/test_hmh_assessed_standards.py -q

The fixture uses invented names and synthetic LASIDs (no real student PII) but
real File-02 shapes: three cross-walked Standard Sets each with their own
"Overall" row, quoted commas in descriptions, a blank SASID column, an
`hmh-xxxxxxxx` synthetic LASID, and a cluster (3-segment) standard code.
"""

from __future__ import annotations

import csv
import io
from uuid import uuid4

import pytest

from app.jobs.file_path_parser import (
    PathParseError,
    classify_file_type,
    classify_hmh_file_type,
    is_hmh_file,
)
from app.jobs.parsers import hmh_assessed_standards as h
from app.jobs.unique_key import student_submission_unique_key

_HEADERS = [
    "Academic Year", "District Name", "School Name", "StudentID - SASID",
    "StudentID LASID", "LastName", "FirstName", "Student Grade", "Class Name",
    "Teacher Last Name", "Teacher First Name", "Class Grade", "Subject",
    "Program Name", "Component", "AssignmentName", "Date Completed",
    "Standard Set", "Standard Coding Number", "Standard Description",
    "Points Achieved", "Points Possible", "PercentCorrect",
]

_BEST = "Florida Benchmarks for Excellent Student Thinking Standards - Mathematics - 2020"
_FL2014 = "Florida Standards - Mathematics - 2014"
_CC2010 = "NGA Center/CCSSO Common Core State Standards - Mathematics - 2010"

_STAMPED_NAME = "HMH-AssessedStandards-Weekly-2026-05-13-120000.csv"


def _row(**over: str) -> dict[str, str]:
    base = {
        "Academic Year": "2025-2026", "District Name": "Test District",
        "School Name": "Test School (HMH)", "StudentID - SASID": "",
        "StudentID LASID": "100001", "LastName": "Rivera", "FirstName": "Sam",
        "Student Grade": "7", "Class Name": "7th Grade Math",
        "Teacher Last Name": "Nolan", "Teacher First Name": "Dana",
        "Class Grade": "7", "Subject": "Mathematics",
        "Program Name": "Into Math Florida: Grade 7", "Component": "Interactive Florida Standards Assessments",
        "AssignmentName": "Unit 1 Practice Test", "Date Completed": "2026-05-13",
        "Standard Set": _BEST, "Standard Coding Number": "MA.7.AR.1.1",
        "Standard Description": "Apply properties of operations, using rational coefficients.",
        "Points Achieved": "2.00", "Points Possible": "2.00", "PercentCorrect": "100.00%",
    }
    base.update(over)
    return base


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=_HEADERS)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def _parse(rows: list[dict[str, str]], *, file_name: str = _STAMPED_NAME) -> h.HmhParseResult:
    return h.parse(
        csv_bytes=_csv_bytes(rows),
        school_id=uuid4(),
        ingestion_run_id=uuid4(),
        source_file_path=f"AthenianHMH/hmh/{file_name}",
        source_file_hash="deadbeef",
        schoology_school_id="hmh-10030164",
        student_role_id="hmh-student",
        file_name=file_name,
    )


# A full 3-framework cross-walk for one (student, assignment): two B.E.S.T.
# standard rows + a B.E.S.T. Overall, mirrored into FL-2014 and CC-2010.
def _crosswalked() -> list[dict[str, str]]:
    return [
        _row(**{"Standard Coding Number": "MA.7.AR.1.1", "Points Achieved": "2.00", "Points Possible": "2.00"}),
        _row(**{"Standard Coding Number": "MA.7.GR.1.1", "Points Achieved": "0.00", "Points Possible": "2.00",
                "Standard Description": "Solve problems involving area, surface area, and volume."}),
        _row(**{"Standard Coding Number": "Overall", "Standard Description": "",
                "Points Achieved": "2.00", "Points Possible": "4.00"}),
        _row(**{"Standard Set": _FL2014, "Standard Coding Number": "MAFS.7.EE.1.1", "Points Achieved": "2.00", "Points Possible": "2.00"}),
        _row(**{"Standard Set": _FL2014, "Standard Coding Number": "Overall", "Standard Description": "", "Points Achieved": "2.00", "Points Possible": "4.00"}),
        _row(**{"Standard Set": _CC2010, "Standard Coding Number": "CCSS.Math.Content.7.EE.A.1", "Points Achieved": "2.00", "Points Possible": "2.00"}),
        _row(**{"Standard Set": _CC2010, "Standard Coding Number": "Overall", "Standard Description": "", "Points Achieved": "2.00", "Points Possible": "4.00"}),
    ]


# ── classifier ───────────────────────────────────────────────────────────────
def test_is_hmh_file_accepts_prefix_rejects_schoology():
    assert is_hmh_file(_STAMPED_NAME) is True
    for schoology in ("Student-Submissions-x.csv", "Question-Data-x.csv", "Submission-Summary-x.csv"):
        assert is_hmh_file(schoology) is False


def test_classify_hmh_file_type_and_unknown_raises():
    assert classify_hmh_file_type(_STAMPED_NAME) == "hmh_assessed_standards"
    with pytest.raises(PathParseError):
        classify_hmh_file_type("HMH-SomethingElse-2026-05-13-120000.csv")


def test_schoology_classifier_unaffected():
    assert classify_file_type("Student-Submissions-x.csv") == "student_submissions"
    with pytest.raises(PathParseError):
        classify_file_type(_STAMPED_NAME)  # HMH name is not a Schoology type


# ── file-level validation ────────────────────────────────────────────────────
def test_missing_export_stamp_raises():
    with pytest.raises(ValueError, match="export stamp"):
        _parse([_row()], file_name="HMH-AssessedStandards-latest.csv")


def test_missing_required_headers_raises():
    bad = b"Academic Year,Subject\n2025-2026,Mathematics\n"
    with pytest.raises(ValueError, match="missing required headers"):
        h.parse(csv_bytes=bad, school_id=uuid4(), ingestion_run_id=uuid4(),
                source_file_path="x", source_file_hash="x",
                schoology_school_id="hmh-10030164", student_role_id="hmh-student",
                file_name=_STAMPED_NAME)


# ── filters ──────────────────────────────────────────────────────────────────
def test_only_best_survives_and_overall_skipped():
    r = _parse(_crosswalked())
    # 2 B.E.S.T. standard rows ingested; FL-2014 + CC-2010 + all Overall skipped.
    assert len(r.submission_rows) == 2
    assert {s.question_id for s in r.submission_rows}  # non-empty
    assert r.skipped.non_best_standard_set == 4  # 2 FL2014 + 2 CC2010 rows
    assert r.skipped.overall_rows == 1  # only the B.E.S.T. Overall (others hit non_best first)
    codes = {q.standards_val for q in r.question_rows}
    assert codes == {"MA.7.AR.1.1", "MA.7.GR.1.1"}
    assert "MAFS.7.EE.1.1" not in codes and "CCSS.Math.Content.7.EE.A.1" not in codes


def test_blank_lasid_and_blank_code_and_bad_points_skipped():
    rows = [
        _row(),  # good
        _row(**{"StudentID LASID": ""}),  # blank LASID
        _row(**{"Standard Coding Number": ""}),  # blank code
        _row(**{"Points Achieved": "n/a"}),  # unparseable points
    ]
    r = _parse(rows)
    assert len(r.submission_rows) == 1
    assert r.skipped.blank_lasid == 1
    assert r.skipped.blank_standard_code == 1
    assert r.skipped.unparseable_points == 1


def test_malformed_dimension_rows_skip_and_do_not_abort():
    # One good row + dirty rows (bad year, unmappable grade, US-format date, and
    # a blank Class Name / Assignment / Component / teacher). The good row must
    # survive, the file must NOT raise (a dirty row can't abort the whole export),
    # and every dirty row is counted as malformed_dimension.
    rows = [
        _row(),  # good
        _row(**{"Academic Year": "2025/2026"}),          # malformed session
        _row(**{"Class Grade": "junk"}),                 # unmappable grade
        _row(**{"Date Completed": "05/13/2026"}),        # US-format date, unparseable
        _row(**{"Class Name": ""}),                      # blank section_name
        _row(**{"AssignmentName": ""}),                  # blank item_name
        _row(**{"Component": ""}),                       # blank item_type
        _row(**{"Teacher Last Name": "", "Teacher First Name": ""}),  # no instructor
    ]
    r = _parse(rows)
    assert len(r.submission_rows) == 1
    assert r.skipped.malformed_dimension == 7


def test_hash_avoids_delimiter_collision():
    # Two genuinely-distinct assignments that differ only in where a delimiter-like
    # char falls must NOT collapse to the same item_id (length-prefixed hash).
    a = _parse([_row(**{"AssignmentName": "A|B", "Class Name": "C"})]).submission_rows[0]
    b = _parse([_row(**{"AssignmentName": "A", "Class Name": "B|C"})]).submission_rows[0]
    assert a.item_id != b.item_id


# ── normalizations ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("ay,expected", [("2025-2026", "2025-26"), ("2024-2025", "2024-25")])
def test_session_normalization(ay, expected):
    r = _parse([_row(**{"Academic Year": ay})])
    assert r.submission_rows[0].session == expected


def test_malformed_session_skips_row_not_aborts_file():
    # A non-consecutive Academic Year is a per-row skip (counted), not a file abort.
    r = _parse([_row(**{"Academic Year": "2025-2027"})])
    assert len(r.submission_rows) == 0
    assert r.skipped.malformed_dimension == 1


@pytest.mark.parametrize("g,expected", [
    ("7", "Grade 7"), ("07", "Grade 7"), ("K", "Grade K"),
    ("00", "Grade K"), ("0", "Grade K"), ("PK", "Grade PK"),
])
def test_grade_normalization(g, expected):
    r = _parse([_row(**{"Class Grade": g})])
    assert r.submission_rows[0].grade == expected


def test_subject_and_assessment_type_normalization():
    r = _parse([
        _row(**{"Subject": "Mathematics", "Component": "Interactive Florida Standards Assessments"}),
        _row(**{"Standard Coding Number": "MA.7.GR.1.1", "Subject": "English Language Arts", "Component": "Interactive Lesson"}),
    ])
    got = {(s.subject, s.assessment_type) for s in r.submission_rows}
    # HMH's discipline names normalize to the GAINS Schoology-feed vocabulary.
    assert ("Mathematics", "Assessment") in got
    assert ("ELA", "Lesson") in got


# ── synthetic ids + invariants ───────────────────────────────────────────────
def test_answer_columns_null_and_sentinel_never_in_data():
    r = _parse(_crosswalked())
    for s in r.submission_rows:
        assert s.answer_submission is None
        assert s.correct_answer is None
        for v in s.model_dump().values():
            assert v != "DEFAULT_ANSWER_SUBMISSION"


def test_ids_are_prefixed_and_gate_fields_nonnull():
    r = _parse(_crosswalked())
    for s in r.submission_rows:
        assert s.item_id.startswith("hmh-i-")
        assert s.question_id.startswith("hmh-q-")
        assert s.section_nid.startswith("hmh-s-")
        assert s.position_number == "1"
        # dim_item 7-col NOT-NULL gate
        assert all([s.item_id, s.subject, s.section_name, s.section_instructors,
                    s.item_type, s.item_name, s.latest_attempt])
        # user_school_id / user_role_id must match the seeded sentinels
        assert s.user_school_id == "hmh-10030164"
        assert s.user_role_id == "hmh-student"


def test_id_determinism_and_row_order_independence():
    rows = _crosswalked()
    a = _parse(rows)
    b = _parse(list(reversed(rows)))

    def key(res: h.HmhParseResult) -> list[tuple[str, str, str]]:
        return sorted((s.item_id, s.question_id, s.user_uid) for s in res.submission_rows)

    assert key(a) == key(b)


def test_distinct_grade_yields_distinct_item_id():
    r = _parse([
        _row(**{"Class Grade": "6", "Class Name": "6th Grade Math"}),
        _row(**{"Class Grade": "7", "Class Name": "7th Grade Math"}),
    ])
    assert len({s.item_id for s in r.submission_rows}) == 2


def test_one_question_row_per_distinct_item_standard():
    r = _parse(_crosswalked())
    qids = {s.question_id for s in r.submission_rows}
    assert len(qids) == len(r.question_rows)
    assert all(q.question_id in qids for q in r.question_rows)


def test_unique_key_matches_canonical_builder():
    r = _parse([_row()])
    s = r.submission_rows[0]
    expected = student_submission_unique_key(
        user_uid=s.user_uid, item_id=s.item_id, question_id=s.question_id,
        position_number=s.position_number, answer_submission=None,
        points_received=s.points_received, points_possible=s.points_possible,
        submission=1, correct_answer=None,
    )
    assert s.unique_key == expected


def test_synthetic_lasid_preserved_as_string():
    r = _parse([_row(**{"StudentID LASID": "hmh-ea670103"})])
    assert r.submission_rows[0].user_uid == "hmh-ea670103"


def test_oracle_divergence_warns_on_undercount(caplog):
    import logging
    # One B.E.S.T. standard row (2/2) but an Overall claiming 6/8 → the assignment
    # has non-B.E.S.T.-tagged items, so the emitted sum under-counts. Must WARN
    # (not fail) and still emit the good row.
    rows = [
        _row(**{"Standard Coding Number": "MA.7.AR.1.1", "Points Achieved": "2.00", "Points Possible": "2.00"}),
        _row(**{"Standard Coding Number": "Overall", "Standard Description": "",
                "Points Achieved": "6.00", "Points Possible": "8.00"}),
    ]
    with caplog.at_level(logging.WARNING, logger="ingest_schoology.parsers"):
        r = _parse(rows)
    assert len(r.submission_rows) == 1
    assert any("!= Overall" in rec.getMessage() for rec in caplog.records)


def test_overall_row_is_score_oracle():
    # Sum of the ingested B.E.S.T. rows for the (student, assignment) must equal
    # the skipped B.E.S.T. Overall row (2 + 0 = 2 of 4).
    r = _parse(_crosswalked())
    got = sum(s.points_received for s in r.submission_rows)
    possible = sum(s.points_possible for s in r.submission_rows)
    assert (got, possible) == (2.0, 4.0)


def test_description_with_comma_roundtrips():
    r = _parse([_row(**{"Standard Description": "Compare ratios a:b, unit rates, and percentages."})])
    assert "," in (r.submission_rows[0].question or "")
