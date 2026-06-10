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

from app.schemas.reports import (
    IncorrectAnswerDetailsPayload,
    QraByStandardTeacherPayload,
    QraByTeacherPayload,
    QraPaginatedPayload,
    QuestionResponseAnalysisPayload,
    QuestionSummaryMatrixPayload,
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
# Chrome:
HEADER_BAR_BG = "FFB8DBFF"  # colors.ts HEADER_BAR_BG #B8DBFF
LAYOUT_BORDER = "FFB3B3B3"  # colors.ts LAYOUT_BORDER #B3B3B3
INCORRECT_GREY = "FFCCCCCC"  # colors.ts INCORRECT_GREY #CCCCCC
PBIX_ACCENT_NAVY = "FF4472C4"  # colors.ts PBIX_ACCENT_NAVY #4472C4

# PBIX-mandated band thresholds (mirror report_service / colors.ts).
_BAND_HIGH = 0.8
_BAND_MID = 0.7

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


# ─── QSR: student × question matrix, standard column bands ───────────────────


def _qsr_to_xlsx(payload: QuestionSummaryMatrixPayload) -> Workbook:
    """Student × question binary matrix, columns grouped into standard bands.

    Layout (mirrors the on-screen QuestionSummaryMatrix + the legacy SSRS
    xlsx column semantics):

      Row 1 (band header, navy): "Standards" | <cpalms band, merged> … | "Totals"
      Row 2 (col header, navy):  Classroom Instructors | Student Name | Score %
                                 | <question_no per leaf> | Possible Points
                                 | # Correct Answers
      Body: one row per (teacher → student); the Score % cell + each 0/1
            question cell carry the QSR_* fill; binary 1 cells green, 0 pink.
      Footer trio (grey): Possible Points / # Correct Answers / Score % grand
            totals, with the Score % row's per-question cells QSR-banded.
    """
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "Question Summary")

    questions = payload.questions
    # Contiguous standard bands over the (already standard-sorted) question list.
    bands: list[tuple[str, int]] = []
    for q in questions:
        code = q.cpalms_standard or q.standard or "Other"
        if bands and bands[-1][0] == code:
            bands[-1] = (code, bands[-1][1] + 1)
        else:
            bands.append((code, 1))

    n_q = len(questions)
    first_q_col = 4  # A=Instructor, B=Student, C=Score %, then leaf q columns
    last_q_col = first_q_col + n_q - 1
    possible_col = last_q_col + 1
    correct_col = last_q_col + 2

    # ── Row 1: band header ──────────────────────────────────────────────────
    c = ws.cell(row=1, column=1, value="Standards")
    c.fill = _NAVY_FILL
    c.font = _HEADER_FONT_WHITE
    c.alignment = _LEFT
    c.border = _BORDER
    if first_q_col > 3:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3)
        for col in (2, 3):
            ws.cell(row=1, column=col).fill = _NAVY_FILL
            ws.cell(row=1, column=col).border = _BORDER
    col = first_q_col
    for code, span in bands:
        bc = ws.cell(row=1, column=col, value=code)
        bc.fill = _NAVY_FILL
        bc.font = _HEADER_FONT_WHITE
        bc.alignment = _CENTER
        bc.border = _BORDER
        if span > 1:
            ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + span - 1)
            for k in range(col + 1, col + span):
                ws.cell(row=1, column=k).fill = _NAVY_FILL
                ws.cell(row=1, column=k).border = _BORDER
        col += span
    tot = ws.cell(row=1, column=possible_col, value="Totals")
    tot.fill = _NAVY_FILL
    tot.font = _HEADER_FONT_WHITE
    tot.alignment = _CENTER
    tot.border = _BORDER
    ws.merge_cells(start_row=1, start_column=possible_col, end_row=1, end_column=correct_col)
    ws.cell(row=1, column=correct_col).fill = _NAVY_FILL
    ws.cell(row=1, column=correct_col).border = _BORDER

    # ── Row 2: column header ────────────────────────────────────────────────
    header = ["Classroom Instructors", "Student Name", "Score %"]
    header += [q.question_no for q in questions]
    header += ["Possible Points", "# Correct Answers"]
    _write_header(ws, 2, header, fill=_NAVY_FILL, white=True)

    # ── Body ────────────────────────────────────────────────────────────────
    r = 3
    for g in payload.teacher_groups:
        for idx, s in enumerate(g.students):
            _txt_cell(ws, r, 1, g.section_instructor if idx == 0 else "", bold=(idx == 0))
            if idx == 0:
                ws.cell(row=r, column=1).fill = _HEADER_FILL
            _txt_cell(ws, r, 2, s.user_name)
            _pct_cell(ws, r, 3, s.score_pct, fill=_qsr_fill(s.score_pct), fmt=_PCT_FMT_INT)
            for qi, q in enumerate(questions):
                cell_val = s.cells.get(q.question_id)
                cc = ws.cell(row=r, column=first_q_col + qi)
                cc.alignment = _CENTER
                cc.border = _BORDER
                if cell_val == 1:
                    cc.value = 1
                    cc.fill = PatternFill("solid", fgColor=QSR_GREEN)
                elif cell_val == 0:
                    cc.value = 0
                    cc.fill = PatternFill("solid", fgColor=QSR_PINK)
                else:
                    cc.value = None
            _txt_cell(ws, r, possible_col, s.possible_points, align=_RIGHT)
            _txt_cell(ws, r, correct_col, s.correct_count, align=_RIGHT)
            r += 1
        # Per-teacher subtotal: Score % row only (mirrors the on-screen "Score %"
        # subtotal band for the teacher group).
        _txt_cell(ws, r, 1, f"Subtotal: {g.section_instructor}", bold=True)
        ws.cell(row=r, column=1).fill = _HEADER_FILL
        _txt_cell(ws, r, 2, "")
        _pct_cell(ws, r, 3, g.teacher_score_pct, fill=_qsr_fill(g.teacher_score_pct), fmt=_PCT_FMT_INT)
        ws.cell(row=r, column=3).font = _BOLD
        r += 1

    # ── Grand-total trio (Possible Points / # Correct Answers / Score %) ─────
    gt = payload.grand_total
    # Possible Points
    _txt_cell(ws, r, 1, "Possible Points", bold=True)
    ws.cell(row=r, column=1).fill = _GREY_FILL
    _txt_cell(ws, r, 3, gt.possible_points, align=_RIGHT, bold=True)
    for qi, q in enumerate(questions):
        _txt_cell(ws, r, first_q_col + qi, gt.per_question_possible.get(q.question_id, 0), align=_CENTER)
    _txt_cell(ws, r, possible_col, gt.possible_points, align=_RIGHT, bold=True)
    r += 1
    # # Correct Answers
    _txt_cell(ws, r, 1, "# Correct Answers", bold=True)
    ws.cell(row=r, column=1).fill = _GREY_FILL
    _txt_cell(ws, r, 3, gt.correct_count, align=_RIGHT, bold=True)
    for qi, q in enumerate(questions):
        _txt_cell(ws, r, first_q_col + qi, gt.per_question_correct.get(q.question_id, 0), align=_CENTER)
    _txt_cell(ws, r, correct_col, gt.correct_count, align=_RIGHT, bold=True)
    r += 1
    # Score %
    _txt_cell(ws, r, 1, "Score %", bold=True)
    ws.cell(row=r, column=1).fill = _GREY_FILL
    _pct_cell(ws, r, 3, gt.score_pct, fill=_qsr_fill(gt.score_pct), fmt=_PCT_FMT_INT)
    ws.cell(row=r, column=3).font = _BOLD
    for qi, q in enumerate(questions):
        p = gt.per_question_pct.get(q.question_id, 0.0)
        _pct_cell(ws, r, first_q_col + qi, p, fill=_qsr_fill(p), fmt=_PCT_FMT_INT)
    r += 1

    ws.freeze_panes = ws.cell(row=3, column=first_q_col).coordinate
    widths = {1: 22, 2: 22, 3: 9}
    for qi in range(n_q):
        widths[first_q_col + qi] = 5
    widths[possible_col] = 15
    widths[correct_col] = 16
    _autosize(ws, widths)
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
        "Assessments",
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
        _txt_cell(ws, r, 6, s.num_assessments, align=_CENTER)
        _pct_cell(ws, r, 7, s.grade_average, fill=_perf_fill(s.grade_average))
        _pct_cell(ws, r, 8, 1 - s.grade_average)
        r += 1
    ws.freeze_panes = "A2"
    _autosize(ws, {1: 24, 2: 18, 3: 22, 4: 48, 5: 15, 6: 13, 7: 16, 8: 12})
    return wb


def _strand_summary_to_xlsx(payload: StrandSummaryPayload) -> Workbook:
    wb = Workbook()
    ws = wb.active
    _set_title(ws, "Strand Summary")
    headers = [
        "Strand",
        "Standards",
        "Questions",
        "Assessments",
        "Grade Average %",
        "% Incorrect",
    ]
    _write_header(ws, 1, headers)
    r = 2
    for s in payload.strands_rollup:
        _txt_cell(ws, r, 1, s.strand)
        _txt_cell(ws, r, 2, s.num_standards, align=_CENTER)
        _txt_cell(ws, r, 3, s.num_questions, align=_CENTER)
        _txt_cell(ws, r, 4, s.num_assessments, align=_CENTER)
        _pct_cell(ws, r, 5, s.grade_average, fill=_perf_fill(s.grade_average))
        _pct_cell(ws, r, 6, s.incorrect_pct)
        r += 1
    ws.freeze_panes = "A2"
    _autosize(ws, {1: 32, 2: 12, 3: 12, 4: 13, 5: 16, 6: 12})
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
