"""Server-side XLSX serialization for GAINS reports (Phase B / B2+B3).

Each ``report_to_xlsx(kind, payload)`` builds an :class:`openpyxl.Workbook`
from the SAME composed Pydantic payloads the JSON endpoints return — there
is one source of truth (``ReportService.build_*``), so the workbook can never
drift from the on-screen view.

The per-report grain mirrors the on-screen visible grain (and the CSV
flatteners in ``frontend/src/lib/reports/export-csv.ts``):

* QRA / QRA-paginated      → one row per question
* QRA-by-teacher           → teacher-group header rows + member question rows
* QRA-by-standard-teacher  → standard-group → teacher-group → question rows
* QSR                      → student × question matrix grouped by standard
                             column bands, per-teacher subtotals, grand total
* YTD                      → student rows × standard columns, teacher subtotals
* Standard / Strand Summary, SDD → one row per standard / strand
* IAD                      → distractor block + student-attempt block

Performance-cell fills reuse the EXACT hex from
``frontend/src/lib/reports/colors.ts``: the interactive/summary surfaces use
``PERF_*`` and the QSR family uses ``QSR_*`` (see the module constants below;
they are copied verbatim and asserted against ``colors.ts`` in the test
suite). ``pandas`` is intentionally NOT imported — only ``openpyxl``.
"""

from __future__ import annotations

import io
from typing import Any, Iterable, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.core.constants import PERF_BAND_HIGH, PERF_BAND_MID
from app.schemas.reports import (
    IncorrectAnswerDetailsPayload,
    QraByStandardTeacherPayload,
    QraByTeacherPayload,
    QraPaginatedPayload,
    QuestionResponseAnalysisPayload,
    QuestionSummaryPointsPayload,
    StandardsDeepDivePayload,
    StandardSummaryPayload,
    StrandSummaryPayload,
    YearToDatePerformancePayload,
)
from app.services.report_service import (
    _decode_html,
    _strip_html,
)

# ─── Colors (verbatim from frontend/src/lib/reports/colors.ts) ───────────────
# openpyxl wants ARGB ("FF" + RRGGBB). The trailing 6 hex chars MUST equal the
# colors.ts literals (a unit test asserts this). Do NOT edit one without the
# other.
#
# Interactive / summary palette (PERF_*):
PERF_PINK = "FFFFB3D9"  # colors.ts PERF_PINK  #FFB3D9 (<70)
PERF_YELLOW = "FFFFF066"  # colors.ts PERF_YELLOW #FFF066 (70–80)
PERF_GREEN = "FF7BE38C"  # colors.ts PERF_GREEN  #7BE38C (≥80)
# QSR paginated palette (QSR_*) — the exact legacy SSRS fills:
QSR_PINK = "FFFFCCFF"  # colors.ts QSR_PINK   #FFCCFF (<70)
QSR_YELLOW = "FFFFF591"  # colors.ts QSR_YELLOW #FFF591 (70–80)
QSR_GREEN = "FF99FF99"  # colors.ts QSR_GREEN  #99FF99 (≥80)
# xlsx-LOCAL yellow: the real legacy SSRS .xlsx uses #FFF492 (NOT colors.ts's
# #FFF591). colors.ts drives the web and must NOT change, so the QSR xlsx
# Score% banding uses this local override for exact .xlsx parity.
QSR_YELLOW_XLSX = "FFFFF492"
# QSR SSRS chrome (verbatim from the legacy .xlsx, not part of colors.ts):
QSR_NAVY = "FF4472C4"  # header bars (matches PBIX_ACCENT_NAVY)
QSR_GREY_SCORE = "FFC0C0C0"  # per-band / per-question Score% sub-columns
QSR_GREY_TOTAL = "FFD3D3D3"  # footer Possible Points / # Correct / label cells
QSR_WHITE = "FFFFFFFF"
# Chrome:
HEADER_BAR_BG = "FFB8DBFF"  # colors.ts HEADER_BAR_BG #B8DBFF
LAYOUT_BORDER = "FFB3B3B3"  # colors.ts LAYOUT_BORDER #B3B3B3
INCORRECT_GREY = "FFCCCCCC"  # colors.ts INCORRECT_GREY #CCCCCC
PBIX_ACCENT_NAVY = "FF4472C4"  # colors.ts PBIX_ACCENT_NAVY #4472C4

# PBIX-mandated band thresholds (mirror report_service / colors.ts).
_BAND_HIGH = PERF_BAND_HIGH
_BAND_MID = PERF_BAND_MID

# Excel number formats.
_PCT_FMT = "0.0%"
_PCT_FMT_INT = "0%"

