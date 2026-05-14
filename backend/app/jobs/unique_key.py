"""Per-CSV-type Unique_Key formulas.

Direct port of notebook lines 558, 587, 593 (40_schoology_py_spec.md §3 line 167-169).

These keys are used in `raw_*.unique_key` and feed the
UNIQUE (school_id, source_file_hash, unique_key) constraint for dedup.

Conversion rules:
    - All key parts are stringified (None -> empty string) and concatenated WITHOUT a separator.
      This matches the original Spark `concat(col1, col2, ...)` semantics where NULLs propagate
      to NULL string in concatenation, but in PySpark with string Type the empty string is
      typically emitted. We replicate empty-string semantics for missing values.
    - Numeric inputs (counts, percentages, scores) are converted via `str(...)` of their
      Python representation, matching pandas' default rendering.
"""

from __future__ import annotations


def _s(v: object) -> str:
    """Stringify a key part. None and missing values become the empty string."""
    if v is None:
        return ""
    return str(v)


def question_data_unique_key(
    item_id: str | None,
    question_id: str | None,
    correct_answer: str | None,
    position_number: str | None,
    answer_option: str | None,
    answer_breakdown_count: int | str | None,
    standards_val: str | None,
) -> str:
    """Notebook line 558 — for raw_question_data after Standards/Answer_Breakdown melt.

    `Unique_Key = Item_ID + Question_ID + Correct_Answer + Position_Number
                + Answer_Option + Answer_Breakdown + Standards`
    """
    return (
        _s(item_id)
        + _s(question_id)
        + _s(correct_answer)
        + _s(position_number)
        + _s(answer_option)
        + _s(answer_breakdown_count)
        + _s(standards_val)
    )


def submission_summary_unique_key(schoology_id: str | None, question_label: str | None) -> str:
    """Notebook line 587 — for raw_submission_summary after Question-N melt.

    `Unique_Key = Schoology_ID + Question`
    where `Question` here is the column LABEL (e.g. "Question 1"), not the question text.
    """
    return _s(schoology_id) + _s(question_label)


def student_submission_unique_key(
    user_uid: str | None,
    item_id: str | None,
    question_id: str | None,
    position_number: str | None,
    answer_submission: str | None,
    points_received: float | str | None,
    points_possible: float | str | None,
    submission: int | str | None,
    correct_answer: str | None,
) -> str:
    """Notebook line 593 — for raw_student_submission (no melt).

    `Unique_Key = User_UID + Item_ID + Question_ID + Position_Number
                + Answer_Submission + Points_Received + Points_Possible
                + Submission + Correct_Answer`
    """
    return (
        _s(user_uid)
        + _s(item_id)
        + _s(question_id)
        + _s(position_number)
        + _s(answer_submission)
        + _s(points_received)
        + _s(points_possible)
        + _s(submission)
        + _s(correct_answer)
    )
