"""Parse an HMH "Assessed Standards Results" export → GAINS raw rows.

Source: HMH Ed → School Data Export → "Assessed Standards Results" (File 02 in the
HMH platform review). One CSV row per (student × assignment × standard), plus an
"Overall" summary row per (student × assignment × standard-set). HMH cross-walks
every score to THREE frameworks (B.E.S.T. 2020, Florida 2014, Common Core 2010),
so each (student × assignment) appears three times over.

Grain we ingest: (student × assignment × B.E.S.T. standard). HMH exports never
carry the student's chosen answer option, the answer key, or a per-question
position, so this is a standard-grain feed (each GAINS "question" is one standard
within an assignment). That is a faithful representation of what HMH exports —
NOT a Schoology per-question feed. `answer_submission` / `correct_answer` are
therefore NULL for every HMH row; the distractor/IAD reports degrade to empty
states by design, while every score/standard/mastery report is fully populated.

Why this parser emits BOTH row families:
    * RawStudentSubmissionRow  — the per-(student, standard) score spine that
      builds the fact.
    * RawQuestionDataRow       — the standards carrier. The fact resolves each
      row's standard through `dim_question_data` (keyed on question_id), which is
      fed exclusively by `raw_question_data`. Without a matching QD row per
      (item, standard), every HMH fact row would resolve to a NULL standard and
      all standards reports would be empty.

Three parser-enforced row filters (see the sample-verified counts in the tests):
    1. Standard-Set filter: keep only rows whose "Standard Set" is the Florida
       B.E.S.T. set (its codes — MA.6.AR.1.1 — are the only ones that exact-match
       `dim_standard.schoology_standard`). Florida-2014 (MAFS.*) and Common-Core
       (CCSS.*) rows would triple-count and mis-resolve.
    2. Overall rows ("Standard Coding Number" == "Overall") are per-assignment
       summaries, not standards — skipped (they would double-count the score).
    3. Rows with a blank standard code or blank LASID are skipped and counted.

Frozen synthetic-id contract (changing any input reshapes subject_id/item_id and
mints a parallel history on the next ingest — treat as an interface):
    item_id      = "hmh-i-" + h(school_key, session, subject, grade,
                                assignment_name, class_name, teacher)
                   DateCompleted is deliberately EXCLUDED (it is the student's
                   completion date; including it would shatter one assignment
                   into per-student items). `grade` is included so an assignment
                   given in two grades can never trip validate_no_cross_band.
    section_nid  = "hmh-s-" + h(school_key, class_name, teacher)
    question_id  = "hmh-q-" + h(item_id, standard_code)   -- 1:1 with the standard
    position_number = "1" (constant). The standard-grain feed has no per-question
                   position; a constant keeps the latest-export-wins partition
                   stable per question_id across weekly re-exports (a per-set
                   ordinal would shift if HMH added a standard, splitting a
                   student's cell in two). Display order comes from question_no.
    submission   = 1 (HMH has no attempt counter).

Future enrichment (NOT built here): HMH File 06 (School Data Export → Usage:
Assignments) carries LASID + student email + assignment refids and could join
richer roster/section identity; File 01 (per-student per-item) could add true
per-question grain but is name-only (no LASID), so joining it is a fragile
name-match we deliberately avoid.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.jobs.parsers.common import (
    coerce_decimal,
    coerce_str,
    coerce_timestamp,
    read_csv_bytes,
    truncate_question,
)
from app.jobs.unique_key import question_data_unique_key, student_submission_unique_key
from app.models.raw_models import RawQuestionDataRow, RawStudentSubmissionRow


logger = logging.getLogger("ingest_schoology.parsers")


# ── Filters ────────────────────────────────────────────────────────────────
# The Florida B.E.S.T. Standard-Set name spells out "B.E.S.T." in full and is
# suffixed with the subject + year ("... - Mathematics - 2020"), so a prefix
# match keeps every subject's/year's B.E.S.T. set while excluding Florida-2014
# and Common-Core sets.
BEST_STANDARD_SET_PREFIX = "Florida Benchmarks for Excellent Student Thinking Standards"
_OVERALL_CODE = "overall"

# Required File-02 headers. Missing any → the file is malformed; raise loudly
# rather than silently emitting empty/degenerate rows.
_REQUIRED_HEADERS = frozenset({
    "Academic Year", "School Name", "StudentID LASID", "LastName", "FirstName",
    "Class Grade", "Class Name", "Teacher Last Name", "Teacher First Name",
    "Subject", "Component", "AssignmentName", "Date Completed", "Standard Set",
    "Standard Coding Number", "Standard Description", "Points Achieved",
    "Points Possible",
})

# The dated-export stamp the pipeline's latest-export-wins dedupe depends on
# (fact_student_submission.sql / dim_question_data.sql parse it out of file_name).
_EXPORT_STAMP_RE = re.compile(r"-\d{4}-\d{2}-\d{2}-\d{6}")
# Compiled once; used per row in the normalizers below.
_ACADEMIC_YEAR_RE = re.compile(r"(\d{4})-(\d{4})")
_INTERACTIVE_PREFIX_RE = re.compile(r"^Interactive\s+", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")

# ── Dimension normalizations → GAINS canonical slicer vocabulary ─────────────
_SUBJECT_MAP = {
    # Normalize HMH's discipline names to the GAINS subject vocabulary the
    # Schoology feed already uses (raw folder subject is "Mathematics"/"Science"/
    # "Social Studies"; the platform's ELA token is "ELA").
    "mathematics": "Mathematics",
    "math": "Mathematics",
    "english language arts": "ELA",
    "reading and language arts": "ELA",
    "reading": "ELA",
    "science and health": "Science",
    "science": "Science",
    "social studies": "Social Studies",
}
_ASSESSMENT_TYPE_MAP = {
    "interactive florida standards assessments": "Assessment",
    "interactive module": "Module",
    "interactive lesson": "Lesson",
}


@dataclass
class HmhSkipCounts:
    """Row-level rejections, surfaced so the operator can audit an ingest."""

    non_best_standard_set: int = 0
    overall_rows: int = 0
    blank_standard_code: int = 0
    blank_lasid: int = 0
    unparseable_points: int = 0
    # A row whose dimension fields can't produce a complete fact+dim_item:
    # malformed session/grade/date, or a blank Class Name / Assignment / Component
    # / teacher. Skipped + counted (never aborts the file) so one dirty row cannot
    # take down the whole weekly export or silently orphan an item from dim_item.
    malformed_dimension: int = 0

    def total(self) -> int:
        return (
            self.non_best_standard_set
            + self.overall_rows
            + self.blank_standard_code
            + self.blank_lasid
            + self.unparseable_points
            + self.malformed_dimension
        )


@dataclass
class HmhParseResult:
    submission_rows: list[RawStudentSubmissionRow] = field(default_factory=list)
    question_rows: list[RawQuestionDataRow] = field(default_factory=list)
    skipped: HmhSkipCounts = field(default_factory=HmhSkipCounts)


@dataclass(frozen=True, slots=True)
class _KeptRow:
    """One ingestable B.E.S.T. standard row — normalized once in pass 1, emitted in
    pass 2. A typed record (not a str-dict) so the float/datetime fields and the
    field names are checkable."""

    item_id: str
    code: str
    lasid: str
    last_name: str | None
    first_name: str | None
    school_name: str | None
    class_name: str
    teacher_first: str
    teacher_last: str
    component: str
    assignment_name: str
    subject: str
    grade: str
    session: str
    assessment_type: str
    completed: datetime
    description: str | None
    points_received: float
    points_possible: float


def _hash(*parts: str | None) -> str:
    """Stable 16-hex digest over trimmed, order-significant parts.

    Each part is LENGTH-PREFIXED (`<len>:<value>`) rather than delimiter-joined so
    the encoding is unambiguous: no free-text value (an assignment/class/teacher
    name that happens to contain the delimiter) can make two distinct field tuples
    collide onto the same item_id/section_nid.
    """
    payload = "".join(f"{len(s)}:{s}" for s in ((p or "").strip() for p in parts))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _stripped(row: dict[str, str], key: str) -> str:
    """Trimmed value at `key`, '' if missing. (Distinct from `coerce_str`, which
    does NOT trim and returns None for '' — this is for the strip-and-test fields.)"""
    return (row.get(key) or "").strip()


def _normalize_session(academic_year: str | None) -> str:
    """'2025-2026' → '2025-26'. Raises on a non-'NNNN-NNNN' consecutive-year value."""
    val = (academic_year or "").strip()
    m = _ACADEMIC_YEAR_RE.fullmatch(val)
    if not m:
        raise ValueError(f"HMH: unexpected Academic Year {academic_year!r}; expected NNNN-NNNN")
    start, end = int(m.group(1)), int(m.group(2))
    if end != start + 1:
        raise ValueError(f"HMH: Academic Year {academic_year!r} years are not consecutive")
    return f"{start}-{str(end)[-2:]}"


def _normalize_subject(subject: str | None) -> str:
    val = (subject or "").strip()
    mapped = _SUBJECT_MAP.get(val.lower())
    if mapped:
        return mapped
    logger.warning("HMH: unmapped Subject %r; passing through title-cased", subject)
    return val.title() if val else "Unknown"


def _normalize_grade(class_grade: str | None) -> str:
    """'7'/'07' → 'Grade 7'; 'K'/'KG'/'0'/'00' → 'Grade K'; 'PK' → 'Grade PK'.

    Raises ValueError on blank or an unmappable value (e.g. non-numeric junk); the
    caller catches it and skips+counts the row rather than minting a wrong grade
    slicer like 'Grade 0'.
    """
    val = (class_grade or "").strip().upper()
    if not val:
        raise ValueError("HMH: blank Class Grade")
    if val in ("K", "KG", "KINDERGARTEN", "0", "00"):
        return "Grade K"
    if val in ("PK", "PREK", "PRE-K", "PRE K"):
        return "Grade PK"
    digits = val.lstrip("0") or "0"
    if digits.isdigit() and 1 <= int(digits) <= 12:
        return f"Grade {int(digits)}"
    raise ValueError(f"HMH: unmappable Class Grade {class_grade!r}")


def _normalize_assessment_type(component: str | None) -> str:
    val = (component or "").strip()
    mapped = _ASSESSMENT_TYPE_MAP.get(val.lower())
    if mapped:
        return mapped
    # Fallback: drop the "Interactive " qualifier, collapse whitespace. Honest,
    # non-null, and keeps a distinct slicer value for unmapped HMH components.
    cleaned = _WHITESPACE_RE.sub(" ", _INTERACTIVE_PREFIX_RE.sub("", val)).strip()
    return cleaned or "Assessment"


def _warn_on_oracle_divergence(
    submission_rows: list[RawStudentSubmissionRow],
    overall_oracle: dict[tuple[str, str], tuple[float, float]],
    file_name: str,
) -> None:
    """Warn (don't fail) when a (student, assignment)'s emitted per-standard points
    don't sum to HMH's own B.E.S.T. "Overall" total — the assignment had items NOT
    tagged to a B.E.S.T. standard, so that student's score under-counts. A real HMH
    data condition worth surfacing rather than swallowing."""
    if not overall_oracle:
        return
    emitted: dict[tuple[str, str], list[float]] = {}
    for s in submission_rows:
        acc = emitted.setdefault((s.user_uid, s.item_name), [0.0, 0.0])
        acc[0] += s.points_received or 0.0
        acc[1] += s.points_possible or 0.0
    for (lasid, aname), (o_rec, o_pos) in overall_oracle.items():
        er, ep = emitted.get((lasid, aname), [0.0, 0.0])
        if abs(er - o_rec) > 0.01 or abs(ep - o_pos) > 0.01:
            logger.warning(
                "HMH %s: student …%s assignment %r — summed B.E.S.T. points "
                "%.2f/%.2f != Overall %.2f/%.2f (assignment likely has "
                "non-B.E.S.T.-tagged items; score under-counted)",
                file_name, lasid[-3:], aname, er, ep, o_rec, o_pos,
            )


def parse(
    *,
    csv_bytes: bytes,
    school_id: UUID,
    ingestion_run_id: UUID,
    source_file_path: str,
    source_file_hash: str,
    schoology_school_id: str,
    student_role_id: str,
    file_name: str,
) -> HmhParseResult:
    """Parse an HMH Assessed-Standards CSV into raw student-submission + question rows.

    Args:
        school_id: the HMH tenant's UUID (raw idempotency key only).
        schoology_school_id: the tenant's `schools.schoology_school_id` — stamped
            as every row's `user_school_id` so staging resolves the tenant.
        student_role_id: the tenant's `schools.student_role_id` — stamped as every
            row's `user_role_id` so the "students only" fact filter admits them.
        file_name: the source basename; MUST carry a `-YYYY-MM-DD-HHMMSS` stamp
            (the pipeline's latest-export-wins dedupe parses it out).
    """
    if not _EXPORT_STAMP_RE.search(file_name):
        raise ValueError(
            f"HMH file {file_name!r} lacks a -YYYY-MM-DD-HHMMSS export stamp; "
            "latest-export-wins dedupe requires it"
        )

    headers, rows = read_csv_bytes(csv_bytes, source_name=source_file_path)
    missing = _REQUIRED_HEADERS - set(headers)
    if missing:
        raise ValueError(f"HMH file {file_name!r} missing required headers: {sorted(missing)}")

    result = HmhParseResult()
    skip = result.skipped

    # Pass 1 — keep only ingestable B.E.S.T. standard rows; collect the per-item
    # standard set so question_no can be a meaningful per-assignment ordinal, and
    # retain HMH's own "Overall" rows as a score oracle (checked after pass 2).
    kept: list[_KeptRow] = []
    item_codes: dict[str, set[str]] = {}
    overall_oracle: dict[tuple[str, str], tuple[float, float]] = {}
    for row in rows:
        if not _stripped(row, "Standard Set").startswith(BEST_STANDARD_SET_PREFIX):
            skip.non_best_standard_set += 1
            continue
        code = _stripped(row, "Standard Coding Number")
        if code.lower() == _OVERALL_CODE:
            skip.overall_rows += 1
            o_lasid = _stripped(row, "StudentID LASID")
            o_name = coerce_str(row.get("AssignmentName"))
            o_rec = coerce_decimal(row.get("Points Achieved"))
            o_pos = coerce_decimal(row.get("Points Possible"))
            if o_lasid and o_name and o_rec is not None and o_pos is not None:
                overall_oracle[(o_lasid, o_name)] = (o_rec, o_pos)
            continue
        if not code:
            skip.blank_standard_code += 1
            continue
        lasid = _stripped(row, "StudentID LASID")
        if not lasid:
            skip.blank_lasid += 1
            continue
        points_received = coerce_decimal(row.get("Points Achieved"))
        points_possible = coerce_decimal(row.get("Points Possible"))
        if points_received is None or points_possible is None:
            skip.unparseable_points += 1
            continue

        # Normalize + validate every dimension field a COMPLETE fact+dim row
        # needs: the dim_item 7-col NOT-NULL gate (item_type=Component,
        # section_name=Class Name, section_instructors=teacher, item_name=
        # Assignment, assessment date) AND a normalizable session + grade — both
        # of which feed subject_id via uuid_6 (which tolerates NULLs, so an
        # unnormalizable grade/year would otherwise land the score under a
        # degenerate subject). A malformed/blank value skips THIS row (counted)
        # rather than aborting the export or emitting a fact-spine row whose item
        # drops from dim_item. File-level problems (missing headers / export
        # stamp) still fail loud above — those mean a wrong/corrupt file.
        class_name = coerce_str(row.get("Class Name"))
        assignment_name = coerce_str(row.get("AssignmentName"))
        component = coerce_str(row.get("Component"))
        teacher_last = _stripped(row, "Teacher Last Name")
        teacher_first = _stripped(row, "Teacher First Name")
        try:
            session = _normalize_session(row.get("Academic Year"))
            grade = _normalize_grade(row.get("Class Grade"))
            completed = coerce_timestamp(row.get("Date Completed"))
        except ValueError:
            skip.malformed_dimension += 1
            continue
        if not (class_name and assignment_name and component and completed
                and (teacher_first or teacher_last)):
            skip.malformed_dimension += 1
            continue
        subject = _normalize_subject(row.get("Subject"))

        item_id = "hmh-i-" + _hash(
            schoology_school_id, session, subject, grade,
            assignment_name, class_name, teacher_last, teacher_first,
        )
        kept.append(_KeptRow(
            item_id=item_id,
            code=code,
            lasid=lasid,
            last_name=coerce_str(row.get("LastName")),
            first_name=coerce_str(row.get("FirstName")),
            school_name=coerce_str(row.get("School Name")),
            class_name=class_name,
            teacher_first=teacher_first,
            teacher_last=teacher_last,
            component=component,
            assignment_name=assignment_name,
            subject=subject,
            grade=grade,
            session=session,
            assessment_type=_normalize_assessment_type(component),
            completed=completed,
            description=truncate_question(coerce_str(row.get("Standard Description"))),
            points_received=points_received,
            points_possible=points_possible,
        ))
        item_codes.setdefault(item_id, set()).add(code)

    # Per-item, per-standard display ordinal (question_no). A display attribute on
    # dim_question_data (latest-export-wins), so a re-export reshuffle is harmless.
    item_code_rank: dict[str, dict[str, int]] = {
        item_id: {code: i + 1 for i, code in enumerate(sorted(codes))}
        for item_id, codes in item_codes.items()
    }

    # Pass 2 — emit the score spine + one QD row per distinct (item, standard).
    # position_number is a constant: the standard-grain feed has no per-question
    # slot, and keeping it fixed makes the latest-export-wins dedupe stable across
    # weekly re-exports (question_id already distinguishes the standards).
    seen_qid: set[str] = set()
    position_number = "1"
    for p in kept:
        question_id = "hmh-q-" + _hash(p.item_id, p.code)
        section_nid = "hmh-s-" + _hash(
            schoology_school_id, p.class_name, p.teacher_last, p.teacher_first
        )
        section_instructors = f"{p.teacher_first} {p.teacher_last}".strip() or None
        question_no = str(item_code_rank[p.item_id][p.code])

        result.submission_rows.append(
            RawStudentSubmissionRow(
                school_id=school_id,
                ingestion_run_id=ingestion_run_id,
                source_file_path=source_file_path,
                source_file_hash=source_file_hash,
                unique_key=student_submission_unique_key(
                    user_uid=p.lasid,
                    item_id=p.item_id,
                    question_id=question_id,
                    position_number=position_number,
                    answer_submission=None,
                    points_received=p.points_received,
                    points_possible=p.points_possible,
                    submission=1,
                    correct_answer=None,
                ),
                user_uid=p.lasid,
                username=p.lasid,
                last_name=p.last_name,
                first_name=p.first_name,
                user_role_id=student_role_id,
                user_school_id=schoology_school_id,
                user_school_name=p.school_name,
                section_nid=section_nid,
                section_name=p.class_name,
                section_instructors=section_instructors,
                item_type=p.component,
                item_id=p.item_id,
                item_name=p.assignment_name,
                first_access=p.completed,
                latest_attempt=p.completed,
                submission=1,
                question_id=question_id,
                question=p.description,
                position_number=position_number,
                answer_submission=None,
                correct_answer=None,
                points_received=p.points_received,
                points_possible=p.points_possible,
                session=p.session,
                assessment_type=p.assessment_type,
                subject=p.subject,
                grade=p.grade,
                section=p.class_name,
                file_name=file_name,
            )
        )

        if question_id in seen_qid:
            continue
        seen_qid.add(question_id)
        result.question_rows.append(
            RawQuestionDataRow(
                school_id=school_id,
                ingestion_run_id=ingestion_run_id,
                source_file_path=source_file_path,
                source_file_hash=source_file_hash,
                unique_key=question_data_unique_key(
                    item_id=p.item_id,
                    question_id=question_id,
                    correct_answer=None,
                    position_number=position_number,
                    answer_option=None,
                    answer_breakdown_count=None,
                    standards_val=p.code,
                ),
                item_id=p.item_id,
                item_name=p.assignment_name,
                question_id=question_id,
                total_points=p.points_possible,
                question=p.description,
                position_number=position_number,
                standards_val=p.code,
                session=p.session,
                assessment_type=p.assessment_type,
                subject=p.subject,
                grade=p.grade,
                section=p.class_name,
                file_name=file_name,
                question_no=question_no,
            )
        )

    _warn_on_oracle_divergence(result.submission_rows, overall_oracle, file_name)

    logger.info(
        "HMH parse %s: %d submission rows, %d question rows, skipped %s",
        file_name, len(result.submission_rows), len(result.question_rows), skip,
    )
    return result
