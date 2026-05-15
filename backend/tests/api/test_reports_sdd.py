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
