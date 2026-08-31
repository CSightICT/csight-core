"""Allowlisted cache identities that cannot contain inquiry or provider payloads."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class _CacheIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    def opaque_key(self, namespace: str) -> str:
        payload = self.model_dump_json(exclude_none=False)
        digest = hashlib.sha256(f"{namespace}\0{payload}".encode()).hexdigest()
        return f"{namespace}:{digest}"


class PolicyDocumentCacheIdentity(_CacheIdentity):
    """Only versioned policy content is eligible for reusable caching."""

    tenant_id: str = Field(min_length=1, max_length=255)
    index_version: str = Field(min_length=1, max_length=128)
    profile_version: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=_SHA256_PATTERN)

    @property
    def cache_key(self) -> str:
        return self.opaque_key("policy-document")


class VisionResultReuseIdentity(_CacheIdentity):
    """Exact identity required before reusing one immutable image result."""

    tenant_id: str = Field(min_length=1, max_length=255)
    evidence_sha256: str = Field(pattern=_SHA256_PATTERN)
    model_revision: str = Field(min_length=1, max_length=255)
    preprocessing_version: str = Field(min_length=1, max_length=128)
    threshold_version: str = Field(min_length=1, max_length=128)

    @property
    def cache_key(self) -> str:
        return self.opaque_key("vision-result")


class VisionResultReuseRecord(_CacheIdentity):
    identity: VisionResultReuseIdentity
    source_result_id: str = Field(min_length=1, max_length=255)


__all__ = [
    "PolicyDocumentCacheIdentity",
    "VisionResultReuseIdentity",
    "VisionResultReuseRecord",
]