_THIN = Side(style="thin", color=LAYOUT_BORDER)
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FONT = Font(bold=True, color="FF000000")
_HEADER_FONT_WHITE = Font(bold=True, color="FFFFFFFF")
_BOLD = Font(bold=True)
_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")

_HEADER_FILL = PatternFill("solid", fgColor=HEADER_BAR_BG)
_NAVY_FILL = PatternFill("solid", fgColor=PBIX_ACCENT_NAVY)
_GREY_FILL = PatternFill("solid", fgColor=INCORRECT_GREY)


def _perf_fill(grade: Optional[float]) -> Optional[PatternFill]:
    """PERF_* three-band fill (interactive/summary surfaces). ``None`` → no fill."""
    if grade is None:
        return None
    if grade < _BAND_MID:
        return PatternFill("solid", fgColor=PERF_PINK)
    if grade < _BAND_HIGH:
        return PatternFill("solid", fgColor=PERF_YELLOW)
    return PatternFill("solid", fgColor=PERF_GREEN)


def _qsr_fill(grade: Optional[float]) -> Optional[PatternFill]:
    """QSR_* three-band fill (QSR paginated family). ``None`` → no fill."""
    if grade is None:
        return None
    if grade < _BAND_MID:
        return PatternFill("solid", fgColor=QSR_PINK)
    if grade < _BAND_HIGH:
        return PatternFill("solid", fgColor=QSR_YELLOW)
    return PatternFill("solid", fgColor=QSR_GREEN)


# ─── Cell helpers ────────────────────────────────────────────────────────────


def _plain(raw: Optional[str]) -> str:
    """Reduce a rich HTML/LaTeX cell to plain text (drops images/markup)."""
    return _decode_html(_strip_html(raw))


def _write_header(ws: Worksheet, row: int, labels: Iterable[str], *, fill: PatternFill = _HEADER_FILL, white: bool = False) -> None:
    font = _HEADER_FONT_WHITE if white else _HEADER_FONT
    for col, label in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=col, value=label)
        cell.font = font
        cell.fill = fill
        cell.border = _BORDER
        cell.alignment = _CENTER


