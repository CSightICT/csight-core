"""Technology-neutral privacy and private-object lifecycle contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.evidence import EvidenceUploadStatus

PURGED_CUSTOMER_MESSAGE = "[PURGED_BY_RETENTION]"
EVIDENCE_LIFECYCLE_POLICY_VERSION = "evidence-consistency/1.0.0"
TERMINAL_CONTENT_REDACTION_POLICY_VERSION = "terminal-content-redaction/1.0.0"


class LifecycleRunMode(StrEnum):
    DRY_RUN = "DRY_RUN"
    EXECUTE = "EXECUTE"


class LifecycleMutationStatus(StrEnum):
    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    BLOCKED = "BLOCKED"


class LifecycleFindingKind(StrEnum):
    SENSITIVE_PAYLOAD_EXPIRED = "SENSITIVE_PAYLOAD_EXPIRED"
    STALE_PENDING_OBJECT_VALID = "STALE_PENDING_OBJECT_VALID"
    STALE_PENDING_OBJECT_MISSING = "STALE_PENDING_OBJECT_MISSING"
    EVIDENCE_OBJECT_MISSING = "EVIDENCE_OBJECT_MISSING"
    EVIDENCE_OBJECT_INTEGRITY_MISMATCH = "EVIDENCE_OBJECT_INTEGRITY_MISMATCH"
    FAILED_EVIDENCE_OBJECT_PRESENT = "FAILED_EVIDENCE_OBJECT_PRESENT"
    ORPHAN_EVIDENCE_OBJECT = "ORPHAN_EVIDENCE_OBJECT"
    UNATTRIBUTABLE_OBJECT = "UNATTRIBUTABLE_OBJECT"


class LifecycleFindingOutcome(StrEnum):
    PLANNED = "PLANNED"
    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    BLOCKED = "BLOCKED"


class EvidencePurgeEventType(StrEnum):
    REQUESTED = "EVIDENCE_PURGE_REQUESTED"
    COMPLETED = "EVIDENCE_PURGED"


class _LifecycleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SensitivePayloadLifecycleRecord(_LifecycleModel):
    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retention_policy_version: str = Field(min_length=1, max_length=128)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def normalize_expires_at(cls, value: datetime) -> datetime:
        return _utc(value)


class SensitivePayloadLifecyclePage(_LifecycleModel):
    items: tuple[SensitivePayloadLifecycleRecord, ...]
    truncated: bool


class EvidenceLifecycleRecord(_LifecycleModel):
    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    upload_status: EvidenceUploadStatus
    storage_bucket: str = Field(min_length=1, max_length=255)
    object_key: str = Field(min_length=1, max_length=1024)
    content_type: str = Field(min_length=1, max_length=127)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _utc(value)


class EvidenceLifecyclePage(_LifecycleModel):
    items: tuple[EvidenceLifecycleRecord, ...]
    truncated: bool


class LifecycleMutationResult(_LifecycleModel):
    status: LifecycleMutationStatus
    reason: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9_]+$")


class LifecycleFinding(_LifecycleModel):
    kind: LifecycleFindingKind
    outcome: LifecycleFindingOutcome
    case_id: str | None = Field(default=None, min_length=1)
    resource_id: str | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9_]+$")


class LifecycleRunReport(_LifecycleModel):
    mode: LifecycleRunMode
    tenant_id: str = Field(min_length=1)
    generated_at: datetime
    scanned_count: int = Field(ge=0)
    planned_count: int = Field(ge=0)
    applied_count: int = Field(ge=0)
    already_applied_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    truncated: bool
    findings: tuple[LifecycleFinding, ...] = Field(max_length=10_000)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _utc(value)


def is_purged_customer_message(value: str) -> bool:
    """Return whether a Case carries only the retention tombstone."""

    return value == PURGED_CUSTOMER_MESSAGE


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("lifecycle timestamps must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "EVIDENCE_LIFECYCLE_POLICY_VERSION",
    "PURGED_CUSTOMER_MESSAGE",
    "TERMINAL_CONTENT_REDACTION_POLICY_VERSION",
    "EvidenceLifecyclePage",
    "EvidenceLifecycleRecord",
    "EvidencePurgeEventType",
    "LifecycleFinding",
    "LifecycleFindingKind",
    "LifecycleFindingOutcome",
    "LifecycleMutationResult",
    "LifecycleMutationStatus",
    "LifecycleRunMode",
    "LifecycleRunReport",
    "SensitivePayloadLifecyclePage",
    "SensitivePayloadLifecycleRecord",
    "is_purged_customer_message",
]
