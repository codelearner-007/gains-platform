"""Tests for the server-side XLSX export routes (Phase B / B2+B3).

Exercises the per-report ``export.xlsx`` endpoints through the HTTP layer
(same ``reports:read`` + RLS scoping as the JSON siblings), re-opens the
streamed bytes with openpyxl, and asserts the structure the report-export
service is supposed to produce: bold frozen headers, performance fills equal
to the ``colors.ts`` hex, freeze panes, and values matching the payload.
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook

from app.schemas.reports import (
    QuestionResponseAnalysisPayload,
    StandardSummaryPayload,
)
from app.services import report_export_service as X

_XLSX_MEDIA = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_CHAPTER9 = "8359960427"


def _load(content: bytes):
    return load_workbook(io.BytesIO(content))


@pytest.mark.anyio
async def test_qra_export_xlsx_structure_and_fills(
    admin_client: AsyncClient,
) -> None:
    # Fetch the JSON payload so we can compare cell values.
    j = await admin_client.get(
        f"/api/v1/reports/question-response-analysis/{_CHAPTER9}"
    )
    if j.status_code == 404:
        pytest.skip("Chapter 9 fixture item missing")
    payload = QuestionResponseAnalysisPayload.model_validate(j.json())

    r = await admin_client.get(
        f"/api/v1/reports/question-response-analysis/{_CHAPTER9}/export.xlsx"
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(_XLSX_MEDIA)
    cd = r.headers["content-disposition"]
    assert cd.startswith("attachment; filename=")
    # No CR/LF/quote injection survived into the header.
    assert "\r" not in cd and "\n" not in cd

    wb = _load(r.content)
    ws = wb.active
    assert ws.title == "QRA"
    assert [ws.cell(1, c).value for c in range(1, 9)] == X._QRA_HEADERS
    assert ws.cell(1, 1).font.bold is True
    assert ws.cell(1, 1).fill.fgColor.rgb == X.HEADER_BAR_BG
    assert ws.freeze_panes == "A2"
    assert ws.max_row == len(payload.questions_overall) + 1

    q0 = payload.questions_overall[0]
    cell = ws.cell(2, 5)  # Grade Average %
    assert cell.value == pytest.approx(q0.grade_average)
    assert cell.number_format == "0.0%"
    expected = (
        X.PERF_PINK
        if q0.grade_average < 0.7
        else X.PERF_YELLOW
        if q0.grade_average < 0.8
        else X.PERF_GREEN
    )
    assert cell.fill.fgColor.rgb == expected


@pytest.mark.anyio
async def test_qsr_export_xlsx_partial_credit_ssrs_parity(
    admin_client: AsyncClient,
) -> None:
    """The QSR .xlsx mirrors the legacy SSRS partial-credit layout exactly.

    Cells carry fractional ``points_received``, "# Correct Answers" sums
    points, and every Score% is SUM(received)/SUM(possible). The legacy
    Chapter 9 Test 8359960427 grand totals are 318 / 486 / 65.4%.

    The web/JSON QSR endpoint now serves the SAME partial-credit payload as
    the xlsx (single source of truth), so we anchor the leaf-column order on
    that payload while asserting the values come straight from the workbook.
    """
    j = await admin_client.get(
        f"/api/v1/reports/question-summary-paginated/{_CHAPTER9}"
    )
    if j.status_code == 404:
        pytest.skip("Chapter 9 fixture item missing")
    from app.schemas.reports import QuestionSummaryPointsPayload

    count_payload = QuestionSummaryPointsPayload.model_validate(j.json())
    question_nos = [q.question_no for q in count_payload.questions]

    # The web/JSON QSR grand total is partial-credit and equals the grade-
    # average KPI: 318 / 486 = 65.4% (NOT the old binary 308 / 63.4%).
    assert count_payload.grand_total.correct_count == pytest.approx(318, abs=0.5)
    assert count_payload.grand_total.possible_points == pytest.approx(486, abs=0.5)
    assert count_payload.grand_total.score_pct == pytest.approx(318 / 486, abs=1e-3)

    r = await admin_client.get(
        f"/api/v1/reports/question-summary-paginated/{_CHAPTER9}/export.xlsx"
    )
    assert r.status_code == 200, r.text
    wb = _load(r.content)
    ws = wb.active
    assert ws.title == "Paginated - Question Summary Re"

    # SSRS title block (rows 2 / 4 / 6) + freeze A8.
    assert ws.cell(2, 1).value == "Question Summary Report"
    assert ws.cell(2, 1).font.size == 20
    assert ws.freeze_panes == "A8"
    assert count_payload.assessment.item_name in (ws.cell(6, 3).value or "")

    # Header rows 8/9: navy band header + leaf question_no order, with a
    # grey "Score %" sub-column at the end of every band.
    assert ws.cell(8, 1).value == "Classroom Instructors"
    assert ws.cell(8, 1).fill.fgColor.rgb == X.QSR_NAVY
    assert ws.cell(8, 5).value == "Score %"
    leaf_cols = [
        c
        for c in range(6, ws.max_column - 1)
        if str(ws.cell(9, c).value or "").isdigit()
    ]
    assert [ws.cell(9, c).value for c in leaf_cols] == question_nos
    assert ws.cell(8, ws.max_column - 1).value == "Possible Points"
    assert ws.cell(8, ws.max_column).value == "# Correct Answers"
    # A band Score% sub-column exists and is grey C0C0C0 (not perf-banded).
    score_cols = [
        c for c in range(6, ws.max_column - 1) if ws.cell(9, c).value == "Score %"
    ]
    assert score_cols
    assert ws.cell(10, score_cols[0]).fill.fgColor.rgb == X.QSR_GREY_SCORE
    assert ws.cell(10, score_cols[0]).number_format == "[$-010409]0%"

    # Overall Score% (col E) is a 0–1 fraction, perf-banded, locale percent fmt.
    e0 = ws.cell(10, 5)
    assert isinstance(e0.value, float) and 0.0 <= e0.value <= 1.0
    assert e0.number_format == "[$-010409]0%"
    assert e0.fill.fgColor.rgb in (X.QSR_PINK, X.QSR_YELLOW_XLSX, X.QSR_GREEN)

    # Body leaf cells carry raw (possibly fractional) points; <0.5 pink, else
    # green. Chapter 9 has partial-credit questions → at least one fraction.
    saw_fraction = False
    for c in leaf_cols:
        v = ws.cell(10, c).value
        if v is None:
            continue
        assert ws.cell(10, c).fill.fgColor.rgb == (
            X.QSR_GREEN if v >= 0.5 else X.QSR_PINK
        )
        if v not in (0, 1):
            saw_fraction = True
    assert saw_fraction

    # Instructor block (col A) carries the overall % and the grand-total trio
    # sits at the foot with SUMMED points (Possible 486 / # Correct 318).
    assert "%" in str(ws.cell(10, 1).value)
    labels = [ws.cell(ws.max_row - 2 + k, 1).value for k in range(3)]
    assert labels == ["Possible Points", "# Correct Answers", "Score %"]
    assert ws.cell(ws.max_row - 2, 5).value == pytest.approx(486)
    assert ws.cell(ws.max_row - 1, 5).value == pytest.approx(318)
    assert ws.cell(ws.max_row, 5).value == pytest.approx(318 / 486, abs=1e-4)


@pytest.mark.anyio
async def test_standard_summary_export_xlsx(admin_client: AsyncClient) -> None:
    j = await admin_client.get("/api/v1/reports/standard-summary")
    assert j.status_code == 200, j.text
    payload = StandardSummaryPayload.model_validate(j.json())

    r = await admin_client.get("/api/v1/reports/standard-summary/export.xlsx")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(_XLSX_MEDIA)
    wb = _load(r.content)
    ws = wb.active
    assert ws.freeze_panes == "A2"
    assert ws.cell(1, 1).value == "Standard"
    assert ws.max_row == len(payload.standards) + 1
    if payload.standards:
        s0 = payload.standards[0]
        assert ws.cell(2, 1).value == s0.schoology_standard
        cell = ws.cell(2, 7)  # Grade Average %
        assert cell.value == pytest.approx(s0.grade_average)


@pytest.mark.anyio
async def test_export_xlsx_requires_reports_read(
    user_client: AsyncClient,
) -> None:
    r = await user_client.get(
        f"/api/v1/reports/question-response-analysis/{_CHAPTER9}/export.xlsx"
    )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_export_xlsx_unknown_item_404(admin_client: AsyncClient) -> None:
    r = await admin_client.get(
        "/api/v1/reports/question-response-analysis/0000000000/export.xlsx"
    )
    assert r.status_code == 404


def test_perf_and_qsr_fill_hex_match_colors_ts() -> None:
    """The XLSX fill hexes MUST equal the colors.ts literals (trailing 6 chars).

    Guards against drift between the exporter palette and the single source of
    truth in ``frontend/src/lib/reports/colors.ts``.
    """
    import pathlib
    import re

    colors_ts = pathlib.Path(__file__).resolve().parents[3] / (
        "frontend/src/lib/reports/colors.ts"
    )
    text = colors_ts.read_text()

    def literal(name: str) -> str:
        m = re.search(rf"export const {name} = '#([0-9A-Fa-f]{{6}})'", text)
        assert m, f"{name} not found in colors.ts"
        return m.group(1).upper()

    assert X.PERF_PINK[2:] == literal("PERF_PINK")
    assert X.PERF_YELLOW[2:] == literal("PERF_YELLOW")
    assert X.PERF_GREEN[2:] == literal("PERF_GREEN")
    assert X.QSR_PINK[2:] == literal("QSR_PINK")
    assert X.QSR_YELLOW[2:] == literal("QSR_YELLOW")
    assert X.QSR_GREEN[2:] == literal("QSR_GREEN")
    assert X.HEADER_BAR_BG[2:] == literal("HEADER_BAR_BG")
    assert X.LAYOUT_BORDER[2:] == literal("LAYOUT_BORDER")
    assert X.PBIX_ACCENT_NAVY[2:] == literal("PBIX_ACCENT_NAVY")


def test_sanitize_xlsx_filename_strips_header_injection() -> None:
    bad = 'Chapter\r\n9 "Test"/<x>'
    out = X.sanitize_xlsx_filename("qra", bad)
    assert out.endswith(".xlsx")
    assert "\r" not in out and "\n" not in out and '"' not in out
    assert "/" not in out
    assert out.startswith("qra-")
    # Empty / None item name falls back to the report kind.
    assert X.sanitize_xlsx_filename("qsr", None) == "qsr-qsr.xlsx"