def _autosize(ws: Worksheet, widths: dict[int, float]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def _set_title(ws: Worksheet, title: str) -> None:
    # Excel sheet titles cap at 31 chars and forbid []:*?/\ — sanitize.
    safe = "".join(c for c in title if c not in '[]:*?/\\')[:31] or "Report"
    ws.title = safe


def _pct_cell(
    ws: Worksheet,
    row: int,
    col: int,
    grade: Optional[float],
    *,
    fill: Optional[PatternFill] = None,
    fmt: str = _PCT_FMT,
) -> None:
    """Write a 0–1 fraction as a percent-formatted cell with an optional fill."""
    cell = ws.cell(row=row, column=col, value=grade if grade is not None else None)
    cell.number_format = fmt
    cell.alignment = _RIGHT
    cell.border = _BORDER
    if fill is not None:
        cell.fill = fill


def _txt_cell(ws: Worksheet, row: int, col: int, value: Any, *, align: Alignment = _LEFT, bold: bool = False) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.alignment = align
    cell.border = _BORDER
    if bold:
        cell.font = _BOLD


# ─── QRA interactive / paginated (one row per question) ──────────────────────

_QRA_HEADERS = [
    "Question No",
    "Question",
    "Standards",
    "Correct Answer",
    "Grade Average %",
    "% Incorrect",
    "Incorrect Choices",
    "Incorrect Choice Students",
]


def _qra_question_rows_ws(ws: Worksheet, questions: list[dict[str, Any]]) -> None:
    _write_header(ws, 1, _QRA_HEADERS)
    r = 2
    for q in questions:
        ga = q["grade_average"]
        incorrect = 0.0 if ga >= 1 else 1 - ga
        _txt_cell(ws, r, 1, q["question_no"], align=_CENTER)
        _txt_cell(ws, r, 2, _plain(q["question"]))
        _txt_cell(ws, r, 3, _plain(q["standards"]))
        _txt_cell(ws, r, 4, _plain(q["correct_answer"]))
        _pct_cell(ws, r, 5, ga, fill=_perf_fill(ga))
        _pct_cell(ws, r, 6, incorrect)
        _txt_cell(ws, r, 7, "" if ga >= 1 else _plain(q["incorrect_choice_details"]))
        _txt_cell(ws, r, 8, "" if ga >= 1 else _plain(q["incorrect_details_name"]))
        r += 1
    ws.freeze_panes = "A2"
    _autosize(ws, {1: 12, 2: 50, 3: 22, 4: 22, 5: 15, 6: 12, 7: 30, 8: 36})


def _qra_to_xlsx(payload: QuestionResponseAnalysisPayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "QRA")
    rows = [
        {
            "question_no": q.question_no,
            "question": q.question,
            "standards": q.standards,
            "correct_answer": q.correct_answer,
            "grade_average": q.grade_average,
            "incorrect_choice_details": q.incorrect_choice_details,
            "incorrect_details_name": q.incorrect_details_name,
        }
        for q in payload.questions_overall
    ]
    _qra_question_rows_ws(ws, rows)
    return wb


def _qra_paginated_to_xlsx(payload: QraPaginatedPayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "QRA Paginated")
    rows = [
        {
            "question_no": q.question_no,
            "question": q.question,
            "standards": q.standards,
            "correct_answer": q.correct_answer,
            "grade_average": q.grade_average,
            "incorrect_choice_details": q.incorrect_choice_details,
            "incorrect_details_name": q.incorrect_details_name,
        }
        for q in payload.questions
    ]
    _qra_question_rows_ws(ws, rows)
    return wb


# ─── QRA grouped (by-teacher, by-standard-teacher) ───────────────────────────

_QRA_GROUP_HEADERS = [
    "Group",
    "Question No",
    "Question",
    "Standards",
    "Correct Answer",
    "Grade Average %",
]


def _qra_group_widths(ws: Worksheet) -> None:
    _autosize(ws, {1: 28, 2: 12, 3: 50, 4: 22, 5: 22, 6: 16})


def _qra_member_row(ws: Worksheet, r: int, q: Any) -> None:
    _txt_cell(ws, r, 1, "")
    _txt_cell(ws, r, 2, q.question_no, align=_CENTER)
    _txt_cell(ws, r, 3, _plain(q.question))
    _txt_cell(ws, r, 4, _plain(q.standards))
    _txt_cell(ws, r, 5, _plain(q.correct_answer))
    _pct_cell(ws, r, 6, q.grade_average, fill=_perf_fill(q.grade_average))


def _qra_by_teacher_to_xlsx(payload: QraByTeacherPayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "QRA by Teacher")
    _write_header(ws, 1, _QRA_GROUP_HEADERS)
    r = 2
    for g in payload.teacher_groups:
        _txt_cell(ws, r, 1, f"Teacher: {g.section_instructor}", bold=True)
        for c in range(2, 6):
            ws.cell(row=r, column=c).fill = _HEADER_FILL
            ws.cell(row=r, column=c).border = _BORDER
        ws.cell(row=r, column=1).fill = _HEADER_FILL
        _pct_cell(ws, r, 6, g.teacher_grade_average, fill=_perf_fill(g.teacher_grade_average))
        ws.cell(row=r, column=6).font = _BOLD
        r += 1
        for q in g.questions:
            _qra_member_row(ws, r, q)
            r += 1
    ws.freeze_panes = "A2"
    _qra_group_widths(ws)
    return wb


def _qra_by_standard_teacher_to_xlsx(payload: QraByStandardTeacherPayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "QRA by Std & Teacher")
    _write_header(ws, 1, _QRA_GROUP_HEADERS)
    r = 2
    for sg in payload.standard_groups:
        _txt_cell(ws, r, 1, f"Standard: {sg.cpalms_standard}", bold=True)
        _txt_cell(ws, r, 3, _plain(sg.standard_description), bold=True)
        for c in (1, 2, 3, 4, 5):
            ws.cell(row=r, column=c).fill = _NAVY_FILL
            ws.cell(row=r, column=c).font = _HEADER_FONT_WHITE
        _pct_cell(ws, r, 6, sg.standard_average, fill=_perf_fill(sg.standard_average))
        ws.cell(row=r, column=6).font = _BOLD
        r += 1
        for tg in sg.teacher_groups:
            _txt_cell(ws, r, 1, f"Teacher: {tg.section_instructor}", bold=True)
            for c in range(1, 6):
                ws.cell(row=r, column=c).fill = _HEADER_FILL
                ws.cell(row=r, column=c).border = _BORDER
            _pct_cell(ws, r, 6, tg.teacher_standard_average, fill=_perf_fill(tg.teacher_standard_average))
            ws.cell(row=r, column=6).font = _BOLD
            r += 1
            for q in tg.questions:
                _qra_member_row(ws, r, q)
                r += 1
    ws.freeze_panes = "A2"
    _qra_group_widths(ws)
    return wb


# ─── QSR: SSRS partial-credit student × question matrix ──────────────────────

# Legacy SSRS .xlsx number/locale format for percents (en-US locale tag).
_QSR_PCT_FMT = "[$-010409]0%"
# QSR cells use the body font Segoe UI 9 / #333333; headers white on navy.
_QSR_FONT = Font(name="Segoe UI", size=9, color="FF333333")
_QSR_FONT_BOLD = Font(name="Segoe UI", size=9, color="FF333333", bold=True)
_QSR_HEADER_FONT = Font(name="Segoe UI", size=9, color=QSR_WHITE)
_QSR_TITLE_FONT = Font(name="Segoe UI", size=20, bold=True, color="FF000000")
_QSR_SUB_FONT = Font(name="Segoe UI", size=12, color="FF000000")

_QSR_NAVY_FILL = PatternFill("solid", fgColor=QSR_NAVY)
_QSR_GREY_SCORE_FILL = PatternFill("solid", fgColor=QSR_GREY_SCORE)
_QSR_GREY_TOTAL_FILL = PatternFill("solid", fgColor=QSR_GREY_TOTAL)
_QSR_GREEN_FILL = PatternFill("solid", fgColor=QSR_GREEN)
_QSR_PINK_FILL = PatternFill("solid", fgColor=QSR_PINK)
_QSR_CENTER_TOP = Alignment(horizontal="center", vertical="top", wrap_text=True)
_QSR_LEFT_TOP = Alignment(horizontal="left", vertical="top", wrap_text=True)


def _qsr_score_fill(pct: Optional[float]) -> PatternFill:
    """Overall / per-question Score% 3-band fill: <70 pink, 70–<80 yellow,
    ≥80 green. Uses the xlsx-LOCAL yellow (#FFF492) — the real legacy value."""
    if pct is None:
        return _QSR_PINK_FILL
    if pct < _BAND_MID:
        return _QSR_PINK_FILL
    if pct < _BAND_HIGH:
        return PatternFill("solid", fgColor=QSR_YELLOW_XLSX)
    return _QSR_GREEN_FILL


def _qsr_cell_fill(received: Optional[float]) -> PatternFill:
    """Leaf-question point cell fill: <0.5 pink, ≥0.5 green (legacy binary
    threshold on the fractional points_received)."""
    return _QSR_GREEN_FILL if (received is not None and received >= 0.5) else _QSR_PINK_FILL


def _qsr_to_xlsx(payload: QuestionSummaryPointsPayload) -> Workbook:
    """SSRS partial-credit QSR matrix — exact legacy .xlsx parity.

    Layout (verified cell-for-cell against the legacy Chapter 9 Test
    8359960427 .xlsx):

      Rows 2/4/6  SSRS title block: "Question Summary Report" (A) /
                  "<assessment_type>" (B) / "<Subject> - <Grade>: <Item>" (C).
      Row 8       band header (navy): Classroom Instructors | Student Name |
                  Score % | <CPALMS band, merged over its leaf cols> … |
                  Possible Points | # Correct Answers.
      Row 9       leaf header (navy): question_no per leaf col + a "Score %"
                  sub-column at the end of every band.
      Freeze A8.
      Body        one row per (teacher → student); instructor name + overall %
                  merged down the teacher's rows (cols A:C). Each leaf cell is
                  ``points_received`` (fractional), <0.5 pink / ≥0.5 green; the
                  overall Score% (col C) is perf-banded; per-band Score% sub-
                  columns are grey. Possible Points = SUM(possible),
                  # Correct = SUM(received).
      Footer trio Possible Points / # Correct Answers / Score % (grey labels);
                  the Score% footer perf-bands the leaf + overall cells, greys
                  the per-band sub-columns.
    """
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "Paginated - Question Summary Re")

    a = payload.assessment
    questions = payload.questions
    bands = payload.bands

    # ── Column model ────────────────────────────────────────────────────────
    # A:C = Classroom Instructors (merged), D = Student Name, E = Score %.
    # Then per band: one column per leaf question + one band Score% sub-column.
    # Finally Possible Points + # Correct Answers.
    INSTR_C, STU_C, SCORE_C = 1, 4, 5
    qid_col: dict[str, int] = {}
    band_score_col: dict[str, int] = {}
    col = 6
    for b in bands:
        for qid in b.question_ids:
            qid_col[qid] = col
            col += 1
        band_score_col[b.cpalms_standard] = col
        col += 1
    possible_col = col
    correct_col = col + 1
    last_col = correct_col

    qcol = {q.question_id: q for q in questions}

    # ── Title block (rows 2 / 4 / 6) ────────────────────────────────────────
    t = ws.cell(row=2, column=1, value="Question Summary Report")
    t.font = _QSR_TITLE_FONT
    t.alignment = Alignment(vertical="top", wrap_text=True)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(22, last_col))
    # Leading space mirrors the legacy SSRS render of the assessment-type line.
    sub = ws.cell(row=4, column=2, value=f" {a.assessment_type}" if a.assessment_type else "")
    sub.font = _QSR_SUB_FONT
    sub.alignment = Alignment(vertical="center", wrap_text=True)
    ws.merge_cells(start_row=4, start_column=2, end_row=4, end_column=12)
    course_line = ": ".join(
        p for p in (" - ".join(x for x in (a.subject, a.grade) if x), a.item_name) if p
    )
    cl = ws.cell(row=6, column=3, value=course_line)
    cl.font = _QSR_SUB_FONT
    cl.alignment = Alignment(vertical="center", wrap_text=True)
    ws.merge_cells(start_row=6, start_column=3, end_row=6, end_column=max(23, last_col))

    # ── Row 8: band header (navy) ───────────────────────────────────────────
    def _navy(row: int, col: int, value=None, *, center=True):
        c = ws.cell(row=row, column=col, value=value)
        c.fill = _QSR_NAVY_FILL
        c.font = _QSR_HEADER_FONT
        c.alignment = _CENTER if center else _LEFT
        c.border = _BORDER
        return c

    _navy(8, INSTR_C, "Classroom Instructors", center=False)
    ws.merge_cells(start_row=8, start_column=INSTR_C, end_row=9, end_column=3)
    for cc in (2, 3):
        _navy(8, cc)
        _navy(9, cc)
    _navy(8, STU_C, "Student Name", center=False)
    ws.merge_cells(start_row=8, start_column=STU_C, end_row=9, end_column=STU_C)
    _navy(9, STU_C)
    _navy(8, SCORE_C, "Score %", center=False)
    ws.merge_cells(start_row=8, start_column=SCORE_C, end_row=9, end_column=SCORE_C)
    _navy(9, SCORE_C)
    for b in bands:
        start = qid_col[b.question_ids[0]]
        end = band_score_col[b.cpalms_standard]  # band header spans up to score col
        _navy(8, start, b.cpalms_standard)
        if end > start:
            ws.merge_cells(start_row=8, start_column=start, end_row=8, end_column=end)
            for k in range(start + 1, end + 1):
                _navy(8, k)
        # Row 9 leaf question_no headers + band Score% sub-column.
        for qid in b.question_ids:
            _navy(9, qid_col[qid], qcol[qid].question_no)
        _navy(9, band_score_col[b.cpalms_standard], "Score %")
    _navy(8, possible_col, "Possible Points")
    ws.merge_cells(start_row=8, start_column=possible_col, end_row=9, end_column=possible_col)
    _navy(9, possible_col)
    _navy(8, correct_col, "# Correct Answers")
    ws.merge_cells(start_row=8, start_column=correct_col, end_row=9, end_column=correct_col)
    _navy(9, correct_col)

    # ── Body ────────────────────────────────────────────────────────────────
    def _body(row, col, value, *, fill=None, fmt=None):
        c = ws.cell(row=row, column=col, value=value)
        c.font = _QSR_FONT
        c.alignment = _QSR_CENTER_TOP
        c.border = _BORDER
        if fill is not None:
            c.fill = fill
        if fmt is not None:
            c.number_format = fmt
        return c

    r = 9 + 1  # first body row = 10
    for g in payload.teacher_groups:
        first_row = r
        for s in g.students:
            # Student name (D), overall Score% (E, perf-banded).
            sc = _body(r, STU_C, s.user_name, fill=_qsr_score_fill(s.score_pct))
            sc.alignment = _QSR_LEFT_TOP
            _body(r, SCORE_C, s.score_pct, fill=_qsr_score_fill(s.score_pct), fmt=_QSR_PCT_FMT)
            # Leaf point cells.
            for qid, ccol in qid_col.items():
                recv = s.cells.get(qid)
                _body(r, ccol, recv, fill=_qsr_cell_fill(recv))
            # Per-band Score% sub-columns (grey).
            for b in bands:
                _body(
                    r,
                    band_score_col[b.cpalms_standard],
                    s.band_pct.get(b.cpalms_standard),
                    fill=_QSR_GREY_SCORE_FILL,
                    fmt=_QSR_PCT_FMT,
                )
            # Totals (grey).
            _body(r, possible_col, s.possible_points, fill=_QSR_GREY_TOTAL_FILL)
            _body(r, correct_col, s.correct_count, fill=_QSR_GREY_TOTAL_FILL)
            r += 1
        # Instructor block merged down the teacher's student rows (A:C),
        # carrying "<instructor> <overall %>".
        label = f"{g.section_instructor} {round(g.teacher_score_pct * 100, 1)}%"
        ib = ws.cell(row=first_row, column=INSTR_C, value=label)
        ib.font = _QSR_FONT
        ib.fill = PatternFill("solid", fgColor=QSR_WHITE)
        ib.alignment = Alignment(vertical="top", wrap_text=True)
        ib.border = _BORDER
        if r - 1 >= first_row:
            ws.merge_cells(start_row=first_row, start_column=INSTR_C, end_row=r - 1, end_column=3)

    # ── Footer trio ─────────────────────────────────────────────────────────
    gt = payload.grand_total

    def _footer_label(row, text):
        c = ws.cell(row=row, column=INSTR_C, value=text)
        c.font = _QSR_FONT_BOLD
        c.fill = _QSR_GREY_TOTAL_FILL
        c.alignment = _QSR_LEFT_TOP
        c.border = _BORDER
        ws.merge_cells(start_row=row, start_column=INSTR_C, end_row=row, end_column=STU_C)
        for k in range(2, STU_C + 1):
            cc = ws.cell(row=row, column=k)
            cc.fill = _QSR_GREY_TOTAL_FILL
            cc.border = _BORDER

    # Possible Points row.
    _footer_label(r, "Possible Points")
    _body(r, SCORE_C, gt.possible_points, fill=_QSR_GREY_TOTAL_FILL)
    for qid, ccol in qid_col.items():
        _body(r, ccol, gt.per_question_possible.get(qid, 0.0), fill=_QSR_GREY_TOTAL_FILL)
    for b in bands:
        _body(r, band_score_col[b.cpalms_standard], gt.band_possible.get(b.cpalms_standard, 0.0), fill=_QSR_GREY_SCORE_FILL)
    _body(r, possible_col, gt.possible_points, fill=_QSR_GREY_TOTAL_FILL)
    _body(r, correct_col, gt.correct_count, fill=_QSR_GREY_TOTAL_FILL)
    r += 1
    # # Correct Answers row.
    _footer_label(r, "# Correct Answers")
    _body(r, SCORE_C, gt.correct_count, fill=_QSR_GREY_TOTAL_FILL)
    for qid, ccol in qid_col.items():
        _body(r, ccol, gt.per_question_correct.get(qid, 0.0), fill=_QSR_GREY_TOTAL_FILL)
    for b in bands:
        _body(r, band_score_col[b.cpalms_standard], gt.band_correct.get(b.cpalms_standard, 0.0), fill=_QSR_GREY_SCORE_FILL)
    r += 1
    # Score % row (perf-banded leaf + overall; grey per-band sub-columns).
    _footer_label(r, "Score %")
    _body(r, SCORE_C, gt.score_pct, fill=_qsr_score_fill(gt.score_pct), fmt=_QSR_PCT_FMT)
    for qid, ccol in qid_col.items():
        p = gt.per_question_pct.get(qid, 0.0)
        _body(r, ccol, p, fill=_qsr_score_fill(p), fmt=_QSR_PCT_FMT)
    for b in bands:
        _body(
            r,
            band_score_col[b.cpalms_standard],
            gt.band_pct.get(b.cpalms_standard, 0.0),
            fill=_QSR_GREY_SCORE_FILL,
            fmt=_QSR_PCT_FMT,
        )

    # ── Freeze + widths ─────────────────────────────────────────────────────
    ws.freeze_panes = "A8"
    ws.column_dimensions["A"].width = 0.2
    ws.column_dimensions["B"].width = 0.2
    ws.column_dimensions["C"].width = 13.33
    ws.column_dimensions[get_column_letter(STU_C)].width = 14.61
    ws.column_dimensions[get_column_letter(SCORE_C)].width = 8.0
    for ccol in qid_col.values():
        ws.column_dimensions[get_column_letter(ccol)].width = 8.23
    for ccol in band_score_col.values():
        ws.column_dimensions[get_column_letter(ccol)].width = 6.73
    ws.column_dimensions[get_column_letter(possible_col)].width = 7.76
    ws.column_dimensions[get_column_letter(correct_col)].width = 8.37
    return wb


