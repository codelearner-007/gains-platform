"""Regression tests for user role schemas."""

from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas.response.role import RoleResponse
from app.schemas.response.user_role import UserRoleResponse


@dataclass
class _RoleObj:
    id: str
    name: str
    description: str | None
    hierarchy_level: int
    created_at: datetime
    updated_at: datetime


@dataclass
class _UserRoleObj:
    id: str
    user_id: str
    role_id: str
    role: _RoleObj
    created_at: datetime


def test_user_role_response_does_not_require_updated_at():
    """UserRole table uses created_at only; response must not require updated_at."""

    now = datetime.now(timezone.utc)
    role = _RoleObj(
        id="role-1",
        name="user",
        description=None,
        hierarchy_level=100,
        created_at=now,
        updated_at=now,
    )
    user_role = _UserRoleObj(
        id="ur-1",
        user_id="user-1",
        role_id="role-1",
        role=role,
        created_at=now,
    )

    model = UserRoleResponse.model_validate(user_role)
    assert model.id == "ur-1"
    assert model.user_id == "user-1"
    assert model.role_id == "role-1"
    assert isinstance(model.role, RoleResponse)
    assert model.created_at == now

