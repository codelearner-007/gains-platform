"""Custom exception classes for the application."""

from typing import Any, Dict, Optional


class AppException(Exception):
    """Base exception class for application errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ResourceNotFoundError(AppException):
    """Raised when a requested resource is not found."""

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            message=f"{resource} with identifier '{identifier}' not found",
            status_code=404,
            details={"resource": resource, "identifier": identifier},
        )


class PermissionDeniedError(AppException):
    """Raised when user lacks required permission."""

    def __init__(self, required_permission: str, *, code: str | None = None) -> None:
        # Generic message in the response — never leak the specific permission name.
        # Store internally for server-side logging via AppException handler.
        super().__init__(
            message="Insufficient permissions",
            status_code=403,
            details={"code": code} if code else {},
        )
        # Available for server-side logging but NOT included in JSON response
        self._required_permission = required_permission


class LtiActionForbiddenError(AppException):
    """Raised when an LTI (Schoology-embedded) user attempts an action reserved
    for full platform accounts.

    LTI users get a locked, analytics-only experience (dashboard + reports).
    Account/profile mutation endpoints carry no permission of their own, so this
    closes the write boundary at the API even if the UI/middleware were bypassed.
    """

    def __init__(self) -> None:
        super().__init__(
            message="This action is not available for Schoology-integrated accounts",
            status_code=403,
        )


class InvalidTokenError(AppException):
    """Raised when JWT token is invalid or expired."""

    def __init__(self, reason: str = "Invalid or expired token") -> None:
        super().__init__(
            message=reason,
            status_code=401,
            details={"token_error": reason},
        )


class ValidationError(AppException):
    """Raised when data validation fails."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(
            message=message,
            status_code=422,
            details={"field": field} if field else {},
        )


class HierarchyViolationError(AppException):
    """Raised when an actor tries to act on a role or user that is senior to,
    or the same seniority as, its own role.

    Ranks are internal ordinals (lower = more senior) and are never surfaced —
    the message and details are numberless so authz internals don't leak.
    """

    def __init__(
        self, actor_rank: int, target_rank: int, message: Optional[str] = None
    ) -> None:
        super().__init__(
            message=message
            or (
                "You cannot manage a role or user that is senior to, or the "
                "same seniority as, your own role."
            ),
            status_code=403,
        )


class DuplicateResourceError(AppException):
    """Raised when attempting to create a duplicate resource."""

    def __init__(self, resource: str, field: str, value: str) -> None:
        super().__init__(
            message=f"{resource} with {field}='{value}' already exists",
            status_code=409,
            details={"resource": resource, "field": field, "value": value},
        )


class ImmutableResourceError(AppException):
    """Raised when attempting to modify immutable system resource."""

    def __init__(
        self,
        resource: str,
        identifier: str,
        reason: str = "System resource is immutable",
    ) -> None:
        super().__init__(
            message=f"Cannot modify {resource} '{identifier}': {reason}",
            status_code=403,
            details={
                "resource": resource,
                "identifier": identifier,
                "reason": reason,
            },
        )
