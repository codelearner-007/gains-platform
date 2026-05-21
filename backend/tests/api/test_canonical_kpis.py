"""Regression tests for the canonical, source-of-truth KPI helper.

These tests pin hard expected values for two specific assessments in the
local pipeline-seeded DB so that QRA, SDD, and any future per-assessment
report cannot silently drift from the legacy PBIX DAX semantics.

The contract being defended (see
``.hermes/report-parity/FRESH-RCA-2026-05-18-stable-formulas.md`` §4):

* ``total_students``  — exact match to ``cube_school_summary``.
* ``total_questions`` — exact ``DISTINCTCOUNT(question_no)`` over the
  per-(user, question) collapsed fact (matches legacy
  ``DISTINCTCOUNT(cqso[Question_No])``).
* ``total_standards`` — exact ``COUNT(DISTINCT standard)`` over
  ``dim_question_data`` for the item — matches legacy
  ``DISTINCTCOUNT(cqso[Standards])`` which counts raw long-form labels.
* ``grade_average / grade_min / grade_max`` — per-(user, question)
  collapsed grades averaged per question, then AVG / MIN / MAX across
  questions. Mirrors legacy ``AVERAGE / MAXX / MINX VALUES(Question_No)``.
* ``standards_rollup`` row count — equals legacy
  ``DISTINCTCOUNT(standards_val)`` after the chain restriction.

Two fixture items are pinned:

* ``8359960427`` (Chapter 9 Test — MJ Algebra 3rd Period, Athenian):
  legacy 27 students / 18 questions / 12 standards / 66.9% avg / 96.1%
  high / 28.9% low. Modern target after fix: 27 / 18 / **12** /
  ~65.4% / ~96.3% / ~27.8%. Residual percentage gaps vs legacy are
  documented snapshot drift (legacy CQSO holds Schoology's 2-decimal
  truncated ``average_points_earned`` values; current raw is fresh).

* ``7892351049`` (single-strand control). Used to assert single-strand
  assessments still render cleanly post-fix and that the rollup is
  symmetric.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.reports import (
    QuestionResponseAnalysisPayload,
    StandardsDeepDivePayload,
)


_CHAPTER9_ITEM_ID = "8359960427"
_CONTROL_ITEM_ID = "7892351049"


async def _get_qra(client: AsyncClient, item_id: str) -> QuestionResponseAnalysisPayload:
    response = await client.get(
        f"/api/v1/reports/question-response-analysis/{item_id}"
    )
    if response.status_code == 404:
        pytest.skip(f"Item {item_id} missing — pipeline not seeded for this DB.")
    assert response.status_code == 200, response.text
    return QuestionResponseAnalysisPayload.model_validate(response.json())


async def _get_sdd(client: AsyncClient, item_id: str) -> StandardsDeepDivePayload:
    response = await client.get(
        f"/api/v1/reports/standards-deep-dive/{item_id}"
    )
    if response.status_code == 404:
        pytest.skip(f"Item {item_id} missing — pipeline not seeded for this DB.")
    assert response.status_code == 200, response.text
    return StandardsDeepDivePayload.model_validate(response.json())


@pytest.mark.anyio
async def test_canonical_kpis_chapter9_counts_exact(
    admin_client: AsyncClient,
) -> None:
    """KPI counts must exactly match the legacy PBIX values for Chapter 9 Test.

    These are the values teachers can directly verify in the embedded
    legacy Schoology dashboard. ``total_standards`` was previously 8
    (identifier-grain dedupe); the canonical helper now reports 12
    (legacy raw-label grain).
    """
    qra = await _get_qra(admin_client, _CHAPTER9_ITEM_ID)

    assert qra.kpis.total_students == 27, (
        f"Total Students must equal legacy 27, got {qra.kpis.total_students}"
    )
    assert qra.kpis.total_questions == 18, (
        f"Total Questions must equal legacy 18, got {qra.kpis.total_questions}"
    )
    assert qra.kpis.total_standards == 12, (
        f"Total Standards must equal legacy 12 — counts raw standards_val "
        f"labels per DAX DISTINCTCOUNT(cqso[Standards]) — got "
        f"{qra.kpis.total_standards} (8 = pre-fix identifier-grain)"
    )


@pytest.mark.anyio
async def test_canonical_kpis_chapter9_percentages_within_legacy_band(
    admin_client: AsyncClient,
) -> None:
    """Grade Average / Highest / Lowest sit within the legacy ±2pp band.

    Legacy reported 66.9% / 96.1% / 28.9%. The canonical formula
    computes per-(user, question) collapsed grades and reports ~65.4%
    avg / ~96.3% high / ~27.8% low. The ≤2pp gap on grade_average is
    documented data-snapshot drift (legacy CQSO holds Schoology's
    2-decimal pre-rounded ``average_points_earned`` values; current
    raw is fresh and may have one or two row counts shifted).
    """
    qra = await _get_qra(admin_client, _CHAPTER9_ITEM_ID)

    assert 0.63 <= qra.kpis.grade_average <= 0.68, (
        f"Grade Average must sit within legacy ±2pp band (legacy 0.669), "
        f"got {qra.kpis.grade_average}"
    )
    assert 0.95 <= qra.kpis.grade_max <= 0.97, (
        f"Overall Highest must match legacy 96.1% within Schoology "
        f"2-decimal truncation, got {qra.kpis.grade_max}"
    )
    assert 0.26 <= qra.kpis.grade_min <= 0.30, (
        f"Overall Lowest must match legacy 28.9% within rounding/grain, "
        f"got {qra.kpis.grade_min}"
    )


@pytest.mark.anyio
async def test_canonical_kpis_qra_sdd_parity_chapter9(
    admin_client: AsyncClient,
) -> None:
    """QRA and SDD must report IDENTICAL KPI values for the same item.

    This is the central guarantee of the canonical helper. Any divergence
    here means the helper is bypassed or QRA / SDD diverged in service.
    """
    qra = await _get_qra(admin_client, _CHAPTER9_ITEM_ID)
    sdd = await _get_sdd(admin_client, _CHAPTER9_ITEM_ID)

    assert qra.kpis.total_students == sdd.kpis.total_students, (
        f"QRA total_students {qra.kpis.total_students} != "
        f"SDD total_students {sdd.kpis.total_students}"
    )
    assert qra.kpis.total_questions == sdd.kpis.total_questions, (
        f"QRA total_questions {qra.kpis.total_questions} != "
        f"SDD total_questions {sdd.kpis.total_questions}"
    )
    assert qra.kpis.total_standards == sdd.kpis.total_standards, (
        f"QRA total_standards {qra.kpis.total_standards} != "
        f"SDD total_standards {sdd.kpis.total_standards}"
    )
    assert round(qra.kpis.grade_average, 6) == round(sdd.kpis.grade_average, 6), (
        f"QRA grade_average {qra.kpis.grade_average} != "
        f"SDD grade_average {sdd.kpis.grade_average}"
    )
    assert qra.kpis.grade_average_pct == sdd.kpis.grade_average_pct, (
        f"QRA grade_average_pct {qra.kpis.grade_average_pct} != "
        f"SDD grade_average_pct {sdd.kpis.grade_average_pct}"
    )


@pytest.mark.anyio
async def test_canonical_standards_rollup_chapter9_exact_12_rows(
    admin_client: AsyncClient,
) -> None:
    """Standards rollup table must render 12 Schoology canonical standards.

    Schoology emits 12 distinct standards (its raw long form) across
    Chapter 9 Test. The exact-match join in get_standard_rollup_for_item
    surfaces each of them as its own row; row count = 12.
    """
    sdd = await _get_sdd(admin_client, _CHAPTER9_ITEM_ID)

    assert len(sdd.standards_rollup) == 12, (
        f"Standards rollup must have exactly 12 rows (Schoology parity), "
        f"got {len(sdd.standards_rollup)}: "
        f"{[r.schoology_standard for r in sdd.standards_rollup]}"
    )

    schoology = {r.schoology_standard for r in sdd.standards_rollup}
    # The 12 Schoology canonical codes Schoology emits for Chapter 9.
    expected_schoology = {
        "MA.9-12.MAFS.912.A-CED.1.1",
        "AI.MA.912.AR.1.7",
        "AI.MA.912.AR.3.1",
        "MA.912.AR.1.2",
        "MA.912.AR.1.7",
        "MA.912.AR.3.1",
        "MA.9-12.MAFS.912.A-REI.2.4.a",
        "MA.9-12.MAFS.912.A-REI.2.4.b",
        "MA.9-12.MAFS.912.N-Q.1.3",
        "MA.9-12.MAFS.912.N-RN.1.2",
        "AI.MA.912.NSO.1.4",
        "MA.912.NSO.1.4",
    }
    assert schoology == expected_schoology, (
        f"Standards rollup Schoology set drifted from expected 12. "
        f"Missing: {expected_schoology - schoology}. Extra: {schoology - expected_schoology}."
    )


@pytest.mark.anyio
async def test_canonical_strands_rollup_chapter9_exact_6_strands(
    admin_client: AsyncClient,
) -> None:
    """Strand rollup must render the legacy 6 strands.

    Pre-fix this was already 6 (post-recursive-chain) but we re-assert
    after the chain restriction to ensure parity wasn't lost.
    """
    sdd = await _get_sdd(admin_client, _CHAPTER9_ITEM_ID)

    assert len(sdd.strands_rollup) == 6, (
        f"Strand rollup must have exactly 6 rows (legacy parity), "
        f"got {len(sdd.strands_rollup)}: "
        f"{[r.strand for r in sdd.strands_rollup]}"
    )


@pytest.mark.anyio
async def test_canonical_strand_num_standards_matches_table_grain(
    admin_client: AsyncClient,
) -> None:
    """Per-strand ``num_standards`` must sum to the school-level KPI.

    Bug fix (2026-05-19): pre-fix
    ``get_strand_rollup_for_item`` counted ``DISTINCT identifier`` per
    strand. Florida CPALMS deliberately maps multiple raw label aliases
    (e.g. ``MA.912.AR.3.1`` ↔ ``AI.MA.912.AR.3.1`` ↔ ``AR.3.1``) to the
    same ``dim_standard.identifier`` UUID, so identifier-grain counting
    understated each strand's "# of Standards" column. For
    ``8359960427`` the strand column summed to 8 while
    ``kpis.total_standards = 12`` and the standards rollup table
    rendered 12 rows — an internal contradiction.

    The fix counts ``DISTINCT schoology_standard`` per strand from the
    same ``labeled`` CTE that drives the standards rollup, guaranteeing
    the strand column always sums to the standards-table row count and
    the school-level KPI.
    """
    sdd = await _get_sdd(admin_client, _CHAPTER9_ITEM_ID)

    # Structural: strand sum == standards table count == KPI.
    sum_per_strand = sum(s.num_standards for s in sdd.strands_rollup)
    assert sum_per_strand == len(sdd.standards_rollup), (
        f"sum(strand.num_standards) = {sum_per_strand} must equal "
        f"len(standards_rollup) = {len(sdd.standards_rollup)} — strand "
        f"column and standards table disagree on visible standard count."
    )
    assert sum_per_strand == sdd.kpis.total_standards, (
        f"sum(strand.num_standards) = {sum_per_strand} must equal "
        f"kpis.total_standards = {sdd.kpis.total_standards} — strand "
        f"column and KPI tile disagree."
    )
    assert sum_per_strand == 12, (
        f"Schoology parity: total_standards should be 12, "
        f"got {sum_per_strand}."
    )

    # Per-strand pin (Schoology-standard grain from the labeled CTE).
    expected_per_strand = {
        "Algebra: Creating Equations": 1,                      # MA.9-12.MAFS.912.A-CED.1.1
        "Algebra: Reasoning with Equations & Inequalities": 2, # MA.9-12.MAFS.912.A-REI.2.4.{a,b}
        "Algebraic Reasoning": 5,                              # AI.MA.912.AR.{1.7,3.1} + MA.912.AR.{1.2,1.7,3.1}
        "Number & Quantity: Quantities": 1,                    # MA.9-12.MAFS.912.N-Q.1.3
        "Number & Quantity: The Real Number System": 1,        # MA.9-12.MAFS.912.N-RN.1.2
        "Number Sense and Operations": 2,                      # AI.MA.912.NSO.1.4 + MA.912.NSO.1.4
    }
    actual_per_strand = {s.strand: s.num_standards for s in sdd.strands_rollup}
    assert actual_per_strand == expected_per_strand, (
        f"Per-strand num_standards drifted from Schoology grain.\n"
        f"Expected: {expected_per_strand}\nActual: {actual_per_strand}"
    )


@pytest.mark.anyio
async def test_canonical_qra_strand_num_standards_matches_sdd(
    admin_client: AsyncClient,
) -> None:
    """QRA and SDD must agree on per-strand num_standards.

    Both reports consume ``_build_strand_standard_rollups`` which calls
    the same ``get_strand_rollup_for_item`` repo method. Asserts the
    structural guarantee that a future divergence between the two
    reports' strand tables is caught.
    """
    qra = await _get_qra(admin_client, _CHAPTER9_ITEM_ID)
    sdd = await _get_sdd(admin_client, _CHAPTER9_ITEM_ID)

    qra_per_strand = {s.strand: s.num_standards for s in qra.strands_rollup}
    sdd_per_strand = {s.strand: s.num_standards for s in sdd.strands_rollup}
    assert qra_per_strand == sdd_per_strand, (
        f"QRA and SDD strand num_standards diverged.\n"
        f"QRA: {qra_per_strand}\nSDD: {sdd_per_strand}"
    )


@pytest.mark.anyio
async def test_canonical_per_question_q12_matches_kpi_lowest(
    admin_client: AsyncClient,
) -> None:
    """Q12 in the per-question table must match the canonical KPI Lowest.

    Q12 is a multi-select question whose ``cube_question_summary`` row
    has ``total_score=35 / total_possible_point=146 = 23.97%`` due to
    multi-position fan-out. The canonical per-question grade collapses
    to per-student first → 27.78% — same grain as the KPI Lowest. If
    these disagree, the KPI strip and the question table render
    contradictory percentages for the same question.
    """
    qra = await _get_qra(admin_client, _CHAPTER9_ITEM_ID)

    q12 = next(
        (q for q in qra.questions_overall if q.question_no == "12"),
        None,
    )
    assert q12 is not None, "Q12 missing from questions_overall"
    # Lowest KPI grain ≈ 0.278; per-question grain must agree.
    assert 0.26 <= q12.grade_average <= 0.30, (
        f"Q12 grade_average must match the canonical Lowest KPI grain "
        f"(0.278 ± 0.02), got {q12.grade_average}. If this is 0.24, "
        f"the per-question table is using cube row-grain SUM/SUM "
        f"instead of the canonical per-user collapse."
    )


@pytest.mark.anyio
async def test_canonical_per_question_q1_matches_raw(
    admin_client: AsyncClient,
) -> None:
    """Q1 = 19/27 = 70.37% in raw → modern reports the same.

    Documented snapshot drift: legacy reports 69.2% (= 18/26), which
    requires one fewer student in the legacy snapshot. We do not
    chase that drift — the canonical helper reports 70.37% which is
    correct against current raw at every layer.
    """
    qra = await _get_qra(admin_client, _CHAPTER9_ITEM_ID)

    q1 = next(
        (q for q in qra.questions_overall if q.question_no == "1"),
        None,
    )
    assert q1 is not None, "Q1 missing from questions_overall"
    assert 0.69 <= q1.grade_average <= 0.72, (
        f"Q1 grade_average must match raw 19/27 = 0.704 within rounding, "
        f"got {q1.grade_average}. Legacy 69.2% is documented snapshot "
        f"drift (FRESH-RCA §7)."
    )


@pytest.mark.anyio
async def test_canonical_kpis_control_item_renders_cleanly(
    admin_client: AsyncClient,
) -> None:
    """Single-strand control assessment must render without regression.

    Asserts the canonical helper handles short, single-strand items
    correctly and that QRA/SDD remain in lock-step on a different
    assessment than the audit-target one.
    """
    qra = await _get_qra(admin_client, _CONTROL_ITEM_ID)
    sdd = await _get_sdd(admin_client, _CONTROL_ITEM_ID)

    # Same students / questions / standards as the prior-session control
    # (post-fix verification).
    assert qra.kpis.total_students == 21
    assert qra.kpis.total_questions == 20
    assert qra.kpis.total_standards == 5
    assert 0.85 <= qra.kpis.grade_average <= 0.92, (
        f"Control grade_average should sit ≈0.886, got {qra.kpis.grade_average}"
    )

    # Parity between QRA and SDD on the control too.
    assert qra.kpis.total_students == sdd.kpis.total_students
    assert qra.kpis.total_questions == sdd.kpis.total_questions
    assert qra.kpis.total_standards == sdd.kpis.total_standards
    assert round(qra.kpis.grade_average, 6) == round(sdd.kpis.grade_average, 6)


@pytest.mark.anyio
async def test_canonical_kpis_helper_returns_nonzero_for_seeded_item(
    admin_client: AsyncClient,
) -> None:
    """Sanity guard: the canonical helper must not silently return zeros
    for a fully-seeded assessment. If grade_max == 0 with non-zero
    students, the per-question CTE collapsed everything to NULL —
    indicates the fact_dedup filter (points_possible > 0) is too
    aggressive or fact rows are missing.
    """
    qra = await _get_qra(admin_client, _CHAPTER9_ITEM_ID)

    assert qra.kpis.grade_max > 0.0
    assert qra.kpis.grade_min > 0.0
    assert qra.kpis.grade_min <= qra.kpis.grade_average <= qra.kpis.grade_max
