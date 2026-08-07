"""Per-student reporting service.

Composes the browse roster and the full multi-subject report from
:class:`StudentRepository` (all numbers grain-B; see that module) and reuses
:meth:`CubeRepository.get_school_wide_meta` for the report header. Band strings
are computed here so the frontend never re-implements the 70/80 thresholds.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PERF_BAND_HIGH_PCT, PERF_BAND_MID_PCT
from app.core.exceptions import ResourceNotFoundError
from app.repositories.cube_repository import CubeRepository
from app.repositories.student_repository import StudentRepository
from app.schemas.students import (
    MasteryDist,
    PerStudentReportPayload,
    ReportSchoolInfo,
    StudentAssessmentRow,
    StudentBrowsePage,
    StudentBrowseRow,
    StudentIdentity,
    StudentOverall,
    StudentStandardRow,
    StudentStrandRow,
    StudentSubjectReport,
    StudentSubjectStat,
)
from app.services.reports import _strip_html
from app.utils.coercion import safe_str, to_int

# Default roster page size — mirrors the dashboard's By-Assessment grid.
DEFAULT_BROWSE_PAGE_SIZE = 25

_BAND_HIGH = PERF_BAND_HIGH_PCT
_BAND_MID = PERF_BAND_MID_PCT


def _f(v: Any) -> Optional[float]:
    """Coerce a numeric (Decimal/str) to float, preserving ``None``."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _band(pct: Optional[float]) -> str:
    if pct is None:
        return "na"
    if pct >= _BAND_HIGH:
        return "green"
    if pct >= _BAND_MID:
        return "yellow"
    return "pink"


def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, str):
        try:
            return json.loads(v) or []
        except json.JSONDecodeError:
            return []
    return list(v)


def _as_obj(v: Any) -> dict:
    if v is None:
        return {}
    if isinstance(v, str):
        try:
            return json.loads(v) or {}
        except json.JSONDecodeError:
            return {}
    return dict(v)


def _date_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    iso = getattr(v, "isoformat", None)
    return iso() if callable(iso) else safe_str(v)


def _mastery(rows: list) -> MasteryDist:
    """Count standard rows by band."""
    g = y = p = 0
    for r in rows:
        b = r.band if hasattr(r, "band") else _band(_f(r.get("pct")))
        if b == "green":
            g += 1
        elif b == "yellow":
            y += 1
        elif b == "pink":
            p += 1
    return MasteryDist(green=g, yellow=y, pink=p, total=g + y + p)


class StudentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = StudentRepository(session)
        self.cube = CubeRepository(session)

    # Sort whitelist for the roster (interpolated — value MUST come from here).
    _SORT_SQL = {
        "name": "lower(name)",
        "overall": "overall_pct",
        "assessments": "n_assessments",
        "subjects": "n_subjects",
    }

    async def browse_students(
        self,
        session_filter: Optional[str] = None,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        section: Optional[str] = None,
        instructor: Optional[str] = None,
        q: Optional[str] = None,
        sort: str = "name",
        direction: str = "asc",
        limit: int = DEFAULT_BROWSE_PAGE_SIZE,
        offset: int = 0,
    ) -> StudentBrowsePage:
        sort_sql = self._SORT_SQL.get(sort, "lower(name)")
        dir_sql = "DESC" if direction.lower() == "desc" else "ASC"
        rows_raw, total = await self.repo.browse_students(
            session=session_filter,
            subject=subject,
            grade=grade,
            category=category,
            section=section,
            instructor=instructor,
            q=q,
            sort_sql=sort_sql,
            dir_sql=dir_sql,
            limit=limit,
            offset=offset,
        )
        rows = []
        for r in rows_raw:
            overall_pct = _f(r.get("overall_pct"))
            subjects = [
                StudentSubjectStat(
                    subject=safe_str(s.get("subject")),
                    grade=safe_str(s.get("grade")) or None,
                    pct=_f(s.get("pct")),
                    band=_band(_f(s.get("pct"))),
                )
                for s in _as_list(r.get("subjects"))
            ]
            rows.append(
                StudentBrowseRow(
                    uid=safe_str(r.get("uid")),
                    name=safe_str(r.get("name")),
                    grades=[safe_str(g) for g in _as_list(r.get("grades")) if g],
                    overall_pct=overall_pct,
                    overall_band=_band(overall_pct),
                    n_subjects=to_int(r.get("n_subjects")),
                    n_assessments=to_int(r.get("n_assessments")),
                    subjects=subjects,
                    mastery=MasteryDist(
                        green=to_int(r.get("green")),
                        yellow=to_int(r.get("yellow")),
                        pink=to_int(r.get("pink")),
                        total=to_int(r.get("mastery_total")),
                    ),
                )
            )
        return StudentBrowsePage(rows=rows, total=total, limit=limit, offset=offset)

    async def build_student_report(
        self, uid: str, session_filter: Optional[str] = None
    ) -> PerStudentReportPayload:
        identity = await self.repo.get_student_identity(uid)
        if not identity:
            raise ResourceNotFoundError("Student", uid)

        student = StudentIdentity(
            uid=safe_str(identity.get("uid")) or uid,
            name=safe_str(identity.get("name")) or uid,
            first=safe_str(identity.get("first")) or None,
            last=safe_str(identity.get("last")) or None,
            grad_year=safe_str(identity.get("grad_year")) or None,
            gender=safe_str(identity.get("gender")) or None,
        )
        meta = await self.cube.get_school_wide_meta() or {}
        school = ReportSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
        )

        totals = await self.repo.get_subject_totals(uid, session_filter)
        if not totals:
            # Student exists but has no scored data in scope (e.g. cube-only
            # school, or a filtered session they didn't sit). Graceful empty.
            return PerStudentReportPayload(
                student=student,
                school=school,
                session=safe_str(session_filter) or school.current_session,
                grades=[],
                overall=StudentOverall(),
                subjects=[],
                has_data=False,
            )

        assessments = await self.repo.get_assessments(uid, session_filter)
        standards = await self.repo.get_standards(uid, session_filter)
        strands = await self.repo.get_strands(uid, session_filter)
        markers = await self.repo.get_class_markers(session_filter)

        by_subject = {
            (safe_str(m.get("subject")), safe_str(m.get("grade"))): m
            for m in _as_list(markers.get("by_subject"))
        }
        by_assessment = {
            safe_str(m.get("subject_id")): _f(m.get("class_pct"))
            for m in _as_list(markers.get("by_assessment"))
        }
        overall_marker = _as_obj(markers.get("overall"))

        def _key(row: dict) -> str:
            # Subjects are merged by NAME (grades folded to the dominant grade
            # in the repository), so a stray cross-grade misfiling does not spawn
            # a phantom subject card. Bucket assessments/standards/strands by
            # subject name to match.
            return safe_str(row.get("subject"))

        # Index the flat assessment/standard/strand rows by subject name ONCE, so
        # the per-subject loop below is O(n) instead of re-scanning every list for
        # each subject (defaultdict preserves the source order within each bucket).
        asmts_by_subject: dict[str, list[dict]] = defaultdict(list)
        for a in assessments:
            asmts_by_subject[_key(a)].append(a)
        stds_by_subject: dict[str, list[dict]] = defaultdict(list)
        for s in standards:
            stds_by_subject[_key(s)].append(s)
        strands_by_subject: dict[str, list[dict]] = defaultdict(list)
        for s in strands:
            strands_by_subject[_key(s)].append(s)

        def _assessment_row(a: dict) -> StudentAssessmentRow:
            sc = _f(a.get("score"))
            poss = _f(a.get("possible"))
            apct = round(100.0 * sc / poss, 1) if poss else None
            return StudentAssessmentRow(
                item_id=safe_str(a.get("item_id")),
                name=safe_str(a.get("name")),
                date=_date_str(a.get("date")),
                n_questions=to_int(a.get("n_questions")),
                score=sc,
                possible=poss,
                pct=apct,
                band=_band(apct),
                class_pct=by_assessment.get(safe_str(a.get("item_id"))),
            )

        subjects: list[StudentSubjectReport] = []
        tot_score = tot_possible = 0.0
        tot_assess = 0
        all_ids: set[str] = set()
        overall_dist = {"green": 0, "yellow": 0, "pink": 0}

        for t in totals:
            key = _key(t)
            score = _f(t.get("score")) or 0.0
            possible = _f(t.get("possible")) or 0.0
            pct = round(100.0 * score / possible, 1) if possible else None

            subj_assessments = [
                _assessment_row(a) for a in asmts_by_subject.get(key, [])
            ]
            subj_standards = [
                StudentStandardRow(
                    identifier=safe_str(s.get("identifier")),
                    code=safe_str(s.get("code")) or safe_str(s.get("identifier")),
                    description=_strip_html(safe_str(s.get("description"))) or None,
                    strand=safe_str(s.get("strand")) or None,
                    cluster=safe_str(s.get("cluster")) or None,
                    complexity=safe_str(s.get("complexity")) or None,
                    direct_link=s.get("direct_link") or None,
                    n_questions=to_int(s.get("n_questions")),
                    pct=_f(s.get("pct")),
                    band=_band(_f(s.get("pct"))),
                )
                for s in stds_by_subject.get(key, [])
            ]
            subj_strands = [
                StudentStrandRow(
                    strand=safe_str(s.get("strand")),
                    n_questions=to_int(s.get("n_questions")),
                    pct=_f(s.get("pct")),
                    band=_band(_f(s.get("pct"))),
                )
                for s in strands_by_subject.get(key, [])
            ]

            dist = _mastery(subj_standards)
            overall_dist["green"] += dist.green
            overall_dist["yellow"] += dist.yellow
            overall_dist["pink"] += dist.pink
            for sr in subj_standards:
                all_ids.add(sr.identifier)

            cm = by_subject.get(
                (safe_str(t.get("subject")), safe_str(t.get("grade"))), {}
            )
            n_assess = to_int(t.get("n_assessments"))
            tot_score += score
            tot_possible += possible
            tot_assess += n_assess

            subjects.append(
                StudentSubjectReport(
                    subject=safe_str(t.get("subject")),
                    grade=safe_str(t.get("grade")) or None,
                    assessment_types=safe_str(t.get("assessment_types")) or None,
                    pct=pct,
                    band=_band(pct),
                    score=round(score, 1),
                    possible=round(possible, 1),
                    n_questions=to_int(t.get("n_questions")),
                    n_assessments=n_assess,
                    class_pct=_f(cm.get("class_pct")),
                    class_n_students=to_int(cm.get("n_students")) or None,
                    mastery=dist,
                    assessments=subj_assessments,
                    standards=subj_standards,
                    strands=subj_strands,
                )
            )

        overall_pct = round(100.0 * tot_score / tot_possible, 1) if tot_possible else None
        grades = sorted({s.grade for s in subjects if s.grade})
        overall = StudentOverall(
            pct=overall_pct,
            band=_band(overall_pct),
            score=round(tot_score, 1),
            possible=round(tot_possible, 1),
            n_subjects=len(subjects),
            n_assessments=tot_assess,
            n_standards=len(all_ids),
            class_pct=_f(overall_marker.get("class_pct")),
            class_n_students=to_int(overall_marker.get("n_students")) or None,
            mastery=MasteryDist(
                green=overall_dist["green"],
                yellow=overall_dist["yellow"],
                pink=overall_dist["pink"],
                total=sum(overall_dist.values()),
            ),
        )

        return PerStudentReportPayload(
            student=student,
            school=school,
            session=safe_str(session_filter) or school.current_session,
            grades=grades,
            overall=overall,
            subjects=subjects,
            has_data=True,
        )
