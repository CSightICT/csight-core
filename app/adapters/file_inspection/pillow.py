"""Pillow-backed, bounded inspection for image evidence uploads."""

from __future__ import annotations

import re
import unicodedata
import warnings
from typing import BinaryIO, Final

from PIL import Image, UnidentifiedImageError

from app.adapters.hashing import BoundedSha256Hasher
from app.ports.file_inspection import (
    EmptyFileError,
    FileInspectionError,
    FileTooLargeError,
    ImageContentTypeMismatchError,
    ImageFormat,
    ImageInspectionResult,
    ImagePixelLimitError,
    InvalidImageError,
    UnsupportedImageTypeError,
)
from app.ports.hashing import (
    EmptyHashInputError,
    HashingError,
    HashingPort,
    HashInputTooLargeError,
    UnreadableHashInputError,
)

_MAX_FILENAME_STEM_LENGTH: Final = 100
_PILLOW_HARD_PIXEL_LIMIT: Final = 178_956_970
_FORMAT_METADATA: Final[dict[ImageFormat, tuple[str, str, frozenset[str]]]] = {
    "JPEG": ("jpg", "image/jpeg", frozenset({"image/jpeg", "image/jpg", "image/pjpeg"})),
    "PNG": ("png", "image/png", frozenset({"image/png", "image/x-png"})),
    "WEBP": ("webp", "image/webp", frozenset({"image/webp"})),
}


