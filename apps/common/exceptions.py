"""Stable, machine-readable domain exceptions."""

from __future__ import annotations

from typing import Any


class KoraError(Exception):
    """Base class for expected, domain-level failures.

    Each error carries a stable ``code`` so API responses and logs do not
    depend on human-readable message text.
    """

    code = "kora_error"
    http_status = 400

    def __init__(self, message: str = "", **context: Any) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.context = context

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": self.context}


class ValidationError(KoraError):
    code = "validation_error"


class NotFoundError(KoraError):
    code = "not_found"
    http_status = 404


class PermissionDeniedError(KoraError):
    code = "permission_denied"
    http_status = 403


class TenantIsolationError(KoraError):
    """Raised when related records span more than one organisation."""

    code = "tenant_isolation_violation"
    http_status = 409


class InvalidTransitionError(KoraError):
    """Raised when an interaction state transition is not permitted."""

    code = "invalid_transition"
    http_status = 409


class DuplicateEventError(KoraError):
    """Raised when an event has already been applied for its provider scope."""

    code = "duplicate_event"
    http_status = 200
