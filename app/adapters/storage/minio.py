"""Private MinIO object storage with a separate client-facing presign endpoint."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import timedelta
from typing import BinaryIO, Protocol, cast

from minio import Minio
from minio.error import S3Error
from urllib3 import PoolManager, Timeout

from app.ports.storage import StoredObject

_MAX_PRESIGN_TTL = timedelta(days=7)
_MISSING_OBJECT_CODES = frozenset({"NoSuchKey", "NoSuchObject", "NotFound"})
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_SHA256_METADATA_HEADER = "x-amz-meta-sha256"


class StoredObjectIntegrityError(RuntimeError):
    """Raised when MinIO's post-write metadata differs from the upload contract."""


class _ObjectStat(Protocol):
    @property
    def size(self) -> int | None: ...

    @property
    def content_type(self) -> str | None: ...

    @property
    def metadata(self) -> Mapping[str, object] | None: ...


class _MinioClient(Protocol):
    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> object: ...

    def stat_object(self, bucket_name: str, object_name: str) -> _ObjectStat: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...

    def presigned_get_object(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = _MAX_PRESIGN_TTL,
    ) -> str: ...

    def bucket_exists(self, bucket_name: str) -> bool: ...


class MinioObjectStorage:
    """Store private evidence through internal DNS and sign URLs for public DNS."""

    def __init__(
        self,
        *,
        endpoint: str,
        presigned_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
        secure: bool,
        presigned_secure: bool,
        timeout_seconds: float,
        internal_client: _MinioClient | None = None,
        presign_client: _MinioClient | None = None,
    ) -> None:
        if not endpoint or not presigned_endpoint:
            raise ValueError("MinIO endpoints must not be empty")
        if not access_key or not secret_key:
            raise ValueError("MinIO credentials must not be empty")
        if not bucket or not region:
            raise ValueError("MinIO bucket and region must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._bucket = bucket
        self._internal_client = internal_client or _build_client(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            secure=secure,
            timeout_seconds=timeout_seconds,
        )
        if presign_client is not None:
            self._presign_client = presign_client
        elif presigned_endpoint == endpoint and presigned_secure is secure:
            self._presign_client = self._internal_client
        else:
            self._presign_client = _build_client(
                endpoint=presigned_endpoint,
                access_key=access_key,
                secret_key=secret_key,
                region=region,
                secure=presigned_secure,
                timeout_seconds=timeout_seconds,
            )

    @property
    def bucket(self) -> str:
        return self._bucket

    def put(
        self,
        *,
        key: str,
        content: BinaryIO,
        length: int,
        content_type: str,
        sha256: str,
    ) -> StoredObject:
        _validate_object_key(key)
        if length < 0:
            raise ValueError("Object length must not be negative")
        if not content_type.strip():
            raise ValueError("Object content type must not be empty")
        if _SHA256_PATTERN.fullmatch(sha256) is None:
            raise ValueError("Object SHA-256 must be 64 lowercase hexadecimal characters")

        self._internal_client.put_object(
            self._bucket,
            key,
            content,
            length,
            content_type=content_type,
            metadata={"sha256": sha256},
        )
        stat = self._internal_client.stat_object(self._bucket, key)
        stored_sha256 = _sha256_from_metadata(stat.metadata)
        if (
            stat.size != length
            or _normalized_content_type(stat.content_type) != _normalized_content_type(content_type)
            or stored_sha256 != sha256
        ):
            raise StoredObjectIntegrityError(
                "Stored object metadata did not match the requested upload."
            )
        return StoredObject(
            bucket=self._bucket,
            key=key,
            content_type=stat.content_type or content_type,
            size_bytes=stat.size if stat.size is not None else length,
            sha256=stored_sha256 or sha256,
        )

    def delete(self, key: str) -> None:
        _validate_object_key(key)
        self._internal_client.remove_object(self._bucket, key)

    def exists(self, key: str) -> bool:
        _validate_object_key(key)
        try:
            self._internal_client.stat_object(self._bucket, key)
        except S3Error as exc:
            if exc.code in _MISSING_OBJECT_CODES:
                return False
            raise
        return True

    def presign_get(self, key: str, *, expires_in: timedelta) -> str:
        _validate_object_key(key)
        if expires_in <= timedelta(0) or expires_in > _MAX_PRESIGN_TTL:
            raise ValueError("Presigned URL expiry must be between 1 second and 7 days")
        return self._presign_client.presigned_get_object(
            self._bucket,
            key,
            expires=expires_in,
        )

    def is_ready(self) -> bool:
        return self._internal_client.bucket_exists(self._bucket)


def _build_client(
    *,
    endpoint: str,
    access_key: str,
    secret_key: str,
    region: str,
    secure: bool,
    timeout_seconds: float,
) -> _MinioClient:
    http_client = PoolManager(
        timeout=Timeout(connect=timeout_seconds, read=timeout_seconds),
        retries=False,
    )
    return cast(
        _MinioClient,
        Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            secure=secure,
            http_client=http_client,
        ),
    )


def _validate_object_key(key: str) -> None:
    if not key or key.startswith("/") or "\x00" in key:
        raise ValueError("Object key is invalid")
    parts = key.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Object key contains an unsafe path segment")


def _normalized_content_type(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().casefold()


def _sha256_from_metadata(metadata: Mapping[str, object] | None) -> str | None:
    if metadata is None:
        return None
    for key, value in metadata.items():
        if key.casefold() == _SHA256_METADATA_HEADER and isinstance(value, str):
            return value.strip()
    return None
