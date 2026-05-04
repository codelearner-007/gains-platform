"""Test authentication and JWT validation."""

import pytest
from unittest.mock import AsyncMock, patch

from app.core.security import verify_token_hs256, extract_user_claims
from app.core.exceptions import InvalidTokenError


@pytest.mark.anyio
async def test_verify_token_hs256_invalid():
    """Test HS256 token verification with invalid token."""
    with pytest.raises(InvalidTokenError):
        verify_token_hs256("invalid-token")


@pytest.mark.anyio
async def test_extract_user_claims():
    """Test extracting user claims from JWT payload."""
    payload = {
        "sub": "user-123",
        "email": "test@example.com",
        "user_role": "super_admin",
        "hierarchy_level": 10000,
        "permissions": ["roles:create", "users:read_all"],
    }

    claims = extract_user_claims(payload)

    assert claims["user_id"] == "user-123"
    assert claims["email"] == "test@example.com"
    assert claims["user_role"] == "super_admin"
    assert claims["hierarchy_level"] == 10000
    assert "roles:create" in claims["permissions"]


@pytest.mark.anyio
async def test_extract_user_claims_defaults():
    """Test extracting user claims with default values."""
    payload = {
        "sub": "user-456",
        "email": "user@example.com",
    }

    claims = extract_user_claims(payload)

    assert claims["user_id"] == "user-456"
    assert claims["user_role"] == "user"  # default
    assert claims["hierarchy_level"] == 100  # default
    assert claims["permissions"] == []  # default


@pytest.mark.anyio
async def test_jwks_fetch_timeout():
    """Test JWKS fetch timeout handling."""
    from app.core.security import fetch_jwks
    import httpx

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.TimeoutException("Timeout")
        mock_client.return_value.__aenter__.return_value = mock_instance

        with pytest.raises(InvalidTokenError) as exc_info:
            await fetch_jwks()

        assert "timeout" in str(exc_info.value).lower()
