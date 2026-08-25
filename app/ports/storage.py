"""Minimal object-storage port for future evidence use cases."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    content_type: str
    size_bytes: int
    checksum: str


@runtime_checkable
class ObjectStorage(Protocol):
    def put(self, *, key: str, content: bytes, content_type: str) -> StoredObject:
        """Store an object and return non-secret metadata."""
        ...

    def exists(self, key: str) -> bool: ...

    def is_ready(self) -> bool: ...
