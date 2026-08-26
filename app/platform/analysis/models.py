"""Immutable analysis-run entities independent from persistence technology."""

from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.analysis.enums import (
    AnalysisAttemptStatus,
    AnalysisPipeline,
    AnalysisRunStatus,
    AnalysisStageStatus,
    AnalysisStageType,
    AnalysisTrigger,
    OutboxStatus,
)


class AnalysisEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("analysis timestamps must be timezone-aware")
    return value.astimezone(UTC)


class AnalysisFailure(AnalysisEntity):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500, repr=False)
    retryable: bool


class ProviderExecutionMetadata(AnalysisEntity):
    provider_name: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=255)
    model_version: str = Field(min_length=1, max_length=100)
    model_revision: str | None = Field(default=None, min_length=1, max_length=255)
    provider_request_id: str | None = Field(default=None, min_length=1, max_length=255)
    input_token_count: int | None = Field(default=None, ge=0)
    output_token_count: int | None = Field(default=None, ge=0)
    latency_ms: int = Field(ge=0)


class AnalysisAttemptSummary(AnalysisEntity):
    attempt_count: int = Field(default=0, ge=0)
    last_attempt_started_at: datetime | None = None
    last_attempt_completed_at: datetime | None = None

    @field_validator("last_attempt_started_at", "last_attempt_completed_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_attempt_times(self) -> Self:
        if self.attempt_count == 0 and (
            self.last_attempt_started_at is not None or self.last_attempt_completed_at is not None
        ):
            raise ValueError("an attempt timestamp requires a positive attempt_count")
        if self.last_attempt_completed_at is not None:
            if self.last_attempt_started_at is None:
                raise ValueError("completed attempts require a start time")
            if self.last_attempt_completed_at < self.last_attempt_started_at:
                raise ValueError("attempt completion cannot precede its start")
        return self


class AnalysisRun(AnalysisEntity):
    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    pipeline: AnalysisPipeline
    pipeline_version: str = Field(min_length=1, max_length=32)
    trigger: AnalysisTrigger
    status: AnalysisRunStatus
    requested_by: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=255, repr=False)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure: AnalysisFailure | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("requested_at", "started_at", "completed_at", "created_at", "updated_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value) if value is not None else None


class AnalysisStageRun(AnalysisEntity):
    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    analysis_run_id: str = Field(min_length=1)
    stage_type: AnalysisStageType
    status: AnalysisStageStatus
    attempt_summary: AnalysisAttemptSummary = Field(default_factory=AnalysisAttemptSummary)
    provider_name: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=255)
    model_version: str = Field(min_length=1, max_length=100)
    model_revision: str | None = Field(default=None, min_length=1, max_length=255)
    provider_execution: ProviderExecutionMetadata | None = None
    prompt_name: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=32)
    prompt_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_schema_version: str = Field(min_length=1, max_length=32)
    output_schema_version: str = Field(min_length=1, max_length=32)
    claim_token: str | None = Field(default=None, min_length=1, max_length=255, repr=False)
    claim_expires_at: datetime | None = None
    next_attempt_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure: AnalysisFailure | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "claim_expires_at",
        "next_attempt_at",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_claim_lease(self) -> Self:
        if (self.claim_token is None) != (self.claim_expires_at is None):
            raise ValueError("claim_token and claim_expires_at must be set together")
        if self.claim_token is not None and self.status is not AnalysisStageStatus.RUNNING:
            raise ValueError("only a RUNNING stage may hold a claim lease")
        return self


class AnalysisStageAttempt(AnalysisEntity):
    """Immutable snapshot of one provider attempt within a stage run."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    analysis_run_id: str = Field(min_length=1)
    stage_run_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    status: AnalysisAttemptStatus
    claim_token: str = Field(min_length=1, max_length=255, repr=False)
    provider_name: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=255)
    model_version: str = Field(min_length=1, max_length=100)
    model_revision: str | None = Field(default=None, min_length=1, max_length=255)
    prompt_name: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=32)
    prompt_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_schema_version: str = Field(min_length=1, max_length=32)
    output_schema_version: str = Field(min_length=1, max_length=32)
    provider_execution: ProviderExecutionMetadata | None = None
    started_at: datetime
    completed_at: datetime | None = None
    failure: AnalysisFailure | None = None
    created_at: datetime

    @field_validator("started_at", "completed_at", "created_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value) if value is not None else None


class AnalysisRequestIdempotencyRecord(AnalysisEntity):
    """Tenant-scoped claim linking an API key to exactly one Analysis Run."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    operation: str = Field(default="analysis.create.v1", pattern=r"^analysis\.create\.v1$")
    idempotency_key: str = Field(min_length=1, max_length=255, repr=False)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    analysis_run_id: str = Field(min_length=1)
    response_status: int = Field(default=202, ge=100, le=599)
    created_at: datetime
    expires_at: datetime

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def require_future_expiry(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        return self


class OutboxEvent(AnalysisEntity):
    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    aggregate_type: str = Field(min_length=1, max_length=100)
    aggregate_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1, max_length=100)
    event_version: str = Field(min_length=1, max_length=32)
    payload: dict[str, object]
    status: OutboxStatus
    attempt_count: int = Field(default=0, ge=0)
    available_at: datetime
    claimed_at: datetime | None = None
    claimed_by: str | None = Field(default=None, min_length=1, max_length=255)
    published_at: datetime | None = None
    claim_token: str | None = Field(default=None, min_length=1, max_length=255, repr=False)
    last_error: str | None = Field(default=None, min_length=1, max_length=500, repr=False)
    created_at: datetime
    updated_at: datetime

    @field_validator("available_at", "claimed_at", "published_at", "created_at", "updated_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_claim_fields(self) -> Self:
        claim_values = (self.claimed_at, self.claimed_by, self.claim_token)
        if any(value is not None for value in claim_values) and not all(
            value is not None for value in claim_values
        ):
            raise ValueError("claimed_at, claimed_by, and claim_token must be set together")
        if self.claim_token is not None and self.status is not OutboxStatus.PROCESSING:
            raise ValueError("only a PROCESSING outbox event may hold a claim")
        return self
