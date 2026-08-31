"""Technology-neutral evidence sanitization and malware scanning boundaries."""

from dataclasses import dataclass
from typing import BinaryIO, Protocol, runtime_checkable

from app.ports.file_inspection import ImageFormat


class EvidenceSanitizationError(ValueError):
    """The uploaded evidence could not be safely normalized."""


class MalwareDetectedError(EvidenceSanitizationError):
    """A malware scanner rejected the uploaded content."""


class MalwareScannerUnavailableError(EvidenceSanitizationError):
    """The configured malware scanner did not return a trustworthy verdict."""


@dataclass(frozen=True, slots=True)
class SanitizedImage:
    content: bytes
    image_format: ImageFormat


@runtime_checkable
class MalwareScanner(Protocol):
    def scan(self, content: bytes) -> None:
        """Return only for a clean payload; otherwise raise a typed error."""
        ...


@runtime_checkable
class ImageSanitizer(Protocol):
    def sanitize(self, content: BinaryIO) -> SanitizedImage:
        """Return bounded, metadata-free, re-encoded image bytes."""
        ...


__all__ = [
    "EvidenceSanitizationError",
    "ImageSanitizer",
    "MalwareDetectedError",
    "MalwareScanner",
    "MalwareScannerUnavailableError",
    "SanitizedImage",
]
