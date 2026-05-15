"""Tests for the standards-alignment data-quality endpoint.

Verifies the admin DQ surface introduced to address the Athenian
"empty SDD" RCA (tasks/cleanup/standards-missing-rca-2026-05-15.md).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.reports import AlignmentDataQualityReport


ALIGNED_ITEM_ID = "8359960427"      # Chapter 9 Test (fully aligned)
UNALIGNED_ITEM_ID = "8368737293"    # Sci Quiz Week 3 FSSA Review (no Standards)


@pytest.mark.anyio
async def test_dq_lists_items_with_status(admin_client: AsyncClient) -> None:
    """Endpoint returns per-item rows with the correct alignment_status."""
    response = await admin_client.get(
        "/api/v1/reports/data-quality/standards-alignment"
    )
    assert response.status_code == 200, response.text

    payload = AlignmentDataQualityReport.model_validate(response.json())
    assert payload.school_id
    assert payload.school_name
    assert payload.items_total == len(payload.items)
    assert (
        payload.items_with_alignment
        + payload.items_missing_alignment
        == payload.items_total
    )

    by_id = {row.item_id: row for row in payload.items}

    if ALIGNED_ITEM_ID in by_id:
        aligned = by_id[ALIGNED_ITEM_ID]
        assert aligned.alignment_status == "full"
        assert aligned.questions_with_alignment == aligned.questions_total
        assert aligned.pct_aligned == 1.0

    if UNALIGNED_ITEM_ID in by_id:
        unaligned = by_id[UNALIGNED_ITEM_ID]
        assert unaligned.alignment_status == "missing"
        assert unaligned.questions_with_alignment == 0
        assert unaligned.pct_aligned == 0.0


@pytest.mark.anyio
async def test_dq_requires_reports_read_permission(
    user_client: AsyncClient,
) -> None:
    response = await user_client.get(
        "/api/v1/reports/data-quality/standards-alignment"
    )
    assert response.status_code == 403
