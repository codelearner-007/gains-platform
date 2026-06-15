"""LTI is disabled by default — every /api/v1/lti/* route must 404.

With settings.LTI_ENABLED False (the default), the LTI router is never
included, so the protocol surface is unreachable and no LTI code path can
provision auth.users / user_schools. Flipping the flag true restores the
router (asserted here by re-including it on a throwaway app instance).
"""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


async def _client() -> AsyncClient:
    return AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_lti_disabled_by_default():
    assert settings.LTI_ENABLED is False


@pytest.mark.anyio
async def test_jwks_returns_404_when_disabled():
    async with await _client() as ac:
        r = await ac.get("/api/v1/lti/.well-known/jwks.json")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_login_returns_404_when_disabled():
    async with await _client() as ac:
        r = await ac.get(
            "/api/v1/lti/login",
            params={"iss": "https://x", "client_id": "c"},
        )
    assert r.status_code == 404


@pytest.mark.anyio
async def test_launch_returns_404_when_disabled():
    async with await _client() as ac:
        r = await ac.post("/api/v1/lti/launch", data={"id_token": "x", "state": "y"})
    assert r.status_code == 404


def test_router_includes_lti_when_flag_enabled(monkeypatch):
    """With LTI_ENABLED true, a freshly built v1 router exposes the LTI routes."""
    import importlib

    import app.api.v1.router as router_module

    monkeypatch.setattr(router_module.settings, "LTI_ENABLED", True)
    rebuilt = importlib.reload(router_module)
    try:
        lti_paths = [
            r.path for r in rebuilt.api_router.routes if "/lti/" in getattr(r, "path", "")
        ]
        assert any(p.endswith("/lti/launch") for p in lti_paths), lti_paths
        assert any("jwks" in p for p in lti_paths), lti_paths
    finally:
        # Restore the default-off router so the rest of the suite is unaffected.
        monkeypatch.setattr(router_module.settings, "LTI_ENABLED", False)
        importlib.reload(router_module)
