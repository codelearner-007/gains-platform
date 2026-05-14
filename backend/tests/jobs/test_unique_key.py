"""Tests for the three Unique_Key formulas."""

from __future__ import annotations

from app.jobs.unique_key import (
    question_data_unique_key,
    student_submission_unique_key,
    submission_summary_unique_key,
)


class TestQuestionDataUniqueKey:
    def test_all_present(self) -> None:
        # notebook line 558: Item_ID + Question_ID + Correct_Answer + Position_Number
        # + Answer_Option + Answer_Breakdown + Standards
        uk = question_data_unique_key(
            item_id="ITEM",
            question_id="QID",
            correct_answer="CA",
            position_number="1",
            answer_option="a",
            answer_breakdown_count=5,
            standards_val="MA.5.X",
        )
        assert uk == "ITEMQIDCA1a5MA.5.X"

    def test_empty_standards_ok(self) -> None:
        uk = question_data_unique_key(
            item_id="ITEM",
            question_id="QID",
            correct_answer="CA",
            position_number="1",
            answer_option="a",
            answer_breakdown_count=5,
            standards_val=None,
        )
        assert uk == "ITEMQIDCA1a5"

    def test_all_none(self) -> None:
        # All NULLs -> empty string. (Never occurs in real data but contract is well-defined.)
        uk = question_data_unique_key(None, None, None, None, None, None, None)
        assert uk == ""


class TestSubmissionSummaryUniqueKey:
    def test_canonical(self) -> None:
        # notebook line 587: Schoology_ID + Question
        uk = submission_summary_unique_key(
            schoology_id="98354149", question_label="Question 3"
        )
        assert uk == "98354149Question 3"

    def test_none_inputs(self) -> None:
        uk = submission_summary_unique_key(schoology_id=None, question_label="Question 1")
        assert uk == "Question 1"


class TestStudentSubmissionUniqueKey:
    def test_canonical(self) -> None:
        # notebook line 593: User_UID + Item_ID + Question_ID + Position_Number
        # + Answer_Submission + Points_Received + Points_Possible + Submission + Correct_Answer
        uk = student_submission_unique_key(
            user_uid="85649679",
            item_id="8368732914",
            question_id="2271509018",
            position_number="1",
            answer_submission="42",
            points_received=0.0,
            points_possible=1.0,
            submission=1,
            correct_answer="384",
        )
        # Floats stringify with their default repr ("0.0", "1.0")
        assert uk == "85649679836873291422715090181420.01.01384"

    def test_with_nones(self) -> None:
        uk = student_submission_unique_key(
            user_uid="UID",
            item_id="IID",
            question_id="QID",
            position_number=None,
            answer_submission=None,
            points_received=None,
            points_possible=None,
            submission=None,
            correct_answer="CA",
        )
        assert uk == "UIDIIDQIDCA"

    def test_int_submission(self) -> None:
        # submission is INTEGER; ensure str repr is bare int (no '.0')
        uk = student_submission_unique_key(
            user_uid="U", item_id="I", question_id="Q",
            position_number="1", answer_submission="A",
            points_received=None, points_possible=None,
            submission=2, correct_answer="C",
        )
        assert "2" in uk
        assert "2.0" not in uk
