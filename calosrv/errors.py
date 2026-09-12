"""Application error hierarchy, rendered to RFC 7807 ``application/problem+json``.

Routes raise these rather than ``HTTPException`` so that the message a physicist
sees names the actual problem - an unknown table, a colliding event range, a
resolution that would alias against the detector lattice - instead of a bare
status code.
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Base class for every error the API reports deliberately."""

    status_code: int = 500
    error_type: str = "internal-error"
    title: str = "Internal server error"

    def __init__(self, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra

    def to_problem(self) -> dict[str, Any]:
        problem: dict[str, Any] = {
            "type": f"/problems/{self.error_type}",
            "title": self.title,
            "status": self.status_code,
            "detail": self.detail,
        }
        problem.update(self.extra)
        return problem


class NotFoundError(ApiError):
    status_code = 404
    error_type = "not-found"
    title = "Resource not found"


class UnknownTableError(NotFoundError):
    error_type = "unknown-table"
    title = "Unknown experiment table"


class ValidationError(ApiError):
    status_code = 422
    error_type = "validation-error"
    title = "Invalid request parameters"


class ConflictError(ApiError):
    status_code = 409
    error_type = "conflict"
    title = "Request conflicts with existing state"


class EventRangeCollisionError(ConflictError):
    """Appending a file whose ``event_number`` range overlaps the target table.

    Ported from ``calodash/ingest.py``, which rejects the same situation in the
    batch pipeline. Merging two files that both number events from zero silently
    fuses distinct physics events into one, and every per-event aggregate
    downstream then describes something that never happened.
    """

    error_type = "event-range-collision"
    title = "Event number ranges overlap"


class IngestError(ApiError):
    status_code = 400
    error_type = "ingest-failed"
    title = "Dataset ingestion failed"


class InsufficientStorageError(ApiError):
    status_code = 507
    error_type = "insufficient-storage"
    title = "Not enough free disk space"


class ServiceUnavailableError(ApiError):
    status_code = 503
    error_type = "service-unavailable"
    title = "Service temporarily unavailable"
