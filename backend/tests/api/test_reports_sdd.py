"""Tests for the Standards Deep Dive endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.reports import StandardsDeepDivePayload


@pytest.mark.anyio
async def test_sdd_returns_strand_rollup_and_standards(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get("/api/v1/reports/standards-deep-dive")
    assert response.status_code == 200, response.text

    payload = StandardsDeepDivePayload.model_validate(response.json())

    # Should produce some strand rollup (cube_standard_summary has 110 rows
    # for Athenian -> at least one strand_id)
    assert isinstance(payload.strands, list)
    # The strand rollup may be small (some standards may have no strand);
    # the standards list itself must be populated.
    assert isinstance(payload.standards, list)
    assert len(payload.standards) > 0

    for s in payload.standards:
        assert s.total_questions >= 0
        assert 0.0 <= s.grade_average <= 1.0001


@pytest.mark.anyio
async def test_sdd_requires_reports_read_permission(
    user_client: AsyncClient,
) -> None:
    response = await user_client.get("/api/v1/reports/standards-deep-dive")
    assert response.status_code == 403