# ─── YTD: student rows × standard columns (points) ───────────────────────────


def _ytd_to_xlsx(payload: YearToDatePerformancePayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "YTD Longitudinal")

    standards = payload.standards
    std_keys = [s.schoology_standard for s in standards]
    header = ["Classroom Instructors", "Student Name", "Tests Taken"]
    header += [s.standard_label for s in standards]
    header += ["Score %"]
    _write_header(ws, 1, header)

    first_std_col = 4
    last_std_col = first_std_col + len(standards) - 1
    score_col = last_std_col + 1

    r = 2
    for g in payload.teacher_groups:
        for idx, s in enumerate(g.students):
            _txt_cell(ws, r, 1, g.section_instructor if idx == 0 else "", bold=(idx == 0))
            if idx == 0:
                ws.cell(row=r, column=1).fill = _HEADER_FILL
            _txt_cell(ws, r, 2, s.user_name)
            _txt_cell(ws, r, 3, s.tests_taken, align=_CENTER)
            for ki, key in enumerate(std_keys):
                cell = s.cells.get(key)
                _txt_cell(
                    ws,
                    r,
                    first_std_col + ki,
                    cell.points_received if cell else None,
                    align=_CENTER,
                )
            _pct_cell(ws, r, score_col, s.score_pct, fill=_perf_fill(s.score_pct))
            r += 1
        # Teacher subtotal row (# correct points + Score %).
        _txt_cell(ws, r, 1, f"Subtotal: {g.section_instructor}", bold=True)
        ws.cell(row=r, column=1).fill = _HEADER_FILL
        _txt_cell(ws, r, 2, "")
        for ki, key in enumerate(std_keys):
            sub = g.standard_subtotals.get(key)
            _txt_cell(
                ws,
                r,
                first_std_col + ki,
                sub.points_received if sub else None,
                align=_CENTER,
                bold=True,
            )
        _pct_cell(ws, r, score_col, g.teacher_score_pct, fill=_perf_fill(g.teacher_score_pct))
        ws.cell(row=r, column=score_col).font = _BOLD
        r += 1

    # Grand total.
    gt = payload.grand_total
    _txt_cell(ws, r, 1, "Grand Total", bold=True)
    ws.cell(row=r, column=1).fill = _GREY_FILL
    _txt_cell(ws, r, 2, "")
    for ki, key in enumerate(std_keys):
        t = gt.standard_totals.get(key)
        _txt_cell(ws, r, first_std_col + ki, t.points_received if t else None, align=_CENTER, bold=True)
    _pct_cell(ws, r, score_col, gt.score_pct, fill=_perf_fill(gt.score_pct))
    ws.cell(row=r, column=score_col).font = _BOLD

    ws.freeze_panes = ws.cell(row=2, column=first_std_col).coordinate
    widths = {1: 22, 2: 22, 3: 12}
    for ki in range(len(standards)):
        widths[first_std_col + ki] = 14
    widths[score_col] = 10
    _autosize(ws, widths)
    return wb


