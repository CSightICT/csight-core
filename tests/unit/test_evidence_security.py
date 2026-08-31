"""Evidence metadata stripping and malware-gate tests."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

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
