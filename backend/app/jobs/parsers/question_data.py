"""Parse Question-Data-*.csv → list[RawQuestionDataRow].

Notebook lines 489-598 / spec §3 line 167. The most complex of the three parsers.

CSV shape — variable widths observed across the 35 Athenian files:

    Item ID, Item Name, Question ID, Associated Question ID, Total Points, Question Type,
    Question, Position Number, Sub-Question, Answer Option,
    Answer Breakdown, Answer Breakdown,           # COUNT then PCT (same column name twice!)
    Correct Answer, Correctly Answered, Most Points Earned, Least Points Earned,
    Average Points Earned,
    Standards, Standards, Standards, Standards    # 0-4 occurrences

The duplicate "Answer Breakdown" header is disambiguated to ('Answer Breakdown', 'Answer Breakdown__1').
The duplicate "Standards" headers become ('Standards', 'Standards__1', 'Standards__2', ...).

Wide → long melts:

* Each input row already represents one (question × answer-option) row, with a single
  (count, pct) PAIR for that option — these come through as-is to (answer_breakdown_count,
  answer_breakdown_pct).

* The N Standards columns (N in {0,1,2,4}) ARE multi-melted: emit ONE output row per
  non-empty Standards_Val. If N == 0 (or all Standards cells are empty), emit ONE output
  row with standards_val=None (we still need the row in raw_question_data).

* `question_no` is computed AFTER all rows are emitted: a DENSE RANK over Question_ID
  ordered LEXICOGRAPHICALLY by Question_ID. This matches notebook lines 566-567:
      df_final = df_final.sort_values(by="Question_ID").reset_index(drop=True)
      df_final['Question_No'] = rankdata(df_final['Question_ID'], method='dense')
  Effect: for the set of distinct Question_IDs in the file, sort ascending and
  assign 1..N. Rows with the same Question_ID share the same rank.

Unique_Key formula (notebook line 558):
    Item_ID + Question_ID + Correct_Answer + Position_Number + Answer_Option
    + Answer_Breakdown_Count + Standards_Val
"""

from __future__ import annotations

from uuid import UUID

from app.jobs.file_path_parser import ParsedPath
from app.jobs.parsers.common import (
    coerce_decimal,
    coerce_int,
    coerce_str,
    read_csv_bytes,
    truncate_question,
)
from app.jobs.unique_key import question_data_unique_key
from app.models.raw_models import RawQuestionDataRow


# Note on Answer Breakdown:
#   Header row example: Answer Breakdown, Answer Breakdown
#   After disambiguation:   "Answer Breakdown" (the COUNT) and "Answer Breakdown__1" (the PCT)
# This convention matches the pilot script (data/_pilot/_build_pilot.py).
_AB_COUNT = "Answer Breakdown"
_AB_PCT = "Answer Breakdown__1"


