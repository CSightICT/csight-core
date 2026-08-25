"""Bounded streaming SHA-256 adapter tests."""

import hashlib
from io import BytesIO

import pytest

from app.adapters.hashing import BoundedSha256Hasher
from app.ports.hashing import EmptyHashInputError, HashingPort, HashInputTooLargeError

pytestmark = pytest.mark.unit


def test_hasher_calculates_size_and_digest_and_rewinds() -> None:
    content = BytesIO(b"bounded evidence")
    hasher = BoundedSha256Hasher(max_bytes=1024)

    result = hasher.calculate(content)

    assert isinstance(hasher, HashingPort)
    assert result.size_bytes == len(b"bounded evidence")
    assert result.sha256 == hashlib.sha256(b"bounded evidence").hexdigest()
    assert content.tell() == 0


def test_hasher_rejects_empty_and_oversized_streams_and_rewinds() -> None:
    with pytest.raises(EmptyHashInputError):
        BoundedSha256Hasher(max_bytes=10).calculate(BytesIO())
    oversized = BytesIO(b"12345")
    with pytest.raises(HashInputTooLargeError):
        BoundedSha256Hasher(max_bytes=4).calculate(oversized)
    assert oversized.tell() == 0
