"""Machine-auth ingestion endpoints for the Schoology scraper.

FROZEN scraper ↔ backend contract:

    GET  /api/v1/ingestion/scraper-config   → active-school config (no creds)
    POST /api/v1/ingestion/scraper-complete → pre-create a run row + dispatch

Auth is a shared secret in the ``X-Ingestion-Secret`` header (NOT a user JWT):
the scraper is a headless machine caller. The dependency fails CLOSED — when
``INGESTION_TRIGGER_SECRET`` is unset/empty every request 401s BEFORE any
compare, so this trigger surface is never open when unconfigured.

These endpoints use the privileged ``get_db`` session (never
``get_db_with_rls``): there is no JWT, so an RLS-scoped session would resolve to
an empty tenant set and fail closed on the school lookup.
"""

from __future__ import annotations

import hmac

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.exceptions import AppException
from app.core.rate_limit import limiter
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.schemas.ingestion import (
    ScraperCompleteRequest,
    ScraperCompleteResponse,
    ScraperConfigResponse,
    ScraperSchool,
    ScraperStorage,
)
from app.services.ingestion_dispatch import enqueue

router = APIRouter(prefix="/ingestion", tags=["Ingestion (machine)"])


async def require_ingestion_secret(
    x_ingestion_secret: str | None = Header(default=None),
) -> None:
    """Constant-time machine-auth check; fails CLOSED (R7).

    When ``INGESTION_TRIGGER_SECRET`` is unset/empty, every caller is rejected
    BEFORE any compare (never ``compare_digest(x, "")``). A missing or wrong
    header is likewise rejected. Raises ``AppException`` → the app-wide handler
    renders ``401 {"error":"unauthorized", ...}``.
    """
    configured = settings.INGESTION_TRIGGER_SECRET
    if (
        not configured
        or not x_ingestion_secret
        or not hmac.compare_digest(x_ingestion_secret, configured)
    ):
        raise AppException("unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)


@router.get("/scraper-config", response_model=ScraperConfigResponse)
async def scraper_config(
    _: None = Depends(require_ingestion_secret),
    db: AsyncSession = Depends(get_db),
) -> ScraperConfigResponse:
    """Return the active-school config the scraper needs (NO credentials)."""
    result = await db.execute(
        text(
            """
            SELECT
                school_id::text AS school_id,
                name,
                short_name,
                schoology_building_id,
                category_regex,
                due_date_window_days,
                course_page_limit,
                download_index,
                category_folder_override,
                current_session,
                timezone,
                credential_ref
            FROM schools
            WHERE is_active = TRUE
            ORDER BY short_name
            """
        )
    )
    schools = [
        ScraperSchool(
            school_id=row.school_id,
            name=row.name,
            short_name=row.short_name,
            schoology_building_id=row.schoology_building_id,
            category_regex=row.category_regex,
            due_date_window_days=row.due_date_window_days,
            course_page_limit=row.course_page_limit,
            download_index=list(row.download_index)
            if row.download_index is not None
            else None,
            category_folder_override=row.category_folder_override,
            current_session=row.current_session,
            timezone=row.timezone,
            credential_ref=row.credential_ref,
        )
        for row in result
    ]
    return ScraperConfigResponse(
        storage=ScraperStorage(bucket=settings.INGESTION_STORAGE_BUCKET),
        schools=schools,
    )


@router.post(
    "/scraper-complete",
    response_model=ScraperCompleteResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("10/minute")
async def scraper_complete(
    request: Request,
    payload: ScraperCompleteRequest,
    _: None = Depends(require_ingestion_secret),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Enqueue a pending run for the school; the durable worker does the rest.

    Validates the school exists and is active (404 otherwise), then ENQUEUES a
    ``pending`` ``ingestion_runs`` row (coalescing onto an existing pending run
    for the same school so a retrying scraper never queues a duplicate) and
    commits it. The in-process durable worker (started in the FastAPI lifespan)
    claims the row, lands its raw rows, runs the transform gate, and marks it
    terminal — surviving restarts via a lease + reaper. There is NO synchronous
    dispatch / BackgroundTask here. Returns 202 with the run id.
    """
    result = await db.execute(
        text(
            """
            SELECT school_id::text AS school_id, short_name
            FROM schools
            WHERE short_name = :short_name AND is_active = TRUE
            LIMIT 1
            """
        ),
        {"short_name": payload.short_name},
    )
    school = result.first()
    if school is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "unknown or inactive school"},
        )

    repo = IngestionRunRepository(db)
    run = await enqueue(repo, school_id=school.school_id, note=payload.note)
    # Commit the (possibly coalesced) pending row NOW so it is durable before the
    # worker can claim it. `get_db`'s auto-commit runs at request teardown, but
    # committing explicitly keeps the enqueue self-contained and matches the
    # admin path.
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "run_id": run["run_id"],
            "status": run["status"],
            "school_id": school.school_id,
            "short_name": school.short_name,
        },
    )
