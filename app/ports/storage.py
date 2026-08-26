"""Technology-neutral private object-storage boundary."""

from dataclasses import dataclass
from datetime import timedelta
from typing import BinaryIO, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class StoredObject:
    bucket: str
    key: str
    content_type: str
    size_bytes: int
    sha256: str

    @property
    def checksum(self) -> str:
        """Backward-compatible name for the canonical SHA-256 digest."""

        return self.sha256


@runtime_checkable
class ObjectStorage(Protocol):
    def put(
        self,
        *,
        key: str,
        content: BinaryIO,
        length: int,
        content_type: str,
        sha256: str,
    ) -> StoredObject:
        """Store an object and return non-secret metadata."""
        ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def presign_get(self, key: str, *, expires_in: timedelta) -> str:
        """Return a temporary private-object download URL."""
        ...

    def is_ready(self) -> bool: ...


@runtime_checkable
class ReadableObjectStorage(ObjectStorage, Protocol):
    def get(self, key: str, *, max_bytes: int) -> bytes:
        """Read a bounded private object without creating a signed URL."""
        ...
