"""Pillow-backed evidence inspection tests."""

from __future__ import annotations

import hashlib
import struct
import zlib
from io import BytesIO

import pytest
from PIL import Image

from app.adapters.file_inspection import PillowImageInspector
from app.ports.file_inspection import (
    EmptyFileError,
    FileInspector,
    FileTooLargeError,
    ImageContentTypeMismatchError,
    ImagePixelLimitError,
    InvalidImageError,
    UnsupportedImageTypeError,
)

pytestmark = pytest.mark.unit


def _image_bytes(image_format: str, *, size: tuple[int, int] = (8, 6)) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, color=(25, 50, 75)).save(stream, format=image_format)
    return stream.getvalue()


def _animated_png_bytes() -> bytes:
    stream = BytesIO()
    first = Image.new("RGB", (8, 6), color=(25, 50, 75))
    second = Image.new("RGB", (8, 6), color=(75, 50, 25))
    first.save(
        stream,
        format="PNG",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
    )
    return stream.getvalue()


def _png_with_dimensions(*, width: int, height: int) -> bytes:
    payload = bytearray(_image_bytes("PNG"))
    ihdr_data = bytes(payload[16:29])
    updated_ihdr = struct.pack(">II", width, height) + ihdr_data[8:]
    payload[16:29] = updated_ihdr
    payload[29:33] = struct.pack(">I", zlib.crc32(b"IHDR" + updated_ihdr) & 0xFFFFFFFF)
    return bytes(payload)


def _png_with_truncated_srgb_chunk() -> bytes:
    payload = _image_bytes("PNG")
    malformed_chunk = (
        struct.pack(">I", 0) + b"sRGB" + struct.pack(">I", zlib.crc32(b"sRGB") & 0xFFFFFFFF)
    )
    return payload[:33] + malformed_chunk + payload[33:]


@pytest.mark.parametrize(
    ("image_format", "declared_type", "expected_format", "expected_extension"),
    [
        ("JPEG", "image/jpeg", "JPEG", "jpg"),
        ("PNG", "image/png", "PNG", "png"),
        ("WEBP", "image/webp", "WEBP", "webp"),
    ],
)
def test_inspector_decodes_supported_images_and_rewinds_stream(
    image_format: str,
    declared_type: str,
    expected_format: str,
    expected_extension: str,
) -> None:
    payload = _image_bytes(image_format)
    stream = BytesIO(payload)
    inspector = PillowImageInspector(max_bytes=1024 * 1024, max_pixels=1000)

    result = inspector.inspect(
        content=stream,
        filename=f"../../고객 사진.{expected_extension}",
        declared_content_type=declared_type,
    )

    assert isinstance(inspector, FileInspector)
    assert result.original_filename == f"고객_사진.{expected_extension}"
    assert result.image_format == expected_format
    assert result.extension == expected_extension
    assert result.content_type == declared_type
    assert result.size_bytes == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert (result.width, result.height) == (8, 6)
    assert stream.tell() == 0


def test_inspector_rejects_a_declared_content_type_mismatch() -> None:
    with pytest.raises(ImageContentTypeMismatchError):
        PillowImageInspector(max_bytes=10_000, max_pixels=1000).inspect(
            content=BytesIO(_image_bytes("PNG")),
            filename="photo.png",
            declared_content_type="image/jpeg; charset=binary",
        )


def test_inspector_rejects_unsupported_image_format() -> None:
    with pytest.raises(UnsupportedImageTypeError):
        PillowImageInspector(max_bytes=10_000, max_pixels=1000).inspect(
            content=BytesIO(_image_bytes("GIF")),
            filename="photo.gif",
            declared_content_type="image/gif",
        )


def test_inspector_rejects_truncated_image_after_actual_decode() -> None:
    payload = _image_bytes("JPEG")

    with pytest.raises(InvalidImageError):
        PillowImageInspector(max_bytes=10_000, max_pixels=1000).inspect(
            content=BytesIO(payload[:-20]),
            filename="photo.jpg",
            declared_content_type="image/jpeg",
        )


