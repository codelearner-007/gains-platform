"""Machine-auth tests for the scraper ingestion endpoints.

No live DB, no real ingestion run. We override the ``get_db`` dependency with a
fake async session whose ``execute`` returns canned rows, monkeypatch the
``INGESTION_TRIGGER_SECRET`` setting + the run-repo, and drive the app over
httpx's in-process ASGI transport.

Covers the frozen contract's auth + routing behaviour:
  * 401 when no header is sent,
  * 401 when a wrong secret is sent,
  * 401 when the secret setting is unset (fail CLOSED — R7),
  * 202 + a pending row ENQUEUED (monkeypatched) on a known active school,
  * 404 for an unknown / inactive school.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

import app.api.v1.ingestion as ingestion_mod
from app.core.config import settings
from app.core.dependencies import get_db
from app.main import app

SECRET = "devsecret"
KNOWN_SCHOOL = {"school_id": "11111111-1111-1111-1111-111111111111", "short_name": "Athenian"}


class _FakeResult:
    """Mimics the slice of SQLAlchemy's Result we use (``.first()``)."""

    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Row:
    """Attribute-access row (``row.school_id`` / ``row.short_name``)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeSession:
    """Fake AsyncSession: returns a school row for the known short_name only."""

    def __init__(self, known_short_name: str | None):
        self._known = known_short_name

    async def execute(self, statement, params=None):
        short_name = (params or {}).get("short_name")
        if short_name is not None and short_name == self._known:
            return _FakeResult(
                _Row(school_id=KNOWN_SCHOOL["school_id"], short_name=short_name)
            )
        return _FakeResult(None)

    async def commit(self):
        # The endpoint commits the pending run row before scheduling the
        # out-of-band task; the fake just records that it was awaited.
        self.committed = True


def _override_db(known_short_name: str | None):
    async def _dep():
        yield _FakeSession(known_short_name)

    return _dep


@pytest.fixture
async def machine_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


async def test_scraper_complete_no_header_is_401(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", SECRET)
    app.dependency_overrides[get_db] = _override_db(KNOWN_SCHOOL["short_name"])

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        json={"short_name": KNOWN_SCHOOL["short_name"]},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


async def test_scraper_complete_wrong_secret_is_401(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", SECRET)
    app.dependency_overrides[get_db] = _override_db(KNOWN_SCHOOL["short_name"])

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        headers={"X-Ingestion-Secret": "wrong"},
        json={"short_name": KNOWN_SCHOOL["short_name"]},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


async def test_scraper_complete_unset_secret_fails_closed(machine_client, monkeypatch):
    # Secret unset → fail CLOSED even if the caller sends a header (R7).
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", None)
    app.dependency_overrides[get_db] = _override_db(KNOWN_SCHOOL["short_name"])

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        headers={"X-Ingestion-Secret": ""},
        json={"short_name": KNOWN_SCHOOL["short_name"]},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


async def test_scraper_config_unset_secret_fails_closed(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", None)
    app.dependency_overrides[get_db] = _override_db(None)

    resp = await machine_client.get(
        "/api/v1/ingestion/scraper-config",
        headers={"X-Ingestion-Secret": SECRET},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


async def test_scraper_complete_enqueues_and_returns_202(machine_client, monkeypatch):
    # Enqueue-only (HARDENING_PLAN §4): the endpoint pre-creates a pending row and
    # commits it; the durable worker does the rest. No synchronous dispatch.
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", SECRET)
    app.dependency_overrides[get_db] = _override_db(KNOWN_SCHOOL["short_name"])

    created = {}

    async def _fake_pending_for_school(self, school_id):
        return None  # nothing queued yet → create a fresh pending row

    async def _fake_create_pending(self, school_id, note=None):
        created["school_id"] = school_id
        created["note"] = note
        return {
            "run_id": "22222222-2222-2222-2222-222222222222",
            "status": "pending",
        }

    monkeypatch.setattr(
        ingestion_mod.IngestionRunRepository,
        "pending_for_school",
        _fake_pending_for_school,
    )
    monkeypatch.setattr(
        ingestion_mod.IngestionRunRepository,
        "create_pending",
        _fake_create_pending,
    )

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        headers={"X-Ingestion-Secret": SECRET},
        json={"short_name": KNOWN_SCHOOL["short_name"], "note": "hi"},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] == "22222222-2222-2222-2222-222222222222"
    assert body["status"] == "pending"
    assert body["school_id"] == KNOWN_SCHOOL["school_id"]
    assert body["short_name"] == KNOWN_SCHOOL["short_name"]

    # The pending row was created for the resolved school + note passed through.
    assert created["school_id"] == KNOWN_SCHOOL["school_id"]
    assert created["note"] == "hi"


async def test_scraper_complete_unknown_school_is_404(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", SECRET)
    # Fake DB knows a DIFFERENT school, so the requested one is "unknown".
    app.dependency_overrides[get_db] = _override_db("SomeOtherSchool")

    async def _boom(self, *a, **k):  # enqueue must NOT happen on the 404 path
        raise AssertionError("enqueue must not run for an unknown school")

    monkeypatch.setattr(
        ingestion_mod.IngestionRunRepository, "create_pending", _boom
    )
    monkeypatch.setattr(
        ingestion_mod.IngestionRunRepository, "pending_for_school", _boom
    )

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        headers={"X-Ingestion-Secret": SECRET},
        json={"short_name": "Nonexistent"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown or inactive school"


def test_httpx_available():
    # Guard: the ASGI transport import path stays valid (defensive; cheap).
    assert hasattr(httpx, "ASGITransport")
