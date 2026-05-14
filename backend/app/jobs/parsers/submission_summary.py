"""Parse Submission-Summary-*.csv → list[RawSubmissionSummaryRow].

Notebook lines 489-587 / spec §3 line 168.

CSV shape (verified across all 35 Athenian files — only fixed-column header found):

    Schoology ID,First Name,Last Name,Unique ID,Job Title,Gradebook Grade,
    Submission #,Submission Score,Question 1,Question 2,...,Question N

Each row is one student's submission. The N "Question X" columns hold the
per-question score (0/1 for binary, fractional for partial-credit).

Wide → long melt: emit one output row per (student × Question N column).

Unique_Key formula (notebook line 587): Schoology_ID + Question_label
"""

from __future__ import annotations

from uuid import UUID

from app.jobs.parsers.common import (
    coerce_decimal,
    coerce_int,
    coerce_str,
    read_csv_bytes,
)
from app.jobs.unique_key import submission_summary_unique_key
from app.models.raw_models import RawSubmissionSummaryRow


def parse(
    *,
    csv_bytes: bytes,
    school_id: UUID,
    ingestion_run_id: UUID,
    source_file_path: str,
    source_file_hash: str,
) -> list[RawSubmissionSummaryRow]:
    """Parse a Submission-Summary CSV.

    Args:
        csv_bytes: raw bytes of the CSV (utf-8 with BOM accepted).
        school_id: tenant identifier; copied to every row.
        ingestion_run_id: the running job's run_id; copied to every row.
        source_file_path: relative blob path used for traceability/dedup.
        source_file_hash: SHA-256 hex digest of csv_bytes.

    Returns:
        list of validated RawSubmissionSummaryRow objects, ready to INSERT.
    """
    headers, rows = read_csv_bytes(csv_bytes, source_name=source_file_path)

    # Identify the wide "Question N" columns to melt.
    question_cols = [h for h in headers if h.startswith("Question ")]

    out: list[RawSubmissionSummaryRow] = []
    for row in rows:
        # Capture fixed columns
        fixed: dict[str, str | int | float | None] = {}
        fixed["schoology_id"] = coerce_str(row.get("Schoology ID"))
        fixed["first_name"] = coerce_str(row.get("First Name"))
        fixed["last_name"] = coerce_str(row.get("Last Name"))
        fixed["unique_id_csv"] = coerce_str(row.get("Unique ID"))
        fixed["job_title"] = coerce_str(row.get("Job Title"))
        fixed["gradebook_grade"] = coerce_str(row.get("Gradebook Grade"))
        fixed["submission_no"] = coerce_int(row.get("Submission #"))
        fixed["submission_score"] = coerce_decimal(row.get("Submission Score"))

        # Melt the Question-N columns
        for q_label in question_cols:
            q_score_raw = row.get(q_label, "")
            q_score = coerce_decimal(q_score_raw)

            uk = submission_summary_unique_key(
                schoology_id=fixed["schoology_id"],
                question_label=q_label,
            )

            out.append(
                RawSubmissionSummaryRow(
                    school_id=school_id,
                    ingestion_run_id=ingestion_run_id,
                    source_file_path=source_file_path,
                    source_file_hash=source_file_hash,
                    unique_key=uk,
                    schoology_id=fixed["schoology_id"],
                    first_name=fixed["first_name"],
                    last_name=fixed["last_name"],
                    unique_id_csv=fixed["unique_id_csv"],
                    job_title=fixed["job_title"],
                    gradebook_grade=fixed["gradebook_grade"],
                    submission_no=fixed["submission_no"],
                    submission_score=fixed["submission_score"],
                    question_label=q_label,
                    question_score=q_score,
                )
            )

    return out
