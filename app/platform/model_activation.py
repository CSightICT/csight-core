"""Framework-free signed LLM release and append-only activation contracts."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.errors import CSightError

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_HASH_PATTERN = r"^[0-9a-f]{64}$"
_REVISION_PATTERN = r"^[0-9a-f]{40}$"


class ModelReleaseTask(StrEnum):
    PRODUCT_DEFECT_TEXT_EXTRACTION_V2 = "PRODUCT_DEFECT_TEXT_EXTRACTION_V2"
    POLICY_QUERY_BUILDER_V1 = "POLICY_QUERY_BUILDER_V1"
    GROUNDED_POLICY_EXPLANATION_V1 = "GROUNDED_POLICY_EXPLANATION_V1"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class LLMReleaseManifest(_Contract):
    schema_version: Literal["llm_release_manifest/1.0.0"] = "llm_release_manifest/1.0.0"
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    package_name: str = Field(min_length=1, max_length=128)
    package_version: str = Field(min_length=1, max_length=128)
    task: ModelReleaseTask
    artifact: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    artifact_revision: str = Field(pattern=_REVISION_PATTERN)
    artifact_content_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_image: str = Field(min_length=2, max_length=255)
    runtime_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    dependency_lock_digest: str = Field(pattern=_DIGEST_PATTERN)
    sbom_digest: str = Field(pattern=_DIGEST_PATTERN)
    served_model_name: str = Field(min_length=2, max_length=255)
    model_version: str = Field(min_length=1, max_length=100)
    prompt_name: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    prompt_content_hash: str = Field(pattern=_HASH_PATTERN)
    input_schema_version: str = Field(min_length=1, max_length=128)
    output_schema_version: str = Field(min_length=1, max_length=128)
    device_profile: Literal["onprem-cuda"] = "onprem-cuda"
    precision: str = Field(min_length=2, max_length=64)
    max_context_tokens: int = Field(ge=1, le=1_000_000)
    max_num_sequences: int = Field(ge=1, le=64)
    gpu_memory_utilization: float = Field(gt=0.0, le=1.0)
    kv_cache_dtype: str = Field(min_length=2, max_length=64)
    language_model_only: Literal[True] = True
    automatic_cross_model_fallback: Literal[False] = False
    qualification_dataset_digest: str = Field(pattern=_DIGEST_PATTERN)
    qualification_result_digest: str = Field(pattern=_DIGEST_PATTERN)
    candidate_matrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    candidate_assessment_digest: str = Field(pattern=_DIGEST_PATTERN)
    release_status: Literal["RELEASE_ELIGIBLE"] = "RELEASE_ELIGIBLE"
    qualified_at: datetime

    @field_validator("qualified_at")
    @classmethod
    def require_qualified_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("qualified_at must be timezone-aware")
        return value.astimezone(UTC)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @property
    def manifest_digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()


class SignedLLMReleaseManifest(_Contract):
    manifest: LLMReleaseManifest
    signing_key_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
    signature_algorithm: Literal["ED25519"] = "ED25519"
    signature_base64: str = Field(min_length=88, max_length=88, repr=False)

    @field_validator("signature_base64")
    @classmethod
    def require_ed25519_signature(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("signature_base64 must be valid base64") from None
        if len(decoded) != 64:
            raise ValueError("ED25519 signature must contain exactly 64 bytes")
        return value

    @property
    def signature_bytes(self) -> bytes:
        return base64.b64decode(self.signature_base64, validate=True)


class RegisteredLLMRelease(_Contract):
    id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64)
    signed_manifest: SignedLLMReleaseManifest
    registered_by: str = Field(min_length=1, max_length=64)
    registered_at: datetime

    @field_validator("registered_at")
    @classmethod
    def require_registered_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("registered_at must be timezone-aware")
        return value.astimezone(UTC)


class ModelActivationEvent(_Contract):
    id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64)
    task: ModelReleaseTask
    execution_mode: AnalysisExecutionMode
    model_release_id: str = Field(min_length=1, max_length=64)
    previous_activation_id: str | None = Field(default=None, max_length=64)
    activated_by: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=255, repr=False)
    request_hash: str = Field(pattern=_HASH_PATTERN)
    activated_at: datetime

    @field_validator("activated_at")
    @classmethod
    def require_activated_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("activated_at must be timezone-aware")
        return value.astimezone(UTC)


class ActiveLLMRelease(_Contract):
    release: RegisteredLLMRelease
    activation: ModelActivationEvent


class ModelReleaseRegistrationResult(_Contract):
    release: RegisteredLLMRelease
    idempotent_replay: bool


class ModelActivationResult(_Contract):
    activation: ModelActivationEvent
    idempotent_replay: bool


class RuntimeLLMIdentity(_Contract):
    served_model_name: str = Field(min_length=2, max_length=255)
    model_version: str = Field(min_length=1, max_length=100)
    artifact_revision: str = Field(pattern=_REVISION_PATTERN)
    artifact_content_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    dependency_lock_digest: str = Field(pattern=_DIGEST_PATTERN)
    sbom_digest: str = Field(pattern=_DIGEST_PATTERN)
    prompt_name: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    prompt_content_hash: str = Field(pattern=_HASH_PATTERN)
    input_schema_version: str = Field(min_length=1, max_length=128)
    output_schema_version: str = Field(min_length=1, max_length=128)


class ModelReleaseSignatureInvalidError(CSightError):
    code = "MODEL_RELEASE_SIGNATURE_INVALID"
    default_message = "The model release signature is invalid."
    retryable: ClassVar[bool] = False


class ModelReleaseNotFoundError(CSightError):
    code = "MODEL_RELEASE_NOT_FOUND"
    default_message = "The requested model release was not found."


class ModelReleaseRegistrationConflictError(CSightError):
    code = "MODEL_RELEASE_REGISTRATION_CONFLICT"
    default_message = "The model package version is already registered with different content."


class ModelActivationConflictError(CSightError):
    code = "MODEL_ACTIVATION_CONFLICT"
    default_message = "The active model release changed before activation completed."


class ModelReleaseIdentityMismatchError(CSightError):
    code = "MODEL_RELEASE_IDENTITY_MISMATCH"
    default_message = "The configured model runtime does not match the active signed release."
    retryable: ClassVar[bool] = False


class ActiveModelReleaseRequiredError(CSightError):
    code = "ACTIVE_MODEL_RELEASE_REQUIRED"
    default_message = "No active signed model release exists for this execution profile."
    retryable: ClassVar[bool] = False


__all__ = [
    "ActiveLLMRelease",
    "ActiveModelReleaseRequiredError",
    "LLMReleaseManifest",
    "ModelActivationConflictError",
    "ModelActivationEvent",
    "ModelActivationResult",
    "ModelReleaseIdentityMismatchError",
    "ModelReleaseNotFoundError",
    "ModelReleaseRegistrationConflictError",
    "ModelReleaseRegistrationResult",
    "ModelReleaseSignatureInvalidError",
    "ModelReleaseTask",
    "RegisteredLLMRelease",
    "RuntimeLLMIdentity",
    "SignedLLMReleaseManifest",
]
