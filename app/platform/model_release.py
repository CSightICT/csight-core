"""Framework-free model package and hardware-specific qualification contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"


class DeviceProfile(StrEnum):
    DEV_MACOS_MPS = "dev-macos-mps"
    ONPREM_CUDA = "onprem-cuda"
    CPU_CONTRACT_SMOKE = "cpu-contract-smoke"


class QualificationOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ModelQualification(_Contract):
    device_profile: DeviceProfile
    outcome: QualificationOutcome
    dataset_digest: str = Field(pattern=_DIGEST_PATTERN)
    result_digest: str = Field(pattern=_DIGEST_PATTERN)
    qualified_at: datetime

    @field_validator("qualified_at")
    @classmethod
    def require_qualified_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("qualified_at must be timezone-aware")
        return value.astimezone(UTC)


class ModelPackageManifest(_Contract):
    schema_version: str = Field(pattern=r"^model_package/1\.0\.0$")
    package_name: str = Field(min_length=1, max_length=128)
    package_version: str = Field(min_length=1, max_length=128)
    task: str = Field(min_length=1, max_length=128)
    artifact_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    dependency_lock_digest: str = Field(pattern=_DIGEST_PATTERN)
    input_schema_version: str = Field(min_length=1, max_length=128)
    output_schema_version: str = Field(min_length=1, max_length=128)
    preprocessing_version: str = Field(min_length=1, max_length=128)
    threshold_version: str = Field(min_length=1, max_length=128)
    device_profile: DeviceProfile
    precision: str = Field(min_length=1, max_length=64)
    max_batch_size: int = Field(ge=1, le=4096)
    max_context_tokens: int | None = Field(default=None, ge=1, le=10_000_000)
    license_identifier: str = Field(min_length=1, max_length=255)
    sbom_digest: str = Field(pattern=_DIGEST_PATTERN)
    qualifications: tuple[ModelQualification, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_qualification_profiles(self) -> ModelPackageManifest:
        profiles = tuple(item.device_profile for item in self.qualifications)
        if len(profiles) != len(set(profiles)):
            raise ValueError("qualification device profiles must be unique")
        return self

    def qualified_for(self, profile: DeviceProfile) -> bool:
        """Never transfer a qualification result between hardware/runtime profiles."""

        return profile is self.device_profile and any(
            item.device_profile is profile and item.outcome is QualificationOutcome.PASS
            for item in self.qualifications
        )


__all__ = [
    "DeviceProfile",
    "ModelPackageManifest",
    "ModelQualification",
    "QualificationOutcome",
]
