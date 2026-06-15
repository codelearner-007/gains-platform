"""Assessment listing and drill-down service."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.repositories.cube_repository import CubeRepository
from app.repositories.dim_repository import DimRepository
from app.schemas.assessments import (
    AssessmentDetail,
    AssessmentListRow,
    AssessmentSummary,
    AssessmentSummaryListRow,
    AssessmentSummaryPage,
)
from app.schemas.reports import (
    IncorrectChoice,
    QuestionOverall,
    StandardSummaryRow,
)
from app.utils.coercion import safe_str, to_float, to_int


class AssessmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.dim = DimRepository(session)
        self.cube = CubeRepository(session)

    async def list_assessments(
        self,
        session_filter: Optional[str] = None,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[AssessmentListRow]:
        rows = await self.dim.list_items(
            session_filter=session_filter,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
        )
        return [AssessmentListRow.model_validate(r) for r in rows]

    # Whitelist: sort key -> SQL expression. Interpolated (not bound), so the
    # value MUST come from this dict, never from raw user input.
    _SORT_SQL = {
        "date": "assessment_date",
        "item": "lower(item_name)",
        "grade": "grade",
        "students": "total_students",
        "average": "grade_average",
    }

    async def list_assessment_summaries(
        self,
        session_filter: Optional[str] = None,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        section: Optional[str] = None,
        q: Optional[str] = None,
        sort: str = "date",
        direction: str = "desc",
        limit: int = 25,
        offset: int = 0,
    ) -> AssessmentSummaryPage:
        """One server-paginated page of the dashboard By-Assessment grid (rows
        with grade_average + total_students) plus the full scoped total. Server
        sort + name search so a school with thousands of assessments only
        transfers one page per request."""
        sort_sql = self._SORT_SQL.get(sort, "assessment_date")
        dir_sql = "ASC" if direction.lower() == "asc" else "DESC"
        rows_raw, total = await self.cube.get_assessment_summary_page(
            session_filter=session_filter,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
            q=q,
            sort_sql=sort_sql,
            dir_sql=dir_sql,
            limit=limit,
            offset=offset,
        )
        rows = [
            AssessmentSummaryListRow.model_validate(
                {
                    **r,
                    "grade_average": to_float(r.get("grade_average"))
                    if r.get("grade_average") is not None
                    else None,
                    "total_students": to_int(r.get("total_students"))
                    if r.get("total_students") is not None
                    else None,
                }
            )
            for r in rows_raw
        ]
        return AssessmentSummaryPage(
            rows=rows, total=total, limit=limit, offset=offset
        )

    async def get_assessment(self, item_id: str) -> AssessmentDetail:
        row = await self.dim.get_item(item_id)
        if not row:
            raise ResourceNotFoundError("Assessment", item_id)
        return AssessmentDetail.model_validate(row)

    async def get_summary(self, item_id: str) -> AssessmentSummary:
        school = await self.cube.get_school_summary_for_item(item_id)
        grade = await self.cube.get_grade_summary_for_item(item_id)
        if not school:
            raise ResourceNotFoundError("AssessmentSummary", item_id)
        return AssessmentSummary(
            item_id=safe_str(school.get("item_id")) or item_id,
            total_questions=to_int(school.get("total_questions")),
            total_standards=to_int(school.get("total_standards")),
            total_students=to_int(school.get("total_students")),
            total_possible_point=to_float(school.get("total_possible_point")),
            total_score=to_float(school.get("total_score")),
            grade_average=to_float(school.get("grade_average")),
            percentage_incorrect_answers=to_float(
                school.get("percentage_incorrect_answers")
            ),
            grade_min=to_float((grade or {}).get("grade_min")) if grade else None,
            grade_max=to_float((grade or {}).get("grade_max")) if grade else None,
        )

    async def get_questions(self, item_id: str) -> List[QuestionOverall]:
        rows = await self.cube.get_questions_overall_for_item(item_id)
        if not rows:
            return []
        return [
            QuestionOverall(
                question_id=safe_str(q.get("question_id")),
                question_no=safe_str(q.get("question_no")),
                position_number=safe_str(q.get("position_number")) or "n/a",
                question=safe_str(q.get("question")),
                question_type=safe_str(q.get("question_type")),
                correct_answer=safe_str(q.get("correct_answer")),
                total_possible_point=to_float(q.get("total_possible_point")),
                total_score=to_float(q.get("total_score")),
                grade_average=to_float(q.get("grade_average")),
                percentage_incorrect=to_float(q.get("percentage_incorrect")),
                incorrect_choice_details=safe_str(q.get("incorrect_choice_details")),
                incorrect_details_name=safe_str(q.get("incorrect_details_name")),
                standards=safe_str(q.get("standards")),
                standard_raw=safe_str(q.get("strand_raw")),
                description=safe_str(q.get("description")),
            )
            for q in rows
        ]

    async def get_standards(self, item_id: str) -> List[StandardSummaryRow]:
        rows = await self.cube.get_standards_for_item(item_id)
        return [
            StandardSummaryRow(
                item_id=row.get("item_id"),
                strand_id=row.get("strand_id"),
                identifier=row.get("identifier"),
                strand=row.get("strand"),
                schoology_standard=row.get("schoology_standard"),
                description=row.get("description"),
                total_questions=to_int(row.get("total_questions")),
                total_standards=to_int(row.get("total_standards")),
                total_possible_point=to_float(row.get("total_possible_point")),
                total_score=to_float(row.get("total_score")),
                grade_average=to_float(row.get("grade_average")),
                percentage_incorrect_answers=to_float(
                    row.get("percentage_incorrect_answers")
                ),
            )
            for row in rows
        ]

    async def get_incorrect_choices(self, item_id: str) -> List[IncorrectChoice]:
        rows = await self.cube.get_incorrect_choices_for_item(item_id)
        return [
            IncorrectChoice(
                question_id=safe_str(r.get("question_id")),
                answer_submission=safe_str(r.get("answer_submission")),
                is_correct=bool(r.get("is_correct")),
                students_count=to_int(r.get("students_count")),
                attempt_count_for_choice=to_int(r.get("attempt_count_for_choice")),
                total_attempts_for_question=to_int(
                    r.get("total_attempts_for_question")
                ),
                share_of_attempts=to_float(r.get("share_of_attempts")),
                total_score=to_float(r.get("total_score")),
                total_possible_point=to_float(r.get("total_possible_point")),
                grade_average=to_float(r.get("grade_average")),
                students=[],
            )
            for r in rows
        ]
