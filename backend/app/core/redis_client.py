"""Async Redis client lifecycle and helpers."""

import logging
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import redis.asyncio as redis
from redis.asyncio.client import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def _redact_redis_url(raw_url: str) -> str:
    parts = urlsplit(raw_url)
    if parts.username or parts.password:
        netloc = parts.hostname or ""
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        if parts.username:
            netloc = f"{parts.username}:***@{netloc}"
        else:
            netloc = f"***@{netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return raw_url


def build_redis_key(*parts: str) -> str:
    return ":".join([settings.REDIS_PREFIX, *parts])


async def init_redis() -> None:
    global _redis
    if _redis is not None:
        return

    if not (settings.REDIS_ENABLE_RATE_LIMIT_STORAGE or settings.REDIS_ENABLE_SHARE_SESSIONS):
        return

    if not settings.REDIS_URL:
        return

    _redis = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
    )

    try:
        await _redis.ping()
        logger.info(
            "Redis client initialized (%s)",
            _redact_redis_url(settings.REDIS_URL),
        )
    except Exception:
        logger.warning(
            "Redis client initialized but ping failed (%s)",
            _redact_redis_url(settings.REDIS_URL),
            exc_info=True,
        )
        try:
            await _redis.aclose()
        except Exception:
            logger.warning(
                "Failed to close broken Redis client after ping failure (%s)",
                _redact_redis_url(settings.REDIS_URL),
                exc_info=True,
            )
        finally:
            _redis = None


def get_redis() -> Optional[Redis]:
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is None:
        return
    try:
        await _redis.aclose()
    except Exception:
        logger.warning("Failed to close Redis client", exc_info=True)
    finally:
        _redis = None


async def redis_ping() -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception as exc:
        logger.warning("Redis ping failed: %s", exc, exc_info=True)
        return False

