"""Cache eligibility is narrow, tenant-scoped, and provenance preserving."""

import pytest
from pydantic import ValidationError

from app.platform.model_cache import (
    PolicyDocumentCacheIdentity,
    VisionResultReuseIdentity,
    VisionResultReuseRecord,
)

pytestmark = pytest.mark.unit


def test_policy_cache_identity_rejects_inquiry_content() -> None:
    with pytest.raises(ValidationError):
        PolicyDocumentCacheIdentity.model_validate(
            {
                "tenant_id": "tenant-a",
                "index_version": "index-v1",
                "profile_version": "raw-hybrid-top3-v1",
                "content_hash": "a" * 64,
                "customer_message": "must never become a cache key",
            }
        )


def test_vision_reuse_requires_every_version_and_source_result_provenance() -> None:
    original = VisionResultReuseIdentity(
        tenant_id="tenant-a",
        evidence_sha256="b" * 64,
        model_revision="model-revision-1",
        preprocessing_version="preprocess-1",
        threshold_version="threshold-1",
    )
    different_threshold = original.model_copy(update={"threshold_version": "threshold-2"})

    assert original.cache_key != different_threshold.cache_key
    record = VisionResultReuseRecord(identity=original, source_result_id="result-original")
    assert record.source_result_id == "result-original"
    assert record.identity.tenant_id == "tenant-a"
