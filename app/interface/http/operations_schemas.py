"""Public response contracts for aggregate operational visibility."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.model_activation import (
    ActiveLLMRelease,
    LLMReleaseManifestContract,
    ModelActivationEvent,
    ModelReleaseTask,
    RegisteredLLMRelease,
    SignedLLMReleaseManifest,
)
from app.platform.model_routing import (
    ModelRoutePlan,
    ModelRoutePlanActivationResult,
    ResolvedModelRoutePlan,
)
from app.platform.onboarding_readiness import (
    OnboardingGateCode,
    OnboardingGateStatus,
    OnboardingReadiness,
)
from app.platform.operations import (
    OperationalFailureAction,
    OperationalFailureKind,
    OperationalFailurePipeline,
    OperationalFailureResolutionResult,
    OperationalFailureStatus,
    OperationsComponent,
    OperationsFailures,
    OperationsOverview,
    OperationsQueue,
    OperationsVersionKind,
    OperationsVersionSource,
)
from app.platform.pilot_readiness import (
    PilotReadiness,
    PilotReadinessGateKind,
    PilotReadinessGateStatus,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueueOperationsResponse(_Schema):
    queue: OperationsQueue
    backlog_count: int
    pending_count: int
    processing_count: int
    published_unconsumed_count: int
    failed_count: int
    retry_count: int
    stalled_count: int
    oldest_backlog_age_seconds: int | None
    last_healthy_at: datetime | None


class ProcessingOperationsResponse(_Schema):
    component: OperationsComponent
    backlog_count: int
    running_count: int
    retry_count: int
    partial_success_count: int
    failed_count: int
    stalled_count: int
    oldest_backlog_age_seconds: int | None
    last_healthy_at: datetime | None


class ActiveVersionResponse(_Schema):
    kind: OperationsVersionKind
    component: str
    name: str
    version: str
    revision: str | None
    numeric_value: float | None
    source: OperationsVersionSource
    observed_at: datetime


class OperationsOverviewResponse(_Schema):
    generated_at: datetime
    stalled_after_seconds: int
    total_backlog_count: int
    total_stalled_count: int
    queues: list[QueueOperationsResponse]
    processing: list[ProcessingOperationsResponse]
    active_versions: list[ActiveVersionResponse]

    @classmethod
    def from_overview(cls, overview: OperationsOverview) -> OperationsOverviewResponse:
        return cls.model_validate(overview.model_dump(mode="python"))


class OnboardingReadinessGateResponse(_Schema):
    code: OnboardingGateCode
    status: OnboardingGateStatus
    description: str


class OnboardingReadinessResponse(_Schema):
    pilot_ready: bool
    gates: list[OnboardingReadinessGateResponse]

    @classmethod
    def from_readiness(
        cls,
        readiness: OnboardingReadiness,
    ) -> OnboardingReadinessResponse:
        return cls.model_validate(readiness.model_dump(mode="python"))


class PilotReadinessGateResponse(_Schema):
    kind: PilotReadinessGateKind
    code: str
    status: PilotReadinessGateStatus
    verified_at: datetime | None
    expires_at: datetime | None
    evidence_digest: str | None
    description: str


class PilotReadinessResponse(_Schema):
    configuration_ready: bool
    operationally_qualified: bool
    pilot_ready: bool
    gates: list[PilotReadinessGateResponse]

    @classmethod
    def from_readiness(cls, readiness: PilotReadiness) -> PilotReadinessResponse:
        return cls.model_validate(readiness.model_dump(mode="python"))


class FailureCodeCountResponse(_Schema):
    code: str
    count: int


class ComponentFailureSummaryResponse(_Schema):
    component: OperationsComponent
    failed_count: int
    partial_success_count: int
    retry_count: int
    stalled_count: int
    oldest_signal_at: datetime | None
    latest_signal_at: datetime | None
    last_healthy_at: datetime | None
    top_failure_codes: list[FailureCodeCountResponse]


class OperationalFailureResponse(_Schema):
    failure_id: str
    pipeline: OperationalFailurePipeline
    failure_kind: OperationalFailureKind
    failure_code: str
    source_event_id: str
    source_run_id: str | None
    source_stage_id: str | None
    correlation_id: str
    replayable: bool
    status: OperationalFailureStatus
    occurred_at: datetime
    resolved_at: datetime | None
    recovery_run_id: str | None
    recovery_event_id: str | None


class OperationsFailuresResponse(_Schema):
    generated_at: datetime
    lookback_seconds: int
    total_failed_count: int
    total_partial_success_count: int
    total_retry_count: int
    total_stalled_count: int
    components: list[ComponentFailureSummaryResponse]
    items: list[OperationalFailureResponse]
    next_cursor: str | None

    @classmethod
    def from_failures(cls, failures: OperationsFailures) -> OperationsFailuresResponse:
        return cls.model_validate(failures.model_dump(mode="python"))


class OperationalFailureResolutionResponse(_Schema):
    failure_id: str
    action: OperationalFailureAction
    recovery_run_id: str | None
    recovery_event_id: str | None
    created_at: datetime
    idempotent_replay: bool

    @classmethod
    def from_result(
        cls,
        result: OperationalFailureResolutionResult,
    ) -> OperationalFailureResolutionResponse:
        return cls.model_validate(result.model_dump(mode="python"))


class RegisterModelReleaseRequest(_Schema):
    manifest: LLMReleaseManifestContract
    signing_key_id: str
    signature_algorithm: Literal["ED25519"] = "ED25519"
    signature_base64: str

    def signed_manifest(self) -> SignedLLMReleaseManifest:
        return SignedLLMReleaseManifest.model_validate(self.model_dump(mode="python"))


class RegisteredModelReleaseResponse(_Schema):
    release: RegisteredLLMRelease
    idempotent_replay: bool


class ActivateModelReleaseRequest(_Schema):
    execution_mode: AnalysisExecutionMode
    expected_current_activation_id: str | None = None
    reason: str


class ModelActivationResponse(_Schema):
    activation: ModelActivationEvent
    idempotent_replay: bool


class ActiveModelReleaseResponse(_Schema):
    task: ModelReleaseTask
    execution_mode: AnalysisExecutionMode
    active: ActiveLLMRelease


class ActivateModelRouteRequest(_Schema):
    task: ModelReleaseTask
    execution_mode: AnalysisExecutionMode
    model_activation_id: str = Field(min_length=1, max_length=64)
    deployment_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    expected_current_route_plan_id: str | None = Field(default=None, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)


class ModelRouteActivationResponse(_Schema):
    route_plan: ModelRoutePlan
    idempotent_replay: bool

    @classmethod
    def from_result(
        cls,
        result: ModelRoutePlanActivationResult,
    ) -> ModelRouteActivationResponse:
        return cls(
            route_plan=result.route_plan,
            idempotent_replay=result.idempotent_replay,
        )


class ActiveModelRouteResponse(_Schema):
    route_plan: ModelRoutePlan
    active_release: ActiveLLMRelease

    @classmethod
    def from_result(cls, result: ResolvedModelRoutePlan) -> ActiveModelRouteResponse:
        return cls(
            route_plan=result.route_plan,
            active_release=result.active_release,
        )


__all__ = [
    "ActivateModelReleaseRequest",
    "ActivateModelRouteRequest",
    "ActiveModelReleaseResponse",
    "ActiveModelRouteResponse",
    "ModelActivationResponse",
    "ModelRouteActivationResponse",
    "OnboardingReadinessResponse",
    "OperationalFailureResolutionResponse",
    "OperationsFailuresResponse",
    "OperationsOverviewResponse",
    "PilotReadinessResponse",
    "RegisterModelReleaseRequest",
    "RegisteredModelReleaseResponse",
]


class DemoResetPreviewResponse(BaseModel):
    enabled: bool
    count: int
    fingerprint: str
    reset_id: str | None = None


class DemoResetRequest(BaseModel):
    fingerprint: str = Field(min_length=64, max_length=64, pattern="^[a-f0-9]+$")
