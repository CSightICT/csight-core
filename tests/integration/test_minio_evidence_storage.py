"""Opt-in private MinIO upload, signed download, and cleanup verification."""

from __future__ import annotations

import hashlib
import os
from datetime import timedelta
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen
from uuid import uuid4

import pytest

from app.adapters.storage import MinioObjectStorage, StoredObjectIntegrityError
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def minio_settings() -> Settings:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test private MinIO evidence storage")
    settings = Settings()
    if not settings.minio_endpoint or not settings.minio_presigned_endpoint_value:
        pytest.fail("MinIO internal and presigned endpoints are required")
    if not settings.minio_access_key_value or not settings.minio_secret_key_value:
        pytest.fail("MinIO credentials are required")
    return settings


def _storage(settings: Settings) -> MinioObjectStorage:
    endpoint = settings.minio_endpoint
    presigned_endpoint = settings.minio_presigned_endpoint_value
    access_key = settings.minio_access_key_value
    secret_key = settings.minio_secret_key_value
    assert endpoint is not None
    assert presigned_endpoint is not None
    assert access_key is not None
    assert secret_key is not None
    return MinioObjectStorage(
        endpoint=endpoint,
        presigned_endpoint=presigned_endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=settings.minio_bucket,
        region=settings.minio_region,
        secure=settings.minio_secure,
        presigned_secure=settings.minio_presigned_secure_value,
        timeout_seconds=settings.readiness_timeout_seconds,
    )


def test_private_object_round_trip_requires_a_short_lived_signature(
    minio_settings: Settings,
) -> None:
    storage = _storage(minio_settings)
    tenant_id, case_id, evidence_id = (str(uuid4()) for _ in range(3))
    key = f"tenants/{tenant_id}/cases/{case_id}/evidence/{evidence_id}/original"
    payload = b"csight-minio-integration-evidence"
    sha256 = hashlib.sha256(payload).hexdigest()

    try:
        stored = storage.put(
            key=key,
            content=BytesIO(payload),
            length=len(payload),
            content_type="image/png",
            sha256=sha256,
        )

        assert stored.key == key
        assert stored.sha256 == sha256
        assert storage.exists(key) is True
        inventory_item = storage.stat(key)
        inventory_page = storage.list_keys(prefix=f"tenants/{tenant_id}/", limit=10)
        assert inventory_item is not None
        assert inventory_item.key == key
        assert inventory_item.sha256 == sha256
        assert key in inventory_page.keys
        assert inventory_page.truncated is False
        assert storage.get(key, max_bytes=len(payload)) == payload
        with pytest.raises(StoredObjectIntegrityError, match="configured read limit"):
            storage.get(key, max_bytes=len(payload) - 1)
        signed_url = storage.presign_get(key, expires_in=timedelta(seconds=60))
        with urlopen(signed_url, timeout=5) as response:
            assert response.read() == payload

        scheme = "https" if minio_settings.minio_presigned_secure_value else "http"
        endpoint = minio_settings.minio_presigned_endpoint_value
        assert endpoint is not None
        unsigned_url = f"{scheme}://{endpoint}/{minio_settings.minio_bucket}/{quote(key, safe='/')}"
        with pytest.raises(HTTPError) as error:
            urlopen(unsigned_url, timeout=5)
        assert error.value.code in {401, 403}
    finally:
        for version in storage.list_versions(key=key, limit=100).versions:
            storage.delete_version(key=key, version_id=version.version_id)

    assert storage.exists(key) is False


def test_versioned_erasure_removes_payload_versions_and_delete_marker(
    minio_settings: Settings,
) -> None:
    storage = _storage(minio_settings)
    tenant_id, case_id, evidence_id = (str(uuid4()) for _ in range(3))
    key = f"tenants/{tenant_id}/cases/{case_id}/evidence/{evidence_id}/original"
    first = b"synthetic-version-one"
    second = b"synthetic-version-two"

    try:
        storage.put(
            key=key,
            content=BytesIO(first),
            length=len(first),
            content_type="image/png",
            sha256=hashlib.sha256(first).hexdigest(),
        )
        storage.put(
            key=key,
            content=BytesIO(second),
            length=len(second),
            content_type="image/png",
            sha256=hashlib.sha256(second).hexdigest(),
        )
        storage.delete(key)

        page = storage.list_versions(key=key, limit=10)
        assert page.truncated is False
        assert len(page.versions) == 3
        assert sum(item.is_delete_marker for item in page.versions) == 1
        assert sum(not item.is_delete_marker for item in page.versions) == 2

        for version in page.versions:
            storage.delete_version(key=key, version_id=version.version_id)

        assert storage.list_versions(key=key, limit=10).versions == ()
        assert storage.exists(key) is False
    finally:
        for version in storage.list_versions(key=key, limit=100).versions:
            storage.delete_version(key=key, version_id=version.version_id)
