"""Test permission guards and authorization."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from app.schemas.auth import CurrentUser


@pytest.mark.anyio
async def test_permission_guard_blocks_unauthorized(client: AsyncClient):
    """Test that permission guards return 401 for missing auth."""
    response = await client.get("/api/v1/roles")
    assert response.status_code == 401
    assert "authentication token" in response.json()["error"].lower()


@pytest.mark.anyio
async def test_permission_guard_requires_specific_permission():
    """Test that permission guards check for specific permissions."""
    from app.core.dependencies import require_permission

    # Create a mock user without required permission
    mock_user = CurrentUser(
        user_id="user-123",
        email="test@example.com",
        user_role="user",
        hierarchy_level=100,
        permissions=["users:read_all"],  # Missing roles:create
    )

    permission_checker = require_permission("roles:create")

    # Should raise PermissionDeniedError (consistent app error format)
    from app.core.exceptions import PermissionDeniedError

    with pytest.raises(PermissionDeniedError) as exc_info:
        await permission_checker(mock_user)

    assert exc_info.value.status_code == 403
    assert "roles:create" in exc_info.value.message


@pytest.mark.anyio
async def test_permission_guard_allows_with_permission():
    """Test that permission guards allow access with correct permission."""
    from app.core.dependencies import require_permission

    # Create a mock user with required permission
    mock_user = CurrentUser(
        user_id="user-123",
        email="admin@example.com",
        user_role="super_admin",
        hierarchy_level=10000,
        permissions=["roles:create", "users:read_all"],
    )

    permission_checker = require_permission("roles:create")

    # Should not raise exception
    result = await permission_checker(mock_user)
    assert result == mock_user


@pytest.mark.anyio
async def test_cookie_token_extraction():
    """Test extracting JWT from cookies."""
    from app.core.dependencies import extract_token_from_cookies
    from fastapi import Request

    # Mock request with standard cookie
    mock_request = AsyncMock(spec=Request)
    mock_request.cookies = {"sb-access-token": "test-token-123"}

    token = extract_token_from_cookies(mock_request)
    assert token == "test-token-123"


@pytest.mark.anyio
async def test_chunked_cookie_extraction():
    """Test extracting JWT from chunked cookies."""
    from app.core.dependencies import extract_token_from_cookies
    from fastapi import Request

    # Mock request with chunked cookies
    mock_request = AsyncMock(spec=Request)
    mock_request.cookies = {
        "sb-access-token.0": "chunk1",
        "sb-access-token.1": "chunk2",
        "sb-access-token.2": "chunk3",
    }

    token = extract_token_from_cookies(mock_request)
    assert token == "chunk1chunk2chunk3"


@pytest.mark.anyio
async def test_supabase_ssr_auth_cookie_extraction_base64_json():
    """Test extracting JWT from a Supabase SSR auth-token cookie payload."""
    import base64
    import json

    from app.core.dependencies import extract_token_from_cookies
    from fastapi import Request

    session_payload = {"access_token": "jwt-access-token-xyz", "refresh_token": "rt"}
    encoded = base64.b64encode(json.dumps(session_payload).encode("utf-8")).decode("utf-8")

    mock_request = AsyncMock(spec=Request)
    mock_request.cookies = {"sb-test-auth-token": f"base64-{encoded}"}

    token = extract_token_from_cookies(mock_request)
    assert token == "jwt-access-token-xyz"


@pytest.mark.anyio
async def test_supabase_ssr_auth_cookie_extraction_chunked():
    """Test extracting JWT from chunked Supabase SSR auth-token cookies."""
    import base64
    import json

    from app.core.dependencies import extract_token_from_cookies
    from fastapi import Request

    session_payload = {"access_token": "jwt-access-token-abc"}
    encoded = base64.b64encode(json.dumps(session_payload).encode("utf-8")).decode("utf-8")
    value = f"base64-{encoded}"

    mock_request = AsyncMock(spec=Request)
    mock_request.cookies = {
        "sb-anything-auth-token.0": value[:10],
        "sb-anything-auth-token.1": value[10:],
    }

    token = extract_token_from_cookies(mock_request)
    assert token == "jwt-access-token-abc"


@pytest.mark.anyio
async def test_cookie_extraction_returns_none_when_missing():
    """Test that cookie extraction returns None when cookies are missing."""
    from app.core.dependencies import extract_token_from_cookies
    from fastapi import Request

    # Mock request without cookies
    mock_request = AsyncMock(spec=Request)
    mock_request.cookies = {}

    token = extract_token_from_cookies(mock_request)
    assert token is None
