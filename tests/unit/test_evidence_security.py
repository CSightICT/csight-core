"""Evidence metadata stripping and malware-gate tests."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, PngImagePlugin

from app.adapters.evidence_security import PillowImageSanitizer
from app.ports.evidence_security import MalwareDetectedError

pytestmark = pytest.mark.unit


class _RecordingScanner:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.payloads: list[bytes] = []

    def scan(self, content: bytes) -> None:
        self.payloads.append(content)
        if self.reject:
            raise MalwareDetectedError("rejected")


def _jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (3, 2), "red")
    metadata = image.getexif()
    metadata[0x0112] = 6  # rotate 90 degrees clockwise
    metadata[0x010E] = "private-description"
    output = BytesIO()
    image.save(output, format="JPEG", exif=metadata)
    image.close()
    return output.getvalue()


def test_sanitizer_scans_both_sides_applies_orientation_and_removes_exif() -> None:
    scanner = _RecordingScanner()
    sanitizer = PillowImageSanitizer(
        scanner=scanner,
        max_input_bytes=1024 * 1024,
        max_output_bytes=1024 * 1024,
        max_pixels=100,
    )

    result = sanitizer.sanitize(BytesIO(_jpeg_with_exif()))

    assert result.image_format == "JPEG"
    assert len(scanner.payloads) == 2
    assert scanner.payloads[1] == result.content
    with Image.open(BytesIO(result.content)) as image:
        assert image.size == (2, 3)
        assert len(image.getexif()) == 0
        assert "private-description" not in repr(image.info)


def test_sanitizer_stops_before_decoding_when_malware_scan_rejects() -> None:
    scanner = _RecordingScanner(reject=True)
    sanitizer = PillowImageSanitizer(
        scanner=scanner,
        max_input_bytes=1024,
        max_output_bytes=1024,
        max_pixels=100,
    )

    with pytest.raises(MalwareDetectedError):
        sanitizer.sanitize(BytesIO(b"not-an-image"))

    assert scanner.payloads == [b"not-an-image"]


@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP"])
def test_sanitizer_strips_source_metadata_for_every_supported_format(image_format: str) -> None:
    marker = b"SYNTHETIC_PRIVATE_METADATA"
    with Image.new("RGB", (3, 2), "red") as original:
        metadata = original.getexif()
        metadata[0x0112] = 6
        metadata[0x010E] = marker.decode()
        output = BytesIO()
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("Comment", marker.decode())
        original.save(
            output,
            format=image_format,
            exif=metadata,
            icc_profile=marker,
            xmp=marker,
            comment=marker,
            pnginfo=pnginfo,
        )
    raw = output.getvalue()
    with Image.open(BytesIO(raw)) as source:
        assert source.info.get("icc_profile") == marker
        assert source.getexif().get(0x010E) == marker.decode()
    scanner = _RecordingScanner()
    sanitizer = PillowImageSanitizer(
        scanner=scanner,
        max_input_bytes=1024 * 1024,
        max_output_bytes=1024 * 1024,
        max_pixels=100,
    )

    result = sanitizer.sanitize(BytesIO(raw))

    assert result.image_format == image_format
    assert scanner.payloads == [raw, result.content]
    assert marker not in result.content
    with Image.open(BytesIO(result.content)) as sanitized:
        assert sanitized.size == (2, 3)
        assert len(sanitized.getexif()) == 0
        assert not {"icc_profile", "exif", "xmp", "Comment", "comment"} & sanitized.info.keys()


@pytest.mark.parametrize("image_format", ["PNG", "WEBP"])
def test_sanitizer_preserves_alpha_and_orientation_without_source_metadata(
    image_format: str,
) -> None:
    pixels = [(255, 0, 0, 255), (0, 255, 0, 64), (0, 0, 255, 128)]
    with Image.new("RGBA", (3, 1)) as original:
        for column, pixel in enumerate(pixels):
            original.putpixel((column, 0), pixel)
        metadata = original.getexif()
        metadata[0x0112] = 6
        raw = BytesIO()
        original.save(raw, format=image_format, exif=metadata, lossless=True)
    sanitizer = PillowImageSanitizer(
        scanner=_RecordingScanner(),
        max_input_bytes=1024 * 1024,
        max_output_bytes=1024 * 1024,
        max_pixels=100,
    )

    result = sanitizer.sanitize(BytesIO(raw.getvalue()))

    with Image.open(BytesIO(result.content)) as sanitized:
        assert sanitized.mode == "RGBA"
        assert sanitized.size == (1, 3)
        assert [sanitized.getpixel((0, row)) for row in range(3)] == pixels
        assert len(sanitized.getexif()) == 0


def test_sanitizer_materializes_palette_transparency_before_removing_metadata() -> None:
    with Image.new("P", (2, 1)) as original:
        original.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
        original.putpixel((0, 0), 0)
        original.putpixel((1, 0), 1)
        raw = BytesIO()
        original.save(raw, format="PNG", transparency=0)
    sanitizer = PillowImageSanitizer(
        scanner=_RecordingScanner(),
        max_input_bytes=1024 * 1024,
        max_output_bytes=1024 * 1024,
        max_pixels=100,
    )

    result = sanitizer.sanitize(BytesIO(raw.getvalue()))

    with Image.open(BytesIO(result.content)) as sanitized:
        assert sanitized.mode == "RGBA"
        assert sanitized.getpixel((0, 0)) == (255, 0, 0, 0)
        assert sanitized.getpixel((1, 0)) == (0, 255, 0, 255)
        assert "transparency" not in sanitized.info