# ─── Standard / Strand Summary, SDD (one row per standard / strand) ──────────


def _standard_summary_to_xlsx(payload: StandardSummaryPayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "Standard Summary")
    headers = [
        "Standard",
        "CPALMS Standard",
        "Strand",
        "Description",
        "Total Questions",
        "Grade Average %",
        "% Incorrect",
    ]
    _write_header(ws, 1, headers)
    r = 2
    for s in payload.standards:
        _txt_cell(ws, r, 1, s.schoology_standard)
        _txt_cell(ws, r, 2, s.cpalms_standard)
        _txt_cell(ws, r, 3, s.strand)
        _txt_cell(ws, r, 4, _plain(s.description))
        _txt_cell(ws, r, 5, s.num_questions, align=_CENTER)
        _pct_cell(ws, r, 6, s.grade_average, fill=_perf_fill(s.grade_average))
        _pct_cell(ws, r, 7, 1 - s.grade_average)
        r += 1
    ws.freeze_panes = "A2"
    _autosize(ws, {1: 24, 2: 18, 3: 22, 4: 48, 5: 15, 6: 16, 7: 12})
    return wb


def _strand_summary_to_xlsx(payload: StrandSummaryPayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "Strand Summary")
    headers = [
        "Strand",
        "Standards",
        "Questions",
        "Grade Average %",
        "% Incorrect",
    ]
    _write_header(ws, 1, headers)
    r = 2
    for s in payload.strands_rollup:
        _txt_cell(ws, r, 1, s.strand)
        _txt_cell(ws, r, 2, s.num_standards, align=_CENTER)
        _txt_cell(ws, r, 3, s.num_questions, align=_CENTER)
        _pct_cell(ws, r, 4, s.grade_average, fill=_perf_fill(s.grade_average))
        _pct_cell(ws, r, 5, s.incorrect_pct)
        r += 1
    ws.freeze_panes = "A2"
    _autosize(ws, {1: 32, 2: 12, 3: 12, 4: 16, 5: 12})
    return wb


