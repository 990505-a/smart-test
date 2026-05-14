"""Custom exception hierarchy for the application.

Provides structured error types that map to HTTP status codes
for consistent error handling across FastAPI endpoints and
Agent tools.
"""


class AppException(Exception):
    """Base application exception with HTTP status code mapping.

    Attributes:
        status_code: HTTP status code.
        error: Error type identifier.
        message: Human-readable error message.
        details: Optional additional error details.
    """

    def __init__(
        self,
        status_code: int,
        error: str,
        message: str,
        details=None,
    ):
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found (404)."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            status_code=404,
            error="not_found",
            message=f"{resource} '{identifier}' not found",
        )


class ConflictException(AppException):
    """Resource conflict (409), e.g. duplicate unique constraint."""

    def __init__(self, message: str):
        super().__init__(
            status_code=409,
            error="conflict",
            message=message,
        )


class ValidationException(AppException):
    """Validation error (422)."""

    def __init__(self, message: str, details=None):
        super().__init__(
            status_code=422,
            error="validation_error",
            message=message,
            details=details,
        )
