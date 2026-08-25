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

from app.adapters.storage import MinioObjectStorage
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
        storage.delete(key)

    assert storage.exists(key) is False
