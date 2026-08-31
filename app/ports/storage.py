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


@dataclass(frozen=True, slots=True)
class ObjectInventoryPage:
    """Bounded object listing used only by explicit consistency jobs."""

    keys: tuple[str, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class StoredObjectVersion:
    """Opaque object version metadata without payload or credentials."""

    key: str
    version_id: str | None
    is_delete_marker: bool


@dataclass(frozen=True, slots=True)
class ObjectVersionInventoryPage:
    versions: tuple[StoredObjectVersion, ...]
    truncated: bool


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


@runtime_checkable
class EvidenceObjectInventory(Protocol):
    """Read-only private-object metadata inventory for reconciliation."""

    def stat(self, key: str) -> StoredObject | None:
        """Return safe object metadata or ``None`` when the key is absent."""
        ...

    def list_keys(self, *, prefix: str, limit: int) -> ObjectInventoryPage:
        """List at most ``limit`` opaque keys and report truncation."""
        ...


@runtime_checkable
class VersionedObjectLifecycle(Protocol):
    """Exact-version inventory and deletion for privacy erasure."""

    def list_versions(self, *, key: str, limit: int) -> ObjectVersionInventoryPage:
        """List every recoverable version and delete marker for one exact key."""
        ...

    def delete_version(self, *, key: str, version_id: str | None) -> None:
        """Permanently remove one exact version instead of adding a delete marker."""
        ...
