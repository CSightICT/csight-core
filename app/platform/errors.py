"""Technology-neutral errors exposed by CSight application use cases."""

from collections.abc import Mapping


class CSightError(Exception):
    """Base error carrying a stable public code and a non-sensitive message."""

    code = "CSIGHT_ERROR"
    default_message = "The request could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = dict(details or {})
        super().__init__(self.message)


class AuthenticationRequiredError(CSightError):
    code = "AUTHENTICATION_REQUIRED"
    default_message = "Authentication is required."


class InvalidCredentialsError(CSightError):
    code = "INVALID_CREDENTIALS"
    default_message = "The supplied credentials are invalid."


class ForbiddenError(CSightError):
    code = "FORBIDDEN"
    default_message = "The authenticated user is not allowed to perform this operation."


class CaseNotFoundError(CSightError):
    code = "CASE_NOT_FOUND"
    default_message = "The requested case was not found."


class EvidenceNotFoundError(CSightError):
    code = "EVIDENCE_NOT_FOUND"
    default_message = "The requested evidence was not found."


class InvalidFileTypeError(CSightError):
    code = "INVALID_FILE_TYPE"
    default_message = "The uploaded file type is not allowed."


class FileTooLargeError(CSightError):
    code = "FILE_TOO_LARGE"
    default_message = "The uploaded file exceeds the configured size limit."


class EmptyFileError(CSightError):
    code = "EMPTY_FILE"
    default_message = "The uploaded file is empty."


class InvalidImageContentError(CSightError):
    code = "INVALID_IMAGE_CONTENT"
    default_message = "The uploaded file is not a valid supported image."


class ImageDimensionLimitExceededError(CSightError):
    code = "IMAGE_DIMENSION_LIMIT_EXCEEDED"
    default_message = "The uploaded image exceeds the configured pixel limit."


class EvidenceUploadFailedError(CSightError):
    code = "EVIDENCE_UPLOAD_FAILED"
    default_message = "The evidence could not be stored."


class StorageUnavailableError(CSightError):
    code = "STORAGE_UNAVAILABLE"
    default_message = "Object storage is unavailable."


class IdempotencyKeyReusedError(CSightError):
    code = "IDEMPOTENCY_KEY_REUSED"
    default_message = "The idempotency key was already used with a different request."


class ValidationError(CSightError):
    code = "VALIDATION_ERROR"
    default_message = "The request is invalid."


class InconsistentPersistenceStateError(CSightError):
    """Raised when coordination metadata points at a missing resource."""

    code = "INCONSISTENT_PERSISTENCE_STATE"
    default_message = "The persisted resource state is inconsistent."
