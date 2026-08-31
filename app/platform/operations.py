"""Technology-neutral, low-cardinality operations read contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OperationsQueue(StrEnum):
    ANALYSIS_DISPATCH = "analysis_dispatch"
    POLICY_RETRIEVAL = "policy_retrieval"
    GROUNDED_EXPLANATION = "grounded_explanation"
    POLICY_EVALUATION = "policy_evaluation"
    HUMAN_REVIEW = "human_review"
    CASE_RESOLUTION = "case_resolution"
    ACTION_SIMULATION = "action_simulation"


class OperationsComponent(StrEnum):
    ANALYSIS = "analysis"
    POLICY_RETRIEVAL = "policy_retrieval"
    GROUNDED_EXPLANATION = "grounded_explanation"
    POLICY_EVALUATION = "policy_evaluation"
    HUMAN_REVIEW = "human_review"
    CASE_RESOLUTION = "case_resolution"
    ACTION_SIMULATION = "action_simulation"


class OperationalFailurePipeline(StrEnum):
    ANALYSIS = "analysis"
    POLICY_RETRIEVAL = "policy_retrieval"
    GROUNDED_EXPLANATION = "grounded_explanation"
    POLICY_EVALUATION = "policy_evaluation"
    HUMAN_REVIEW = "human_review"
    CASE_RESOLUTION = "case_resolution"
    ACTION_SIMULATION = "action_simulation"
    FAILURE_RECOVERY = "failure_recovery"


class OperationalFailureKind(StrEnum):
    DISPATCH = "DISPATCH"
    CONSUMER = "CONSUMER"


class OperationalFailureStatus(StrEnum):
    OPEN = "OPEN"
    REPLAYED = "REPLAYED"
    CANCELLED = "CANCELLED"


class OperationalFailureAction(StrEnum):
    REPLAYED = "REPLAYED"
    CANCELLED = "CANCELLED"


class OperationsVersionKind(StrEnum):
    MODEL = "model"
    PROMPT = "prompt"
    POLICY = "policy"
    THRESHOLD = "threshold"
    INDEX = "index"


class OperationsVersionSource(StrEnum):
    ACTIVE_RECORD = "active_record"
    LATEST_RUN_SNAPSHOT = "latest_run_snapshot"
    LATEST_SUCCEEDED_RESULT = "latest_succeeded_result"


class _OperationsContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class QueueOperationsSnapshot(_OperationsContract):
    queue: OperationsQueue
    backlog_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    processing_count: int = Field(ge=0)
    published_unconsumed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    stalled_count: int = Field(ge=0)
    oldest_backlog_age_seconds: int | None = Field(default=None, ge=0)
    last_healthy_at: datetime | None = None

    @field_validator("last_healthy_at")
    @classmethod
    def normalize_last_healthy_at(cls, value: datetime | None) -> datetime | None:
        return _to_utc(value)


class ProcessingOperationsSnapshot(_OperationsContract):
    component: OperationsComponent
    backlog_count: int = Field(ge=0)
    running_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    partial_success_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    stalled_count: int = Field(ge=0)
    oldest_backlog_age_seconds: int | None = Field(default=None, ge=0)
    last_healthy_at: datetime | None = None

    @field_validator("last_healthy_at")
    @classmethod
    def normalize_last_healthy_at(cls, value: datetime | None) -> datetime | None:
        return _to_utc(value)


class ActiveVersionSnapshot(_OperationsContract):
    kind: OperationsVersionKind
    component: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=128)
    revision: str | None = Field(default=None, min_length=1, max_length=255)
    numeric_value: float | None = None
    source: OperationsVersionSource
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        normalized = _to_utc(value)
        if normalized is None:  # pragma: no cover - required field, defensive for type narrowing
            raise ValueError("observed_at is required")
        return normalized


class OperationsOverview(_OperationsContract):
    generated_at: datetime
    stalled_after_seconds: int = Field(ge=1)
    total_backlog_count: int = Field(ge=0)
    total_stalled_count: int = Field(ge=0)
    queues: tuple[QueueOperationsSnapshot, ...]
    processing: tuple[ProcessingOperationsSnapshot, ...]
    active_versions: tuple[ActiveVersionSnapshot, ...] = Field(max_length=64)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        normalized = _to_utc(value)
        if normalized is None:  # pragma: no cover - required field, defensive for type narrowing
            raise ValueError("generated_at is required")
        return normalized


class FailureCodeCount(_OperationsContract):
    code: str = Field(
        min_length=2,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )
    count: int = Field(ge=1)


class ComponentFailureSummary(_OperationsContract):
    component: OperationsComponent
    failed_count: int = Field(ge=0)
    partial_success_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    stalled_count: int = Field(ge=0)
    oldest_signal_at: datetime | None = None
    latest_signal_at: datetime | None = None
    last_healthy_at: datetime | None = None
    top_failure_codes: tuple[FailureCodeCount, ...] = Field(max_length=3)

    @field_validator("oldest_signal_at", "latest_signal_at", "last_healthy_at")
    @classmethod
    def normalize_signal_times(cls, value: datetime | None) -> datetime | None:
        return _to_utc(value)


class OperationalFailureRecord(_OperationsContract):
    failure_id: str = Field(min_length=1, max_length=64)
    pipeline: OperationalFailurePipeline
    failure_kind: OperationalFailureKind
    failure_code: str = Field(
        min_length=2,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )
    source_event_id: str = Field(min_length=1, max_length=64)
    source_run_id: str | None = Field(default=None, min_length=1, max_length=64)
    source_stage_id: str | None = Field(default=None, min_length=1, max_length=64)
    correlation_id: str = Field(min_length=1, max_length=128)
    replayable: bool
    status: OperationalFailureStatus
    occurred_at: datetime
    resolved_at: datetime | None = None
    recovery_run_id: str | None = Field(default=None, min_length=1, max_length=64)
    recovery_event_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("occurred_at", "resolved_at")
    @classmethod
    def normalize_failure_times(cls, value: datetime | None) -> datetime | None:
        return _to_utc(value)


class OperationalFailurePage(_OperationsContract):
    items: tuple[OperationalFailureRecord, ...] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=512)


class OperationalFailureResolutionResult(_OperationsContract):
    failure_id: str = Field(min_length=1, max_length=64)
    action: OperationalFailureAction
    recovery_run_id: str | None = Field(default=None, min_length=1, max_length=64)
    recovery_event_id: str | None = Field(default=None, min_length=1, max_length=64)
    created_at: datetime
    idempotent_replay: bool = False

    @field_validator("created_at")
    @classmethod
    def normalize_resolution_time(cls, value: datetime) -> datetime:
        normalized = _to_utc(value)
        if normalized is None:  # pragma: no cover - required field
            raise ValueError("created_at is required")
        return normalized


class OperationsFailures(_OperationsContract):
    generated_at: datetime
    lookback_seconds: int = Field(ge=1)
    total_failed_count: int = Field(ge=0)
    total_partial_success_count: int = Field(ge=0)
    total_retry_count: int = Field(ge=0)
    total_stalled_count: int = Field(ge=0)
    components: tuple[ComponentFailureSummary, ...]
    items: tuple[OperationalFailureRecord, ...] = Field(default=(), max_length=100)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        normalized = _to_utc(value)
        if normalized is None:  # pragma: no cover - required field, defensive for type narrowing
            raise ValueError("generated_at is required")
        return normalized


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("operations timestamps must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "ActiveVersionSnapshot",
    "ComponentFailureSummary",
    "FailureCodeCount",
    "OperationalFailureAction",
    "OperationalFailureKind",
    "OperationalFailurePage",
    "OperationalFailurePipeline",
    "OperationalFailureRecord",
    "OperationalFailureResolutionResult",
    "OperationalFailureStatus",
    "OperationsComponent",
    "OperationsFailures",
    "OperationsOverview",
    "OperationsQueue",
    "OperationsVersionKind",
    "OperationsVersionSource",
    "ProcessingOperationsSnapshot",
    "QueueOperationsSnapshot",
]
