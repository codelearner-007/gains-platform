"""Rate limiting configuration using slowapi."""

import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_limiter() -> Limiter:
    if settings.REDIS_ENABLE_RATE_LIMIT_STORAGE and settings.REDIS_URL:
        try:
            return Limiter(
                key_func=get_remote_address,
                storage_uri=settings.REDIS_URL,
                storage_options={
                    "socket_connect_timeout": settings.REDIS_CONNECT_TIMEOUT_SECONDS,
                    "socket_timeout": settings.REDIS_SOCKET_TIMEOUT_SECONDS,
                },
            )
        except Exception:
            logger.warning(
                "Redis rate-limit storage unavailable; falling back to in-memory limiter",
                exc_info=True,
            )
    return Limiter(key_func=get_remote_address)


limiter = _build_limiter()
