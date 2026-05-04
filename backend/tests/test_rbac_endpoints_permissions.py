"""Tests for RBAC endpoint permission requirements without hitting a real DB."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.main import app
from app.schemas.auth import CurrentUser


@pytest.mark.anyio
async def test_roles_list_requires_roles_read_permission(client: AsyncClient):
    async def override_get_current_user():
        return CurrentUser(
            user_id="user-123",
            email="user@example.com",
            user_role="user",
            hierarchy_level=100,
            permissions=[],  # missing roles:read
        )

    async def override_get_db():
        yield AsyncMock()

    from app.core.dependencies import get_current_user, get_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch(
            "app.services.role_service.RoleService.list_roles",
            new=AsyncMock(return_value=[]),
        ):
            response = await client.get("/api/v1/roles")
        assert response.status_code == 403
        assert "roles:read" in response.json()["error"]
    finally:
        app.dependency_overrides = {}


@pytest.mark.anyio
async def test_roles_list_allows_with_roles_read_permission(client: AsyncClient):
    async def override_get_current_user():
        return CurrentUser(
            user_id="user-123",
            email="user@example.com",
            user_role="user",
            hierarchy_level=100,
            permissions=["roles:read"],
        )

    async def override_get_db():
        yield AsyncMock()

    from app.core.dependencies import get_current_user, get_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch(
            "app.services.role_service.RoleService.list_roles",
            new=AsyncMock(return_value=[]),
        ):
            response = await client.get("/api/v1/roles")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides = {}


@pytest.mark.anyio
async def test_permissions_list_requires_permissions_read_permission(client: AsyncClient):
    async def override_get_current_user():
        return CurrentUser(
            user_id="user-123",
            email="user@example.com",
            user_role="user",
            hierarchy_level=100,
            permissions=[],  # missing permissions:read
        )

    async def override_get_db():
        yield AsyncMock()

    from app.core.dependencies import get_current_user, get_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch(
            "app.services.permission_service.PermissionService.list_grouped_by_module",
            new=AsyncMock(return_value={}),
        ):
            response = await client.get("/api/v1/permissions")
        assert response.status_code == 403
        assert "permissions:read" in response.json()["error"]
    finally:
        app.dependency_overrides = {}


@pytest.mark.anyio
async def test_permissions_list_allows_with_permissions_read_permission(client: AsyncClient):
    async def override_get_current_user():
        return CurrentUser(
            user_id="user-123",
            email="user@example.com",
            user_role="user",
            hierarchy_level=100,
            permissions=["permissions:read"],
        )

    async def override_get_db():
        yield AsyncMock()

    from app.core.dependencies import get_current_user, get_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch(
            "app.services.permission_service.PermissionService.list_grouped_by_module",
            new=AsyncMock(return_value={}),
        ):
            response = await client.get("/api/v1/permissions")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides = {}

