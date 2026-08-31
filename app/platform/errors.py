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


class UnsafeEvidenceError(CSightError):
    code = "UNSAFE_EVIDENCE"
    default_message = "The uploaded evidence did not pass the security scan."


class EvidenceSecurityUnavailableError(CSightError):
    code = "EVIDENCE_SECURITY_UNAVAILABLE"
    default_message = "Evidence security scanning is temporarily unavailable."


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


class SensitivePayloadUnavailableError(CSightError):
    """The retained Case shell no longer has customer prose available for new work."""

    code = "SENSITIVE_PAYLOAD_UNAVAILABLE"
    default_message = "The customer inquiry is no longer available under its retention policy."


class OperationalFailureNotFoundError(CSightError):
    code = "OPERATIONAL_FAILURE_NOT_FOUND"
    default_message = "The requested operational failure was not found."


class OperationalFailureAlreadyResolvedError(CSightError):
    code = "OPERATIONAL_FAILURE_ALREADY_RESOLVED"
    default_message = "The operational failure already has a terminal recovery action."


class OperationalFailureNotReplayableError(CSightError):
    code = "OPERATIONAL_FAILURE_NOT_REPLAYABLE"
    default_message = "The operational failure cannot be replayed safely."
