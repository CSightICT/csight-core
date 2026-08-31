"""Pillow-backed metadata stripping and deterministic image re-encoding."""

from __future__ import annotations

from io import BytesIO
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.ports.evidence_security import (
    EvidenceSanitizationError,
    MalwareScanner,
    SanitizedImage,
)
from app.ports.file_inspection import ImageFormat

_SUPPORTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class NoopMalwareScanner:
    """Network-free scanner used only by local and test sanitization profiles."""

    def scan(self, content: bytes) -> None:
        del content


class PillowImageSanitizer:
    """Scan, orient, strip metadata, and re-encode one bounded still image."""

    def __init__(
        self,
        *,
        scanner: MalwareScanner,
        max_input_bytes: int,
        max_output_bytes: int,
        max_pixels: int,
    ) -> None:
        if min(max_input_bytes, max_output_bytes, max_pixels) < 1:
            raise ValueError("image sanitizer limits must be positive")
        self._scanner = scanner
        self._max_input_bytes = max_input_bytes
        self._max_output_bytes = max_output_bytes
        self._max_pixels = max_pixels

    def sanitize(self, content: BinaryIO) -> SanitizedImage:
        try:
            content.seek(0)
            raw = content.read(self._max_input_bytes + 1)
            content.seek(0)
        except (OSError, ValueError) as error:
            raise EvidenceSanitizationError("The uploaded image must be seekable.") from error
        if not raw or len(raw) > self._max_input_bytes:
            raise EvidenceSanitizationError("The uploaded image size is invalid.")

        self._scanner.scan(raw)
        try:
            with Image.open(BytesIO(raw)) as source:
                image_format = _image_format(source.format)
                if int(getattr(source, "n_frames", 1)) != 1:
                    raise EvidenceSanitizationError("Animated images are not accepted.")
                if source.width * source.height > self._max_pixels:
                    raise EvidenceSanitizationError("The uploaded image exceeds the pixel limit.")
                source.load()
                normalized = ImageOps.exif_transpose(source)
                try:
                    rendered = _renderable_image(normalized, image_format=image_format)
                    try:
                        output = BytesIO()
                        _save(rendered, output=output, image_format=image_format)
                        encoded = output.getvalue()
                    finally:
                        if rendered is not normalized:
                            rendered.close()
                finally:
                    if normalized is not source:
                        normalized.close()
        except EvidenceSanitizationError:
            raise
        except (
            Image.DecompressionBombError,
            UnidentifiedImageError,
            OSError,
            SyntaxError,
        ) as error:
            raise EvidenceSanitizationError("The uploaded image could not be sanitized.") from error

        if not encoded or len(encoded) > self._max_output_bytes:
            raise EvidenceSanitizationError("The sanitized image exceeds the storage limit.")
        self._scanner.scan(encoded)
        return SanitizedImage(content=encoded, image_format=image_format)


def _image_format(value: str | None) -> ImageFormat:
    normalized = (value or "").upper()
    if normalized not in _SUPPORTED_FORMATS:
        raise EvidenceSanitizationError("The uploaded image format is not supported.")
    return normalized  # type: ignore[return-value]


def _renderable_image(image: Image.Image, *, image_format: ImageFormat) -> Image.Image:
    has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
    if image_format == "JPEG":
        if has_alpha:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            rgba.close()
            return background
        return image.convert("RGB")
    return image.convert("RGBA" if has_alpha else "RGB")


def _save(image: Image.Image, *, output: BytesIO, image_format: ImageFormat) -> None:
    if image_format == "JPEG":
        image.save(
            output,
            format="JPEG",
            quality=92,
            optimize=False,
            progressive=False,
            exif=b"",
        )
    elif image_format == "PNG":
        image.save(output, format="PNG", optimize=False, compress_level=6)
    else:
        image.save(output, format="WEBP", lossless=True, method=4, exif=b"", xmp=b"")


__all__ = ["NoopMalwareScanner", "PillowImageSanitizer"]