def _sdd_to_xlsx(payload: StandardsDeepDivePayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "Standards Deep Dive")
    headers = ["Standard", "Strand", "Questions", "Grade Average %"]
    _write_header(ws, 1, headers)
    r = 2
    for s in payload.standards_rollup:
        _txt_cell(ws, r, 1, s.schoology_standard)
        _txt_cell(ws, r, 2, s.strand)
        _txt_cell(ws, r, 3, s.num_questions, align=_CENTER)
        # null grade_average renders BLANK (unassessed alias), per SddStandardRow.
        _pct_cell(ws, r, 4, s.grade_average, fill=_perf_fill(s.grade_average))
        r += 1
    ws.freeze_panes = "A2"
    _autosize(ws, {1: 32, 2: 22, 3: 12, 4: 16})
    return wb


# ─── IAD: distractor block + student-attempt block ───────────────────────────


def _iad_to_xlsx(payload: IncorrectAnswerDetailsPayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "Incorrect Answer Details")

    _txt_cell(ws, 1, 1, "Distractors", bold=True)
    _write_header(ws, 2, ["Answer", "# Students", "% of Attempts", "Correct?"])
    r = 3
    for d in payload.distractors:
        _txt_cell(ws, r, 1, _plain(d.answer_submission))
        _txt_cell(ws, r, 2, d.students_count, align=_CENTER)
        _pct_cell(ws, r, 3, d.share_of_attempts)
        _txt_cell(ws, r, 4, "Yes" if d.is_correct else "No", align=_CENTER)
        r += 1

    r += 1
    _txt_cell(ws, r, 1, "Student Attempts", bold=True)
    r += 1
    _write_header(ws, r, ["Student", "Answer", "Correct Answer", "Correct?", "Score %"])
    r += 1
    for a in payload.student_attempts:
        _txt_cell(ws, r, 1, a.user_name)
        _txt_cell(ws, r, 2, _plain(a.answer_submission))
        _txt_cell(ws, r, 3, _plain(a.correct_answer))
        _txt_cell(ws, r, 4, "Yes" if a.is_correct else "No", align=_CENTER)
        _pct_cell(ws, r, 5, a.score_pct, fill=_perf_fill(a.score_pct))
        r += 1

    _autosize(ws, {1: 36, 2: 12, 3: 22, 4: 10, 5: 10})
    return wb


