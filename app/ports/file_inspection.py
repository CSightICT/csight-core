"""Technology-neutral boundary for validating uploaded evidence files."""

from dataclasses import dataclass
from typing import BinaryIO, Literal, Protocol, runtime_checkable

ImageFormat = Literal["JPEG", "PNG", "WEBP"]


class FileInspectionError(ValueError):
    """Base error carrying a stable, interface-safe failure code."""

    code = "FILE_INSPECTION_FAILED"


class FileTooLargeError(FileInspectionError):
    code = "FILE_TOO_LARGE"


class EmptyFileError(FileInspectionError):
    code = "EMPTY_FILE"


class InvalidImageError(FileInspectionError):
    code = "INVALID_IMAGE"


class UnsupportedImageTypeError(FileInspectionError):
    code = "UNSUPPORTED_IMAGE_TYPE"


class ImagePixelLimitError(FileInspectionError):
    code = "IMAGE_PIXEL_LIMIT_EXCEEDED"


class ImageContentTypeMismatchError(FileInspectionError):
    code = "IMAGE_CONTENT_TYPE_MISMATCH"


@dataclass(frozen=True, slots=True)
class ImageInspectionResult:
    """Validated metadata safe to persist alongside a private object key."""

    original_filename: str
    image_format: ImageFormat
    extension: str
    content_type: str
    size_bytes: int
    sha256: str
    width: int
    height: int


@runtime_checkable
class FileInspector(Protocol):
    def inspect(
        self,
        *,
        content: BinaryIO,
        filename: str | None,
        declared_content_type: str | None,
    ) -> ImageInspectionResult:
        """Validate a seekable upload and leave it rewound for storage."""
        ...
