"""Tests for role schemas and defaults."""

from app.schemas.request.role import CreateRoleRequest as RoleCreate


def test_role_create_defaults_hierarchy_to_zero():
    role = RoleCreate(name="test_role", description=None)
    assert role.hierarchy_level == 0


def test_role_create_allows_hierarchy_zero_explicit():
    role = RoleCreate(name="test_role2", hierarchy_level=0)
    assert role.hierarchy_level == 0

