"""Enqueue-only tests for the machine scraper-complete endpoint.

Wave-3 (HARDENING_PLAN §4/§9 Agent D) turned ``scraper-complete`` into a pure
ENQUEUE: it pre-creates (coalescing) a ``pending`` ``ingestion_runs`` row, commits
it, and returns 202 — the durable in-process worker does the actual landing +
transform gate later. There is NO synchronous ``BackgroundTask`` / dispatch / real
ingestion in the request path anymore.

These tests drive the app over httpx's in-process ASGI transport with a fake
``get_db`` session and a monkeypatched run repo, and assert:
  * 202 + a ``pending`` row is created for a known active school,
  * coalescing: a 2nd call for the same school returns the SAME pending run and
    does NOT create a duplicate,
  * 401 (no header / wrong secret / unset setting) is unchanged,
  * 404 for an unknown / inactive school is unchanged,
  * NO real ingestion / transform runs synchronously in the request.

No live DB, no worker, no real run.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.v1.ingestion as ingestion_mod
from app.core.config import settings
from app.core.dependencies import get_db
from app.main import app

SECRET = "devsecret"
KNOWN_SCHOOL = {
    "school_id": "11111111-1111-1111-1111-111111111111",
    "short_name": "Athenian",
}
PENDING_RUN = {
    "run_id": "22222222-2222-2222-2222-222222222222",
    "status": "pending",
    "started_at": "2026-07-23T00:00:00+00:00",
}


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
        self.commits = 0

    async def execute(self, statement, params=None):
        short_name = (params or {}).get("short_name")
        if short_name is not None and short_name == self._known:
            return _FakeResult(
                _Row(school_id=KNOWN_SCHOOL["school_id"], short_name=short_name)
            )
        return _FakeResult(None)

    async def commit(self):
        self.commits += 1


def _override_db(session: _FakeSession):
    async def _dep():
        yield session

    return _dep


@pytest.fixture
async def machine_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _no_synchronous_ingestion(monkeypatch):
    """Guard: nothing in the request path may run real ingestion/transforms.

    The enqueue endpoint must not import or invoke ``run_ingestion`` / the
    transform runner / a worker synchronously. We replace the run-ingestion
    entrypoint with a landmine so any accidental synchronous call fails the test
    loudly rather than silently reintroducing the retired fire-and-forget path.
    """

    def _landmine(*a, **k):
        raise AssertionError(
            "run_ingestion must NOT be called synchronously from the enqueue path"
        )

    import app.jobs.ingest_schoology as ingest_mod

    monkeypatch.setattr(ingest_mod, "run_ingestion", _landmine)


def _stub_repo(monkeypatch, existing=None):
    """Stub the run repo so ``enqueue`` is exercised without a real DB.

    ``pending_for_school`` returns ``existing`` (None → nothing queued yet).
    ``create_pending`` records its call and returns a fresh pending row. Returns
    a mutable ``calls`` dict for assertions.
    """
    calls = {"pending_for_school": 0, "create_pending": 0, "create_args": None}

    async def _fake_pending_for_school(self, school_id):
        calls["pending_for_school"] += 1
        return existing

    async def _fake_create_pending(self, school_id, note=None):
        calls["create_pending"] += 1
        calls["create_args"] = {"school_id": school_id, "note": note}
        return dict(PENDING_RUN)

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
    return calls


async def test_scraper_complete_enqueues_and_returns_202(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", SECRET)
    session = _FakeSession(KNOWN_SCHOOL["short_name"])
    app.dependency_overrides[get_db] = _override_db(session)
    calls = _stub_repo(monkeypatch, existing=None)

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        headers={"X-Ingestion-Secret": SECRET},
        json={"short_name": KNOWN_SCHOOL["short_name"], "note": "hi"},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] == PENDING_RUN["run_id"]
    assert body["status"] == "pending"
    assert body["school_id"] == KNOWN_SCHOOL["school_id"]
    assert body["short_name"] == KNOWN_SCHOOL["short_name"]

    # A fresh pending row was created for the resolved school + note passed through.
    assert calls["create_pending"] == 1
    assert calls["create_args"] == {
        "school_id": KNOWN_SCHOOL["school_id"],
        "note": "hi",
    }
    # The enqueued row was committed so the worker can claim it durably.
    assert session.commits == 1


async def test_scraper_complete_coalesces_onto_existing_pending(
    machine_client, monkeypatch
):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", SECRET)
    session = _FakeSession(KNOWN_SCHOOL["short_name"])
    app.dependency_overrides[get_db] = _override_db(session)
    # A pending run already exists for this school → enqueue must reuse it.
    existing = dict(PENDING_RUN)
    calls = _stub_repo(monkeypatch, existing=existing)

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        headers={"X-Ingestion-Secret": SECRET},
        json={"short_name": KNOWN_SCHOOL["short_name"]},
    )

    assert resp.status_code == 202
    body = resp.json()
    # Same run returned, and NO duplicate row created.
    assert body["run_id"] == PENDING_RUN["run_id"]
    assert body["status"] == "pending"
    assert calls["pending_for_school"] == 1
    assert calls["create_pending"] == 0


async def test_scraper_complete_no_header_is_401(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", SECRET)
    session = _FakeSession(KNOWN_SCHOOL["short_name"])
    app.dependency_overrides[get_db] = _override_db(session)
    calls = _stub_repo(monkeypatch, existing=None)

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        json={"short_name": KNOWN_SCHOOL["short_name"]},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"
    # Auth fails before any enqueue work.
    assert calls["create_pending"] == 0
    assert calls["pending_for_school"] == 0


async def test_scraper_complete_wrong_secret_is_401(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", SECRET)
    session = _FakeSession(KNOWN_SCHOOL["short_name"])
    app.dependency_overrides[get_db] = _override_db(session)
    _stub_repo(monkeypatch, existing=None)

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        headers={"X-Ingestion-Secret": "wrong"},
        json={"short_name": KNOWN_SCHOOL["short_name"]},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


async def test_scraper_complete_unset_secret_fails_closed(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", None)
    session = _FakeSession(KNOWN_SCHOOL["short_name"])
    app.dependency_overrides[get_db] = _override_db(session)
    _stub_repo(monkeypatch, existing=None)

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        headers={"X-Ingestion-Secret": ""},
        json={"short_name": KNOWN_SCHOOL["short_name"]},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


async def test_scraper_complete_unknown_school_is_404(machine_client, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_TRIGGER_SECRET", SECRET)
    # Fake DB knows a DIFFERENT school, so the requested one is "unknown".
    session = _FakeSession("SomeOtherSchool")
    app.dependency_overrides[get_db] = _override_db(session)
    calls = _stub_repo(monkeypatch, existing=None)

    resp = await machine_client.post(
        "/api/v1/ingestion/scraper-complete",
        headers={"X-Ingestion-Secret": SECRET},
        json={"short_name": "Nonexistent"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown or inactive school"
    # No enqueue happens for an unknown school.
    assert calls["create_pending"] == 0
    assert calls["pending_for_school"] == 0
