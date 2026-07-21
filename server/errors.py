"""Domain exceptions for the server layer.

One small hierarchy so callers (and, later, the HTTP tier) can map failures to
outcomes without string-matching. Every exception carries a stable ``code``
suitable for an API error body and a default HTTP ``status`` so the future web
layer has a single, obvious mapping (``ServerError.status``) instead of a giant
``isinstance`` ladder.
"""
from __future__ import annotations


class ServerError(Exception):
    """Base class for every expected, caller-visible server failure.

    ``status`` is the HTTP status the future API tier should return; ``code``
    is a short machine-stable string for the error body. Unexpected bugs
    should raise ordinary exceptions, not subclasses of this — this hierarchy
    is only for the failures a well-behaved client can provoke.
    """

    status: int = 400
    code: str = "server_error"

    def __init__(self, message: str, *, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field  # set for validation errors that blame one field

    def to_dict(self) -> dict:
        """Serialise to the shape an API error body would use."""
        body = {"code": self.code, "message": self.message}
        if self.field is not None:
            body["field"] = self.field
        return body


class ValidationError(ServerError):
    """A field failed validation (bad email, weak password, …)."""

    status = 422
    code = "validation_error"


class AuthError(ServerError):
    """Authentication failed — bad credentials, or an unknown/expired token."""

    status = 401
    code = "auth_error"


class PermissionDenied(ServerError):
    """The caller is authenticated but not allowed to perform the action."""

    status = 403
    code = "permission_denied"


class NotFound(ServerError):
    """A referenced entity does not exist (or the caller can't see it)."""

    status = 404
    code = "not_found"


class Conflict(ServerError):
    """The request conflicts with existing state (duplicate email/slug, …)."""

    status = 409
    code = "conflict"