# ─── Registry + dispatch ─────────────────────────────────────────────────────

_BUILDERS = {
    "qra": _qra_to_xlsx,
    "qra-paginated": _qra_paginated_to_xlsx,
    "qra-by-teacher": _qra_by_teacher_to_xlsx,
    "qra-by-standard-teacher": _qra_by_standard_teacher_to_xlsx,
    "qsr": _qsr_to_xlsx,
    "ytd": _ytd_to_xlsx,
    "standard-summary": _standard_summary_to_xlsx,
    "strand-summary": _strand_summary_to_xlsx,
    "sdd": _sdd_to_xlsx,
    "iad": _iad_to_xlsx,
}


def report_to_xlsx(kind: str, payload: Any) -> Workbook:
    """Serialize a composed report payload to an :class:`openpyxl.Workbook`."""
    builder = _BUILDERS.get(kind)
    if builder is None:
        raise ValueError(f"Unsupported report kind: {kind!r}")
    return builder(payload)


def workbook_to_bytes(wb: Workbook) -> bytes:
    """Save a workbook to an in-memory ``bytes`` buffer for streaming."""
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─── Filename sanitization (Content-Disposition header injection guard) ──────


def sanitize_xlsx_filename(report: str, item_name: Optional[str]) -> str:
    """Build a safe ``attachment`` filename from the report + item name.

    Strips CR/LF/quotes/backslashes and other control chars that could break
    out of the ``Content-Disposition`` header, collapses whitespace to ``-``,
    and caps the length.
    """
    base = (item_name or report or "report").strip()
    cleaned = []
    for ch in base:
        if ch in '\r\n"\\;,:/?*[]<>|':
            cleaned.append("-")
        elif ord(ch) < 32:
            cleaned.append("-")
        else:
            cleaned.append(ch)
    safe = "".join(cleaned)
    # Collapse runs of whitespace / dashes.
    out: list[str] = []
    prev_dash = False
    for ch in safe:
        if ch.isspace() or ch == "-":
            if not prev_dash:
                out.append("-")
            prev_dash = True
        else:
            out.append(ch)
            prev_dash = False
    name = "".join(out).strip("-")[:96] or "report"
    return f"{report}-{name}.xlsx"
