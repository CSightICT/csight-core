"""Technology-neutral boundary for bounded streaming file digests."""

from dataclasses import dataclass
from typing import BinaryIO, Protocol, runtime_checkable


class HashingError(ValueError):
    """Base failure raised by a file hashing adapter."""


class HashInputTooLargeError(HashingError):
    """The stream exceeded the configured byte limit."""


class EmptyHashInputError(HashingError):
    """The stream contained no bytes."""


class UnreadableHashInputError(HashingError):
    """The stream could not be read or rewound safely."""


@dataclass(frozen=True, slots=True)
class FileDigest:
    size_bytes: int
    sha256: str


@runtime_checkable
class HashingPort(Protocol):
    def calculate(self, content: BinaryIO) -> FileDigest:
        """Hash one bounded stream and leave it rewound for the next adapter."""
        ...
