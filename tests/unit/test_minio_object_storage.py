"""MinIO object adapter tests without network access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from typing import BinaryIO

import pytest
from minio.error import S3Error
from urllib3.response import HTTPResponse

from app.adapters.storage import MinioObjectStorage, StoredObjectIntegrityError
from app.ports.storage import ObjectStorage

pytestmark = pytest.mark.unit


@dataclass(frozen=True, slots=True)
class FakeObjectStat:
    size: int | None
    content_type: str | None
    metadata: dict[str, object] | None


class FakeMinioClient:
    def __init__(self) -> None:
        self.objects: set[tuple[str, str]] = set()
        self.object_stats: dict[tuple[str, str], FakeObjectStat] = {}
        self.put_calls: list[tuple[str, str, bytes, int, str, dict[str, str] | None]] = []
        self.stat_calls: list[tuple[str, str]] = []
        self.remove_calls: list[tuple[str, str]] = []
        self.presign_calls: list[tuple[str, str, timedelta]] = []
        self.bucket_ready = True
        self.stat_error: S3Error | None = None
        self.stat_override: FakeObjectStat | None = None

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> object:
        payload = data.read()
        self.put_calls.append((bucket_name, object_name, payload, length, content_type, metadata))
        self.objects.add((bucket_name, object_name))
        self.object_stats[(bucket_name, object_name)] = FakeObjectStat(
            size=length,
            content_type=content_type,
            metadata={
                "x-amz-meta-sha256": metadata["sha256"]
                if metadata is not None and "sha256" in metadata
                else ""
            },
        )
        return object()

    def stat_object(self, bucket_name: str, object_name: str) -> FakeObjectStat:
        self.stat_calls.append((bucket_name, object_name))
        if self.stat_error is not None:
            raise self.stat_error
        if self.stat_override is not None:
            return self.stat_override
        if (bucket_name, object_name) not in self.objects:
            raise _s3_error("NoSuchKey")
        return self.object_stats.get(
            (bucket_name, object_name),
            FakeObjectStat(size=0, content_type=None, metadata=None),
        )

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self.remove_calls.append((bucket_name, object_name))
        self.objects.discard((bucket_name, object_name))
        self.object_stats.pop((bucket_name, object_name), None)

    def presigned_get_object(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(days=7),
    ) -> str:
        self.presign_calls.append((bucket_name, object_name, expires))
        return f"http://public.example/{bucket_name}/{object_name}?signature=redacted"

    def bucket_exists(self, bucket_name: str) -> bool:
        return self.bucket_ready and bucket_name == "evidence"


def _s3_error(code: str) -> S3Error:
    return S3Error(
        HTTPResponse(status=404),
        code,
        "sanitized",
        "resource",
        "request-id",
        "host-id",
    )


def _storage(
    internal: FakeMinioClient,
    presign: FakeMinioClient | None = None,
) -> MinioObjectStorage:
    return MinioObjectStorage(
        endpoint="minio:9000",
        presigned_endpoint="public.example:443",
        access_key="access",
        secret_key="secret",
        bucket="evidence",
        region="us-east-1",
        secure=False,
        presigned_secure=True,
        timeout_seconds=2,
        internal_client=internal,
        presign_client=presign or internal,
    )


def test_put_streams_to_internal_client_and_returns_persistable_metadata() -> None:
    internal = FakeMinioClient()
    storage = _storage(internal)
    payload = b"validated-image"
    digest = "a" * 64

    result = storage.put(
        key="tenant/case/evidence.jpg",
        content=BytesIO(payload),
        length=len(payload),
        content_type="image/jpeg",
        sha256=digest,
    )

    assert result.bucket == "evidence"
    assert isinstance(storage, ObjectStorage)
    assert result.key == "tenant/case/evidence.jpg"
    assert result.size_bytes == len(payload)
    assert result.sha256 == digest
    assert result.checksum == digest
    assert internal.put_calls == [
        (
            "evidence",
            "tenant/case/evidence.jpg",
            payload,
            len(payload),
            "image/jpeg",
            {"sha256": digest},
        )
    ]
    assert internal.stat_calls == [("evidence", "tenant/case/evidence.jpg")]


@pytest.mark.parametrize(
    "stat",
    [
        FakeObjectStat(
            size=1,
            content_type="image/jpeg",
            metadata={"x-amz-meta-sha256": "a" * 64},
        ),
        FakeObjectStat(
            size=len(b"validated-image"),
            content_type="image/png",
            metadata={"x-amz-meta-sha256": "a" * 64},
        ),
        FakeObjectStat(
            size=len(b"validated-image"),
            content_type="image/jpeg",
            metadata={"x-amz-meta-sha256": "b" * 64},
        ),
        FakeObjectStat(
            size=len(b"validated-image"),
            content_type="image/jpeg",
            metadata=None,
        ),
    ],
    ids=["size", "content-type", "sha256", "missing-sha256"],
)
def test_put_rejects_mismatched_post_write_metadata(stat: FakeObjectStat) -> None:
    internal = FakeMinioClient()
    internal.stat_override = stat

    with pytest.raises(StoredObjectIntegrityError, match="metadata did not match"):
        _storage(internal).put(
            key="tenant/case/evidence.jpg",
            content=BytesIO(b"validated-image"),
            length=len(b"validated-image"),
            content_type="image/jpeg",
            sha256="a" * 64,
        )

    assert internal.objects == {("evidence", "tenant/case/evidence.jpg")}


def test_exists_and_delete_use_internal_client() -> None:
    internal = FakeMinioClient()
    storage = _storage(internal)
    internal.objects.add(("evidence", "tenant/case/evidence.png"))

    assert storage.exists("tenant/case/evidence.png") is True
    storage.delete("tenant/case/evidence.png")
    assert storage.exists("tenant/case/evidence.png") is False
    assert internal.remove_calls == [("evidence", "tenant/case/evidence.png")]


def test_exists_only_suppresses_missing_object_errors() -> None:
    internal = FakeMinioClient()
    storage = _storage(internal)
    internal.stat_error = _s3_error("AccessDenied")

    with pytest.raises(S3Error, match="AccessDenied"):
        storage.exists("tenant/case/evidence.png")


def test_presign_uses_separate_client_facing_endpoint_client() -> None:
    internal = FakeMinioClient()
    public = FakeMinioClient()
    storage = _storage(internal, public)
    expiry = timedelta(minutes=15)

    url = storage.presign_get("tenant/case/evidence.webp", expires_in=expiry)

    assert url.startswith("http://public.example/")
    assert public.presign_calls == [("evidence", "tenant/case/evidence.webp", expiry)]
    assert internal.presign_calls == []


def test_real_presigner_uses_public_endpoint_without_contacting_minio() -> None:
    storage = MinioObjectStorage(
        endpoint="minio:9000",
        presigned_endpoint="evidence.example.test:443",
        access_key="access",
        secret_key="secret",
        bucket="evidence",
        region="us-east-1",
        secure=False,
        presigned_secure=True,
        timeout_seconds=2,
    )

    url = storage.presign_get("tenant/case/evidence.webp", expires_in=timedelta(minutes=15))

    assert url.startswith("https://evidence.example.test/evidence/tenant/case/evidence.webp?")
    assert "X-Amz-Signature=" in url


@pytest.mark.parametrize(
    "expiry",
    [timedelta(0), timedelta(seconds=-1), timedelta(days=7, seconds=1)],
)
def test_presign_rejects_unsafe_expiry(expiry: timedelta) -> None:
    with pytest.raises(ValueError, match="expiry"):
        _storage(FakeMinioClient()).presign_get("tenant/case/evidence.jpg", expires_in=expiry)


@pytest.mark.parametrize("key", ["", "/absolute.jpg", "tenant/../secret.jpg", "tenant//x.jpg"])
def test_object_operations_reject_unsafe_keys(key: str) -> None:
    with pytest.raises(ValueError, match="key"):
        _storage(FakeMinioClient()).exists(key)


def test_put_requires_lowercase_sha256() -> None:
    storage = _storage(FakeMinioClient())

    with pytest.raises(ValueError, match="SHA-256"):
        storage.put(
            key="tenant/case/evidence.jpg",
            content=BytesIO(b"data"),
            length=4,
            content_type="image/jpeg",
            sha256="A" * 64,
        )


def test_is_ready_checks_private_bucket() -> None:
    internal = FakeMinioClient()
    storage = _storage(internal)

    assert storage.is_ready() is True
    internal.bucket_ready = False
    assert storage.is_ready() is False
