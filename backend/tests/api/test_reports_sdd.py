"""Tests for the Standards Deep Dive endpoint and its alignment data quality block.

These tests rely on the live local Supabase DB seeded by the transformation
pipeline. They assume Athenian's 33 ingested items are present and pick:

* a known-aligned assessment (Chapter 9 Test, item_id 8359960427) with 12
  standards across multiple strands
* a known-unaligned assessment (Science Quiz Week 3 FSSA Review, item_id
  8368737293) whose Schoology CSV had zero Standards columns.

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

    The endpoint must still 200 (so the page can render the KPI strip)
    but ``data_quality.alignment_status`` MUST be ``"missing"`` so the
    UI knows to render the empty-state card instead of blank charts.
    """
    response = await admin_client.get(
        f"/api/v1/reports/standards-deep-dive/{UNALIGNED_ITEM_ID}"
    )
    if response.status_code == 404:
        pytest.skip("Unaligned fixture item missing — pipeline not run for this DB.")
    assert response.status_code == 200, response.text

    payload = StandardsDeepDivePayload.model_validate(response.json())
    assert payload.assessment.item_id == UNALIGNED_ITEM_ID
    assert payload.strands_rollup == []
    assert payload.standards_rollup == []
    assert payload.kpis.total_standards == 0

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
async def test_sdd_kpis_pull_from_school_summary(
    admin_client: AsyncClient,
) -> None:
    """KPI strip values must match cube_school_summary (RCA Layer A2).

    Before the fix, ``total_questions`` / ``total_standards`` /
    ``grade_average`` were derived from ``strands_rollup`` which inherited
    the dim_strand many-to-many inflation. Now the SDD service reads the
    pre-rolled-up values directly from ``cube_school_summary`` (see
    ``50_sdd_spec.md`` §3).
    """
    response = await admin_client.get(
        f"/api/v1/reports/standards-deep-dive/{ALIGNED_ITEM_ID}"
    )
    if response.status_code == 404:
        pytest.skip("Aligned fixture item missing — pipeline not run for this DB.")
    assert response.status_code == 200, response.text

    payload = StandardsDeepDivePayload.model_validate(response.json())
    assert payload.kpis.total_questions == 18, (
        f"expected 18 questions (cube_school_summary), got "
        f"{payload.kpis.total_questions}"
    )
    assert payload.kpis.total_standards == 11, (
        f"expected 11 standards (cube_school_summary), got "
        f"{payload.kpis.total_standards}"
    )
    assert 0.62 <= payload.kpis.grade_average <= 0.68, (
        f"grade_average should sit within the legacy ±0.03 band of 0.639, "
        f"got {payload.kpis.grade_average}"
    )


@pytest.mark.anyio
async def test_sdd_standards_rollup_uses_cube_standard_summary(
    admin_client: AsyncClient,
) -> None:
    """Rollups must source from cube_standard_summary (RCA Layer A1).

    The Chapter-9 fixture has 6 distinct strands and 12 distinct cpalms
    rows in cube_standard_summary; the broken substring chain previously
    produced 4 strands and 4 standard rows. We assert the looser bound
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
        f"expected ≥10 cpalms standard rows, got "
        f"{len(payload.standards_rollup)}"
    )
    # Defense: ensure no empty-strand sentinel rows leak through
    for s in payload.strands_rollup:
        assert s.strand, "blank-strand sentinel row leaked into strands_rollup"


@pytest.mark.anyio
async def test_sdd_band_bars_at_cpalms_standard_grain(
    admin_client: AsyncClient,
) -> None:
    """Performance bands must render one row per cpalms_standard (RCA Layer A4).

    Per spec §4.4 (50_sdd_spec.md:143-184) the 3 × 100%-stacked bar
    panels have ``dim_standard.cPalms_Standard`` on the Y-axis. The old
    schema (``SddBandStrandRow``) flattened to per-strand.
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
        assert row.cpalms_standard, (
            "band row missing cpalms_standard — schema regressed to "
            "strand grain?"
        )
