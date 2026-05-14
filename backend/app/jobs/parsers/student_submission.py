"""Parse Student-Submissions-*.csv → list[RawStudentSubmissionRow].

Notebook line 593 / spec §3 line 169.

Each CSV row is ALREADY in long format (one row per student × question), so we
do NOT melt. We coerce types, truncate Question/Answer_Submission to 7500 chars
(notebook lines 482-488), compute Unique_Key per row, and emit.

The path-derived columns (session, assessment_type, subject, grade, section, file_name)
are INJECTED here from the caller — they are not in the CSV body.
"""

from __future__ import annotations

from uuid import UUID

from app.jobs.file_path_parser import ParsedPath
from app.jobs.parsers.common import (
    coerce_decimal,
    coerce_int,
    coerce_interval,
    coerce_str,
    coerce_timestamp,
    read_csv_bytes,
    truncate_question,
)
from app.jobs.unique_key import student_submission_unique_key
from app.models.raw_models import RawStudentSubmissionRow


def parse(
    *,
    csv_bytes: bytes,
    school_id: UUID,
    ingestion_run_id: UUID,
    source_file_path: str,
    source_file_hash: str,
    parsed_path: ParsedPath,
) -> list[RawStudentSubmissionRow]:
    """Parse a Student-Submissions CSV.

    No melt. One output row per input row (excluding any blank rows).
    """
    _, rows = read_csv_bytes(csv_bytes, source_name=source_file_path)

    out: list[RawStudentSubmissionRow] = []
    for row in rows:
        user_uid = coerce_str(row.get("User UID"))
        item_id = coerce_str(row.get("Item ID"))
        question_id = coerce_str(row.get("Question ID"))
        position_number = coerce_str(row.get("Position Number"))
        answer_submission = truncate_question(coerce_str(row.get("Answer Submission")))
        correct_answer = coerce_str(row.get("Correct Answer"))
        points_received = coerce_decimal(row.get("Points Received"))
        points_possible = coerce_decimal(row.get("Points Possible"))
        submission = coerce_int(row.get("Submission"))
        question_text = truncate_question(coerce_str(row.get("Question")))

        uk = student_submission_unique_key(
            user_uid=user_uid,
            item_id=item_id,
            question_id=question_id,
            position_number=position_number,
            answer_submission=answer_submission,
            points_received=points_received,
            points_possible=points_possible,
            submission=submission,
            correct_answer=correct_answer,
        )

        out.append(
            RawStudentSubmissionRow(
                school_id=school_id,
                ingestion_run_id=ingestion_run_id,
                source_file_path=source_file_path,
                source_file_hash=source_file_hash,
                unique_key=uk,
                user_uid=user_uid,
                username=coerce_str(row.get("Username")),
                last_name=coerce_str(row.get("Last Name")),
                first_name=coerce_str(row.get("First Name")),
                user_role_id=coerce_str(row.get("User Role ID")),
                user_school_id=coerce_str(row.get("User School ID")),
                user_school_name=coerce_str(row.get("User School Name")),
                course_nid=coerce_str(row.get("Course NID")),
                course_name=coerce_str(row.get("Course Name")),
                course_code=coerce_str(row.get("Course code")),
                section_nid=coerce_str(row.get("Section NID")),
                section_name=coerce_str(row.get("Section Name")),
                section_code=coerce_str(row.get("Section Code")),
                section_instructors=coerce_str(row.get("Section Instructors")),
                item_type=coerce_str(row.get("Item Type")),
                item_id=item_id,
                item_name=coerce_str(row.get("Item Name")),
                first_access=coerce_timestamp(row.get("First Access")),
                latest_attempt=coerce_timestamp(row.get("Latest Attempt")),
                total_time=coerce_interval(row.get("Total Time")),
                submission_grade=coerce_decimal(row.get("Submission Grade")),
                submission=submission,
                question_id=question_id,
                associated_question_id=coerce_str(row.get("Associated Question ID")),
                question_type=coerce_str(row.get("Question Type")),
                question=question_text,
                position_number=position_number,
                sub_question=coerce_str(row.get("Sub-Question")),
                answer_submission=answer_submission,
                correct_answer=correct_answer,
                points_received=points_received,
                points_possible=points_possible,
                session=parsed_path.session,
                assessment_type=parsed_path.assessment_type,
                subject=parsed_path.subject,
                grade=parsed_path.grade,
                section=parsed_path.section,
                file_name=parsed_path.file_name,
            )
        )

    return out
