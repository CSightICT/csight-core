"""Technology-neutral Evidence metadata and lifecycle values."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceType(StrEnum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    DOCUMENT = "DOCUMENT"
    AUDIO = "AUDIO"
    METADATA = "METADATA"


class EvidenceUploadStatus(StrEnum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    FAILED = "FAILED"


def build_evidence_object_key(*, tenant_id: str, case_id: str, evidence_id: str) -> str:
    """Build an opaque server-owned key without using the client filename."""

    if not tenant_id or not case_id or not evidence_id:
        raise ValueError("tenant_id, case_id, and evidence_id are required")
    identifiers = (tenant_id, case_id, evidence_id)
    if any("/" in identifier or "\\" in identifier for identifier in identifiers):
        raise ValueError("identifiers must not contain path separators")
    return f"tenants/{tenant_id}/cases/{case_id}/evidence/{evidence_id}/original"


class EvidenceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    evidence_type: EvidenceType = EvidenceType.IMAGE
    upload_status: EvidenceUploadStatus
    storage_bucket: str = Field(min_length=1, max_length=255)
    object_key: str = Field(min_length=1, max_length=1024)
    original_filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    created_by: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_utc_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.astimezone(UTC)
