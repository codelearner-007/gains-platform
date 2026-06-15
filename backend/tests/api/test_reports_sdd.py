"""Tests for the Standards Deep Dive endpoint and its alignment data quality block.

These tests rely on the live local Supabase DB seeded by the transformation
pipeline. They assume Athenian's 33 ingested items are present and pick:

* a known-aligned assessment (Chapter 9 Test, item_id 8359960427) with 12
  standards across multiple strands
* a known-unaligned assessment (Science Quiz Week 3 FSSA Review, item_id
  8368737293) whose Schoology CSV had zero Standards columns. Legacy
  coerces its NULL standards to a single ``'Other'`` strand/standard
  (see the unaligned test below for the parity evidence), so the rollups
  are NOT empty — they carry one ``'Other'`` row.

The tests intentionally use a per-item path param rather than a query
filter (the route is ``/standards-deep-dive/{item_id}``) and validate
the full ``StandardsDeepDivePayload`` shape including the
``data_quality`` block introduced for the standards-alignment RCA
(see tasks/cleanup/standards-missing-rca-2026-05-15.md).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.reports import StandardsDeepDivePayload


ALIGNED_ITEM_ID = "8359960427"      # Chapter 9 Test — 59 aligned q-rows
UNALIGNED_ITEM_ID = "8368737293"    # Science Quiz Week 3 FSSA Review — 0 aligned


@pytest.mark.anyio
async def test_sdd_aligned_assessment_returns_strand_rollup(
    admin_client: AsyncClient,
) -> None:
    """A fully-aligned assessment renders strands, standards and KPIs."""
    response = await admin_client.get(
        f"/api/v1/reports/standards-deep-dive/{ALIGNED_ITEM_ID}"
    )
    if response.status_code == 404:
        pytest.skip("Aligned fixture item missing — pipeline not run for this DB.")
    assert response.status_code == 200, response.text

    payload = StandardsDeepDivePayload.model_validate(response.json())
    assert payload.assessment.item_id == ALIGNED_ITEM_ID
    assert len(payload.strands_rollup) > 0
    assert len(payload.standards_rollup) > 0
    assert payload.kpis.total_questions > 0
    assert payload.kpis.total_standards > 0

    assert payload.data_quality is not None
    assert payload.data_quality.alignment_status == "full"
    assert payload.data_quality.questions_with_alignment > 0
    assert (
        payload.data_quality.questions_with_alignment
        == payload.data_quality.questions_total
    )


@pytest.mark.anyio
async def test_sdd_unaligned_assessment_signals_missing_alignment(
    admin_client: AsyncClient,
) -> None:
    """Sci Quiz Week 3 has no Standards columns in the Schoology CSV.

    LEGACY-PARITY UPDATE (Wave 3, 2026-06-05): the original assertions
    here (``strands_rollup == []`` / ``standards_rollup == []`` /
    ``total_standards == 0``) encoded a *pre-parity* expectation. Legacy
    is NOT empty for a truly-unaligned assessment: the Schoology PySpark
    notebook coerces NULL/blank ``Standards`` → ``'Other'`` before the
    cubes are built (``Schoology_py.ipynb`` §8; mirrored in
    ``cube_question_summary.sql:296``,
    ``cube_question_summary_overall.sql:268/291``,
    ``cube_overallperformance_summary.sql:40``, ``cube_user_summary.sql:49``;
    documented in ``40_schoology_py_spec.md:387-388,647,679,741``). The
    legacy PBIX therefore renders a SINGLE ``Other`` strand + ``Other``
    standard at the assessment's overall grade average. Evidence on the
    live seeded DB: ``cube_question_summary`` holds 10 rows for item
    ``8368737293``, ALL tagged ``standards='Other'``.

    ``report_service._synthesize_other_rollups`` (added in ``75517e2``)
    re-injects that synthetic ``Other`` row so QRA/SDD match Schoology
    screenshot-for-screenshot. The endpoint must still 200 and
    ``data_quality.alignment_status`` MUST remain ``"missing"`` so the UI
    can render the alignment-warning card alongside the ``Other`` row.
    """
    response = await admin_client.get(
        f"/api/v1/reports/standards-deep-dive/{UNALIGNED_ITEM_ID}"
    )
    if response.status_code == 404:
        pytest.skip("Unaligned fixture item missing — pipeline not run for this DB.")
    assert response.status_code == 200, response.text

    payload = StandardsDeepDivePayload.model_validate(response.json())
    assert payload.assessment.item_id == UNALIGNED_ITEM_ID

    # Legacy NULL→'Other' coercion: exactly one synthetic strand + standard.
    assert [s.strand for s in payload.strands_rollup] == ["Other"], (
        f"expected single legacy 'Other' strand, got "
        f"{[s.strand for s in payload.strands_rollup]}"
    )
    assert [s.schoology_standard for s in payload.standards_rollup] == ["Other"], (
        f"expected single legacy 'Other' standard, got "
        f"{[s.schoology_standard for s in payload.standards_rollup]}"
    )
    # KPI tile counts the synthesized 'Other' standard exactly once.
    assert payload.kpis.total_standards == 1
    # The synthetic 'Other' row carries every question and the overall grade.
    other_strand = payload.strands_rollup[0]
    assert other_strand.num_standards == 1
    assert other_strand.num_questions == payload.kpis.total_questions
    assert other_strand.grade_average == payload.kpis.grade_average

    # data_quality still flags the gap so the UI shows the warning card.
    assert payload.data_quality is not None
    assert payload.data_quality.alignment_status == "missing"
    assert payload.data_quality.questions_total > 0
    assert payload.data_quality.questions_with_alignment == 0
    assert payload.data_quality.remediation_hint  # non-empty hint


@pytest.mark.anyio
async def test_sdd_unknown_item_returns_404(admin_client: AsyncClient) -> None:
    response = await admin_client.get(
        "/api/v1/reports/standards-deep-dive/__missing__"
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_sdd_requires_reports_read_permission(
    user_client: AsyncClient,
) -> None:
    response = await user_client.get(
        f"/api/v1/reports/standards-deep-dive/{ALIGNED_ITEM_ID}"
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_sdd_kpis_pull_from_canonical_helper(
    admin_client: AsyncClient,
) -> None:
    """KPI strip values must come from the canonical legacy-DAX helper.

    Updated 2026-05-18 to reflect the FRESH RCA's canonical contract.
    Previously this test allowed total_standards in [7, 12] because the
    cube_school_summary column counted distinct identifier UUIDs; the
    canonical helper now matches legacy DAX semantics
    (``DISTINCTCOUNT(cqso[Standards])`` over the raw label column) and
    must report exactly 12 for the audit assessment. See
    ``.hermes/report-parity/FRESH-RCA-2026-05-18-stable-formulas.md``.
    """
    response = await admin_client.get(
        f"/api/v1/reports/standards-deep-dive/{ALIGNED_ITEM_ID}"
    )
    if response.status_code == 404:
        pytest.skip("Aligned fixture item missing — pipeline not run for this DB.")
    assert response.status_code == 200, response.text

    payload = StandardsDeepDivePayload.model_validate(response.json())
    assert payload.kpis.total_questions == 18, (
        f"expected 18 questions, got {payload.kpis.total_questions}"
    )
    assert payload.kpis.total_standards == 12, (
        f"canonical helper must report legacy 12 standards (raw label "
        f"grain), got {payload.kpis.total_standards}"
    )
    assert 0.63 <= payload.kpis.grade_average <= 0.68, (
        f"grade_average must sit within legacy ±2pp band of 0.669, "
        f"got {payload.kpis.grade_average}"
    )


@pytest.mark.anyio
async def test_sdd_standards_rollup_uses_cube_standard_summary(
    admin_client: AsyncClient,
) -> None:
    """Rollups must source from cube_standard_summary (RCA Layer A1).

    The Chapter-9 fixture has 6 distinct strands and 12 distinct
    Schoology canonical standards. We assert the looser bound
    (≥5 strands, ≥10 standards) to remain robust to minor data shifts.
    """
    response = await admin_client.get(
        f"/api/v1/reports/standards-deep-dive/{ALIGNED_ITEM_ID}"
    )
    if response.status_code == 404:
        pytest.skip("Aligned fixture item missing — pipeline not run for this DB.")
    assert response.status_code == 200, response.text

    payload = StandardsDeepDivePayload.model_validate(response.json())
    assert len(payload.strands_rollup) >= 5, (
        f"expected ≥5 real strands, got {len(payload.strands_rollup)}: "
        f"{[s.strand for s in payload.strands_rollup]}"
    )
    assert len(payload.standards_rollup) >= 10, (
        f"expected ≥10 Schoology standard rows, got "
        f"{len(payload.standards_rollup)}"
    )
    # Defense: ensure no empty-strand sentinel rows leak through
    for s in payload.strands_rollup:
        assert s.strand, "blank-strand sentinel row leaked into strands_rollup"


@pytest.mark.anyio
async def test_sdd_band_bars_at_schoology_standard_grain(
    admin_client: AsyncClient,
) -> None:
    """Performance bands must render one row per Schoology standard.

    The 3 × 100%-stacked bar panels have the Schoology canonical
    standard on the Y-axis.
    """
    response = await admin_client.get(
        f"/api/v1/reports/standards-deep-dive/{ALIGNED_ITEM_ID}"
    )
    if response.status_code == 404:
        pytest.skip("Aligned fixture item missing — pipeline not run for this DB.")
    assert response.status_code == 200, response.text

    payload = StandardsDeepDivePayload.model_validate(response.json())
    all_bands = payload.band_high + payload.band_mid + payload.band_low
    assert all_bands, "all three bands empty — pipeline data missing?"
    for row in all_bands:
        # Pydantic validation already ensures the field is present; we
        # assert non-empty to guard against an upstream regression where
        # the field is wired but blank.
        assert row.schoology_standard, (
            "band row missing schoology_standard — schema regressed to "
            "strand grain?"
        )
