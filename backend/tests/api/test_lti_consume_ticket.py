"""D — /lti/consume-ticket machine-auth endpoint (mirrors ingestion machine-auth).

Locks the machine-auth FAIL-CLOSED invariant of the session bridge: the only
caller is the Next /api/lti/bridge route, proven by a constant-time
X-LTI-Bridge-Secret compare. No header, wrong secret, or an UNSET/empty configured
secret ALL reject with 401 BEFORE any ticket is consumed; a valid secret + a good
ticket returns the identity payload; a valid secret + an invalid/forged/consumed
ticket returns 400 invalid_ticket (indistinguishable, no oracle).

No live DB: the get_db dependency is overridden with a fake async session whose
raw-SQL execute returns a canned "valid ticket" row (or None), exactly like
tests/api/test_ingestion_machine_auth.py.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import lti as lti_router_mod
from app.core.config import settings
from app.core.dependencies import get_db
from app.main import app

SECRET = "bridge-devsecret"
VALID_TICKET = "valid-ticket-abc"
IDENTITY = {
    "user_id": "33333333-3333-3333-3333-333333333333",
    "email": "launched@lti.test",
    "school_id": "44444444-4444-4444-4444-444444444444",
}


class _FakeResult:
    def __init__(self, mapping):
        self._mapping_val = mapping

    def first(self):
        if self._mapping_val is None:
            return None
        return _MappedRow(self._mapping_val)


class _MappedRow:
    def __init__(self, mapping):
        self._mapping = mapping


class _FakeSession:
    """Returns the canned identity row ONLY for the valid ticket.

    Also records whether a consume was attempted, so the 401 tests can assert the
    ticket was NEVER touched (auth ran BEFORE the service).
    """

    def __init__(self):
        self.consume_attempts = 0

    async def execute(self, statement, params=None):
        self.consume_attempts += 1
        ticket = (params or {}).get("t")
        if ticket == VALID_TICKET:
            return _FakeResult(IDENTITY)
        return _FakeResult(None)

    async def commit(self):
        pass


def _override_db(fake: _FakeSession):
    async def _dep():
        yield fake

    return _dep


@pytest.fixture(scope="module", autouse=True)
def _mount_lti_routes():
    """The LTI router is gated behind LTI_ENABLED (default off) so its routes are
    NOT mounted on the app. Mount them for this module only, and remove EXACTLY
    those routes in teardown so the app is left byte-identical for other tests.
    """
    before = list(app.router.routes)
    app.include_router(lti_router_mod.router, prefix="/api/v1")
    added = [r for r in app.router.routes if r not in before]
    yield
    for r in added:
        app.router.routes.remove(r)


@pytest.fixture
async def machine_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


async def test_no_bridge_secret_header_is_401_and_ticket_untouched(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "LTI_BRIDGE_SECRET", SECRET)
    fake = _FakeSession()
    app.dependency_overrides[get_db] = _override_db(fake)

    resp = await machine_client.post(
        "/api/v1/lti/consume-ticket", json={"ticket": VALID_TICKET}
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"
    assert fake.consume_attempts == 0  # rejected before the service ran


async def test_wrong_bridge_secret_is_401_and_ticket_untouched(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "LTI_BRIDGE_SECRET", SECRET)
    fake = _FakeSession()
    app.dependency_overrides[get_db] = _override_db(fake)

    resp = await machine_client.post(
        "/api/v1/lti/consume-ticket",
        headers={"X-LTI-Bridge-Secret": "wrong"},
        json={"ticket": VALID_TICKET},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"
    assert fake.consume_attempts == 0


async def test_unset_secret_fails_closed_even_with_header(machine_client, monkeypatch):
    # Secret unset/empty → reject BEFORE any compare (never compare_digest(x, "")).
    monkeypatch.setattr(settings, "LTI_BRIDGE_SECRET", "")
    fake = _FakeSession()
    app.dependency_overrides[get_db] = _override_db(fake)

    resp = await machine_client.post(
        "/api/v1/lti/consume-ticket",
        headers={"X-LTI-Bridge-Secret": ""},
        json={"ticket": VALID_TICKET},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"
    assert fake.consume_attempts == 0


async def test_none_secret_fails_closed(machine_client, monkeypatch):
    # Config default is None; a non-empty header must STILL be rejected fail-closed.
    monkeypatch.setattr(settings, "LTI_BRIDGE_SECRET", None)
    fake = _FakeSession()
    app.dependency_overrides[get_db] = _override_db(fake)

    resp = await machine_client.post(
        "/api/v1/lti/consume-ticket",
        headers={"X-LTI-Bridge-Secret": "anything"},
        json={"ticket": VALID_TICKET},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"
    assert fake.consume_attempts == 0


async def test_correct_secret_valid_ticket_returns_identity(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "LTI_BRIDGE_SECRET", SECRET)
    fake = _FakeSession()
    app.dependency_overrides[get_db] = _override_db(fake)

    resp = await machine_client.post(
        "/api/v1/lti/consume-ticket",
        headers={"X-LTI-Bridge-Secret": SECRET},
        json={"ticket": VALID_TICKET},
    )

    assert resp.status_code == 200
    assert resp.json() == IDENTITY
    assert fake.consume_attempts == 1  # the service ran exactly once


async def test_correct_secret_invalid_ticket_is_400_invalid_ticket(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "LTI_BRIDGE_SECRET", SECRET)
    fake = _FakeSession()
    app.dependency_overrides[get_db] = _override_db(fake)

    resp = await machine_client.post(
        "/api/v1/lti/consume-ticket",
        headers={"X-LTI-Bridge-Secret": SECRET},
        json={"ticket": "already-consumed-or-forged"},
    )

    assert resp.status_code == 400
    # No oracle: invalid / expired / already-consumed all read identically.
    assert resp.json()["error"] == "invalid_ticket"
