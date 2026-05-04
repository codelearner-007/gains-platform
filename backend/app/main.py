"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from sqlalchemy.exc import DataError as SADataError, ProgrammingError

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging_config import setup_logging
from app.core.rate_limit import limiter
from app.core.redis_client import close_redis, init_redis, redis_ping
from app.db.session import get_session_manager

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan events.

    Handles startup and shutdown events for the FastAPI application.
    """
    # Startup
    logger.info("Starting FastAPI application...")
    await init_redis()
    yield

    # Shutdown
    logger.info("Shutting down FastAPI application...")
    await close_redis()
    session_manager = get_session_manager()
    await session_manager.close()
    logger.info("Database connections closed")


# Create FastAPI app
app = FastAPI(
    title="Next.js + Supabase Starter - FastAPI Backend",
    description="Production-ready FastAPI backend for Next.js + Supabase starter template",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware (optional, disabled by default for Vercel rewrites)
if settings.ENABLE_CORS:
    logger.info("CORS enabled for origins: %s", settings.ALLOWED_ORIGINS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Exception handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions."""
    # Log permission details server-side for debugging (never in response)
    from app.core.exceptions import PermissionDeniedError
    if isinstance(exc, PermissionDeniedError):
        logger.warning(
            "PermissionDenied: required=%s path=%s",
            getattr(exc, "_required_permission", "unknown"),
            request.url.path,
        )
    else:
        logger.error("AppException: %s", exc.message, extra={"details": exc.details})
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "status_code": exc.status_code,
            "details": exc.details,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    logger.error("Validation error: %s", exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation failed",
            "status_code": 422,
            "details": exc.errors(),
        },
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Handle Pydantic ValidationError raised outside FastAPI's request parsing layer.

    FastAPI handles RequestValidationError for request body parsing; this handler
    catches ValidationError raised directly (e.g. from model_validator calls).
    """
    logger.error("Pydantic ValidationError: %s", exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation failed",
            "status_code": 422,
            "details": exc.errors(),
        },
    )


@app.exception_handler(SADataError)
async def handle_sa_data_error(request: Request, exc: SADataError) -> JSONResponse:
    """Handle SQLAlchemy DataError (e.g. invalid UUID format) without leaking SQL."""
    logger.error("SQLAlchemy DataError: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Invalid request parameter format"},
    )


@app.exception_handler(ProgrammingError)
async def handle_programming_error(request: Request, exc: ProgrammingError) -> JSONResponse:
    """Handle SQLAlchemy ProgrammingError without leaking SQL details."""
    logger.error("SQLAlchemy ProgrammingError: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Invalid request parameter"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.exception("Unexpected error occurred")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "details": {"message": str(exc)} if settings.ENVIRONMENT == "development" else {},
        },
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns:
        Health status with database connectivity check
    """
    # Check database connection
    try:
        session_manager = get_session_manager()
        async with session_manager.session() as session:
            await session.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        database_status = "disconnected"

    redis_status: str | None = None
    if settings.REDIS_ENABLE_RATE_LIMIT_STORAGE or settings.REDIS_ENABLE_SHARE_SESSIONS:
        redis_status = "connected" if await redis_ping() else "disconnected"

    healthy = database_status == "connected"
    if redis_status is not None and redis_status != "connected":
        healthy = False

    return {
        "status": "healthy" if healthy else "unhealthy",
        "database": database_status,
        "redis": redis_status,
        "environment": settings.ENVIRONMENT,
    }


# Include API routers
app.include_router(api_router, prefix="/api")


# Root endpoint
@app.get("/", tags=["Root"])
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "message": "FastAPI Backend for Next.js + Supabase Starter",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