def parse(
    *,
    csv_bytes: bytes,
    school_id: UUID,
    ingestion_run_id: UUID,
    source_file_path: str,
    source_file_hash: str,
    parsed_path: ParsedPath,
) -> list[RawQuestionDataRow]:
    """Parse a Question-Data CSV; perform Standards melt + question_no dense rank."""
    headers, rows = read_csv_bytes(csv_bytes, source_name=source_file_path)

    # Find Standards columns. After disambiguation they become Standards, Standards__1, ...
    standards_cols = [h for h in headers if h == "Standards" or h.startswith("Standards__")]

    # Pass 1: emit raw rows (without question_no), collecting the set of distinct Question_IDs.
    out: list[RawQuestionDataRow] = []
    qid_set: set[str] = set()

    def _record_qid(qid: str | None) -> None:
        if qid:
            qid_set.add(qid)

    for row in rows:
        item_id = coerce_str(row.get("Item ID"))
        item_name = coerce_str(row.get("Item Name"))
        question_id = coerce_str(row.get("Question ID"))
        associated_qid = coerce_str(row.get("Associated Question ID"))
        total_points = coerce_decimal(row.get("Total Points"))
        question_type = coerce_str(row.get("Question Type"))
        question_text = truncate_question(coerce_str(row.get("Question")))
        position_number = coerce_str(row.get("Position Number"))
        sub_question = coerce_str(row.get("Sub-Question"))
        answer_option = coerce_str(row.get("Answer Option"))
        ab_count = coerce_int(row.get(_AB_COUNT))
        ab_pct = coerce_decimal(row.get(_AB_PCT))
        correct_answer = coerce_str(row.get("Correct Answer"))
        correctly_answered = coerce_decimal(row.get("Correctly Answered"))
        most_pts = coerce_decimal(row.get("Most Points Earned"))
        least_pts = coerce_decimal(row.get("Least Points Earned"))
        avg_pts = coerce_decimal(row.get("Average Points Earned"))

        _record_qid(question_id)

        # Collect non-empty Standards values; if none, emit one row with standards_val=None.
        std_vals = [coerce_str(row.get(c)) for c in standards_cols]
        std_vals = [v for v in std_vals if v is not None]
        if not std_vals:
            std_vals = [None]  # type: ignore[list-item]

        for sv in std_vals:
            uk = question_data_unique_key(
                item_id=item_id,
                question_id=question_id,
                correct_answer=correct_answer,
                position_number=position_number,
                answer_option=answer_option,
                answer_breakdown_count=ab_count,
                standards_val=sv,
            )

            out.append(
                RawQuestionDataRow(
                    school_id=school_id,
                    ingestion_run_id=ingestion_run_id,
                    source_file_path=source_file_path,
                    source_file_hash=source_file_hash,
                    unique_key=uk,
                    item_id=item_id,
                    item_name=item_name,
                    question_id=question_id,
                    associated_question_id=associated_qid,
                    total_points=total_points,
                    question_type=question_type,
                    question=question_text,
                    position_number=position_number,
                    sub_question=sub_question,
                    answer_option=answer_option,
                    answer_breakdown_count=ab_count,
                    answer_breakdown_pct=ab_pct,
                    correct_answer=correct_answer,
                    correctly_answered=correctly_answered,
                    most_points_earned=most_pts,
                    least_points_earned=least_pts,
                    average_points_earned=avg_pts,
                    standards_val=sv,
                    session=parsed_path.session,
                    assessment_type=parsed_path.assessment_type,
                    subject=parsed_path.subject,
                    grade=parsed_path.grade,
                    section=parsed_path.section,
                    file_name=parsed_path.file_name,
                    question_no=None,  # filled in pass 2
                )
            )

    # Pass 2: stamp question_no via dense rank on LEXICOGRAPHIC Question_ID order.
    # Notebook lines 566-567:
    #     df_final = df_final.sort_values(by="Question_ID").reset_index(drop=True)
    #     df_final['Question_No'] = rankdata(df_final['Question_ID'], method='dense')
    # We sort distinct Question_IDs lexicographically and 1-index them. This is
    # deterministic across runs and independent of CSV row order.
    # Returned as TEXT to match the schema (raw_question_data.question_no TEXT).
    qid_to_rank = {qid: idx + 1 for idx, qid in enumerate(sorted(qid_set))}
    for r in out:
        if r.question_id is not None and r.question_id in qid_to_rank:
            r.question_no = str(qid_to_rank[r.question_id])

    # Within-file dedup: identical Unique_Keys collide on the
    # (school_id, source_file_hash, unique_key) UNIQUE constraint. This can
    # happen if a question has e.g. duplicate non-empty Standards entries.
    # Collapse to first occurrence per unique_key — preserves all useful data
    # because every duplicated key has identical fields by construction.
    seen: set[str] = set()
    deduped: list[RawQuestionDataRow] = []
    for r in out:
        if r.unique_key in seen:
            continue
        seen.add(r.unique_key)
        deduped.append(r)

    return deduped