def test_inspector_maps_malformed_png_value_error_to_invalid_image() -> None:
    with pytest.raises(InvalidImageError):
        PillowImageInspector(max_bytes=10_000, max_pixels=1000).inspect(
            content=BytesIO(_png_with_truncated_srgb_chunk()),
            filename="photo.png",
            declared_content_type="image/png",
        )


def test_inspector_enforces_byte_limit_and_rewinds() -> None:
    stream = BytesIO(_image_bytes("PNG"))

    with pytest.raises(FileTooLargeError):
        PillowImageInspector(max_bytes=10, max_pixels=1000).inspect(
            content=stream,
            filename="photo.png",
            declared_content_type="image/png",
        )

    assert stream.tell() == 0


def test_inspector_enforces_pixel_limit_before_full_decode() -> None:
    with pytest.raises(ImagePixelLimitError):
        PillowImageInspector(max_bytes=10_000, max_pixels=99).inspect(
            content=BytesIO(_image_bytes("PNG", size=(10, 10))),
            filename="photo.png",
            declared_content_type="image/png",
        )


def test_inspector_maps_pillow_bomb_warning_to_configured_pixel_limit() -> None:
    with pytest.raises(ImagePixelLimitError):
        PillowImageInspector(max_bytes=20_000, max_pixels=40_000_000).inspect(
            content=BytesIO(_png_with_dimensions(width=10_000, height=10_000)),
            filename="large.png",
            declared_content_type="image/png",
        )


def test_inspector_maps_pillow_hard_bomb_error_to_pixel_limit() -> None:
    with pytest.raises(ImagePixelLimitError):
        PillowImageInspector(max_bytes=20_000, max_pixels=178_956_970).inspect(
            content=BytesIO(_png_with_dimensions(width=20_000, height=10_000)),
            filename="huge.png",
            declared_content_type="image/png",
        )


def test_inspector_rejects_animated_supported_image_format() -> None:
    with pytest.raises(UnsupportedImageTypeError, match="Animated"):
        PillowImageInspector(max_bytes=20_000, max_pixels=1000).inspect(
            content=BytesIO(_animated_png_bytes()),
            filename="animated.png",
            declared_content_type="image/png",
        )


def test_inspector_rejects_empty_content() -> None:
    with pytest.raises(EmptyFileError):
        PillowImageInspector(max_bytes=10_000, max_pixels=1000).inspect(
            content=BytesIO(),
            filename=None,
            declared_content_type=None,
        )


def test_inspector_rejects_disallowed_or_mismatched_filename_extensions() -> None:
    inspector = PillowImageInspector(max_bytes=10_000, max_pixels=1000)
    payload = _image_bytes("PNG")

    with pytest.raises(UnsupportedImageTypeError):
        inspector.inspect(
            content=BytesIO(payload),
            filename="photo.exe",
            declared_content_type="image/png",
        )
    with pytest.raises(ImageContentTypeMismatchError):
        inspector.inspect(
            content=BytesIO(payload),
            filename="photo.jpg",
            declared_content_type="image/png",
        )


def test_inspector_applies_configured_image_type_allowlists() -> None:
    inspector = PillowImageInspector(
        max_bytes=10_000,
        max_pixels=1000,
        allowed_mime_types=frozenset({"image/png"}),
        allowed_extensions=frozenset({"png"}),
    )

    with pytest.raises(UnsupportedImageTypeError):
        inspector.inspect(
            content=BytesIO(_image_bytes("JPEG")),
            filename="photo.jpg",
            declared_content_type="image/jpeg",
        )


@pytest.mark.parametrize(
    ("mime_types", "extensions"),
    [
        (frozenset(), frozenset({"png"})),
        (frozenset({"image/png"}), frozenset()),
    ],
)
def test_inspector_rejects_explicitly_empty_allowlists(
    mime_types: frozenset[str],
    extensions: frozenset[str],
) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        PillowImageInspector(
            max_bytes=10_000,
            max_pixels=1000,
            allowed_mime_types=mime_types,
            allowed_extensions=extensions,
        )