class PillowImageInspector:
    """Validate, fully decode, hash, and normalize a seekable image upload."""

    def __init__(
        self,
        *,
        max_bytes: int,
        max_pixels: int,
        allowed_mime_types: frozenset[str] | None = None,
        allowed_extensions: frozenset[str] | None = None,
        hasher: HashingPort | None = None,
    ) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if max_pixels < 1:
            raise ValueError("max_pixels must be positive")
        if max_pixels > _PILLOW_HARD_PIXEL_LIMIT:
            raise ValueError(
                f"max_pixels must not exceed Pillow's {_PILLOW_HARD_PIXEL_LIMIT}-pixel hard limit"
            )
        self._max_bytes = max_bytes
        self._max_pixels = max_pixels
        self._hasher = hasher or BoundedSha256Hasher(max_bytes=max_bytes)
        configured_mime_types = (
            frozenset({"image/jpeg", "image/png", "image/webp"})
            if allowed_mime_types is None
            else allowed_mime_types
        )
        configured_extensions = (
            frozenset({"jpg", "jpeg", "png", "webp"})
            if allowed_extensions is None
            else allowed_extensions
        )
        self._allowed_mime_types = frozenset(
            value.strip().casefold() for value in configured_mime_types if value.strip()
        )
        self._allowed_extensions = frozenset(
            value.strip().casefold().lstrip(".")
            for value in configured_extensions
            if value.strip().lstrip(".")
        )
        if not self._allowed_mime_types or not self._allowed_extensions:
            raise ValueError("allowed image types must not be empty")

    def inspect(
        self,
        *,
        content: BinaryIO,
        filename: str | None,
        declared_content_type: str | None,
    ) -> ImageInspectionResult:
        size_bytes, sha256 = self._hash(content)
        try:
            image_format, width, height = self._decode_and_validate(content)
            extension, content_type, accepted_content_types = _FORMAT_METADATA[image_format]
            self._validate_allowed_format(
                content_type=content_type,
                canonical_extension=extension,
                filename=filename,
            )
            self._validate_declared_content_type(
                declared_content_type,
                accepted_content_types=accepted_content_types,
            )
            return ImageInspectionResult(
                original_filename=_normalize_filename(filename, extension=extension),
                image_format=image_format,
                extension=extension,
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=sha256,
                width=width,
                height=height,
            )
        finally:
            self._rewind(content)

    def _hash(self, content: BinaryIO) -> tuple[int, str]:
        try:
            result = self._hasher.calculate(content)
        except HashInputTooLargeError as exc:
            raise FileTooLargeError(
                f"Image exceeds the configured {self._max_bytes}-byte limit"
            ) from exc
        except EmptyHashInputError as exc:
            raise EmptyFileError("Uploaded image is empty") from exc
        except UnreadableHashInputError as exc:
            raise InvalidImageError("Uploaded image could not be read") from exc
        except HashingError as exc:
            raise InvalidImageError("Uploaded image could not be hashed") from exc
        return result.size_bytes, result.sha256

    def _decode_and_validate(self, content: BinaryIO) -> tuple[ImageFormat, int, int]:
        try:
            with warnings.catch_warnings():
                # The configured project limit is checked immediately after open.
                # Pillow's lower warning threshold would otherwise override a valid
                # MAX_IMAGE_PIXELS setting; its hard error remains a safety backstop.
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                self._rewind(content)
                with Image.open(content) as image:
                    image_format = _supported_format(image.format)
                    width, height = image.size
                    self._validate_dimensions(width, height)
                    if int(getattr(image, "n_frames", 1)) != 1:
                        raise UnsupportedImageTypeError(
                            "Animated or multi-frame images are not allowed"
                        )
                    image.verify()

                self._rewind(content)
                with Image.open(content) as decoded:
                    decoded_format = _supported_format(decoded.format)
                    if decoded_format != image_format or decoded.size != (width, height):
                        raise InvalidImageError("Image metadata changed while decoding")
                    decoded.load()
        except FileInspectionError:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ImagePixelLimitError(
                f"Image exceeds the configured {self._max_pixels}-pixel limit"
            ) from exc
        except (
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            ValueError,
        ) as exc:
            raise InvalidImageError("Uploaded file is not a valid decodable image") from exc
        return image_format, width, height

    def _validate_dimensions(self, width: int, height: int) -> None:
        if width < 1 or height < 1:
            raise InvalidImageError("Image dimensions must be positive")
        pixels = width * height
        if pixels > self._max_pixels:
            raise ImagePixelLimitError(
                f"Image exceeds the configured {self._max_pixels}-pixel limit"
            )

    def _validate_allowed_format(
        self,
        *,
        content_type: str,
        canonical_extension: str,
        filename: str | None,
    ) -> None:
        if content_type.casefold() not in self._allowed_mime_types:
            raise UnsupportedImageTypeError("Decoded image MIME type is not allowed")

        supplied_extension = _filename_extension(filename)
        if supplied_extension is None or supplied_extension not in self._allowed_extensions:
            raise UnsupportedImageTypeError("Image filename extension is not allowed")
        equivalent_extensions = {canonical_extension}
        if canonical_extension == "jpg":
            equivalent_extensions.add("jpeg")
        if supplied_extension not in equivalent_extensions:
            raise ImageContentTypeMismatchError(
                "Filename extension does not match the decoded image format"
            )

    def _validate_declared_content_type(
        self,
        declared_content_type: str | None,
        *,
        accepted_content_types: frozenset[str],
    ) -> None:
        if declared_content_type is None or not declared_content_type.strip():
            return
        normalized = declared_content_type.partition(";")[0].strip().casefold()
        if normalized not in accepted_content_types or normalized not in self._allowed_mime_types:
            raise ImageContentTypeMismatchError(
                "Declared content type does not match the decoded image format"
            )

    @staticmethod
    def _rewind(content: BinaryIO) -> None:
        try:
            content.seek(0)
        except (OSError, ValueError) as exc:
            raise InvalidImageError("Uploaded image must be seekable") from exc


def _supported_format(value: str | None) -> ImageFormat:
    normalized = (value or "").upper()
    if normalized not in _FORMAT_METADATA:
        raise UnsupportedImageTypeError("Only JPEG, PNG, and WebP images are allowed")
    return normalized


def _normalize_filename(filename: str | None, *, extension: str) -> str:
    normalized = unicodedata.normalize("NFKC", filename or "")
    leaf = normalized.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    stem = leaf.rsplit(".", maxsplit=1)[0] if "." in leaf else leaf
    safe_stem = "".join(
        character if character.isalnum() or character in "-_" else "_" for character in stem
    )
    safe_stem = re.sub(r"_+", "_", safe_stem).strip("_-")
    safe_stem = safe_stem[:_MAX_FILENAME_STEM_LENGTH].rstrip("_-") or "upload"
    return f"{safe_stem}.{extension}"


def _filename_extension(filename: str | None) -> str | None:
    normalized = unicodedata.normalize("NFKC", filename or "")
    leaf = normalized.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    if "." not in leaf:
        return None
    extension = leaf.rsplit(".", maxsplit=1)[-1].strip().casefold()
    return extension or None
