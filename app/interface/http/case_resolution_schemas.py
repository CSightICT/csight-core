"""Public Sprint 5C responses with internal tenancy and fencing fields removed."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.platform.case_resolution import (
    CaseResolution,
    CaseResolutionEvent,
    ExternalActionIntent,
    ExternalActionIntentDetail,
    ExternalActionMode,
    ExternalActionSimulationAttempt,
    ExternalActionSimulationResult,
    ExternalActionType,
    ResolutionEventType,
    ResolutionStatus,
    SimulationAttemptStatus,
    SimulationOutcome,
)


class _Response(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseResolutionResponse(_Response):
    id: str
    case_id: str
    source_review_task_id: str
    source_human_decision_id: str
    status: ResolutionStatus
    version: int
    mapping_name: str
    mapping_version: str
    resolution_schema_version: str
    missing_fields: tuple[str, ...]
    invalid_fields: tuple[str, ...]
    failure_code: str | None
    failure_message: str | None
    correlation_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, value: CaseResolution) -> "CaseResolutionResponse":
        return cls.model_validate(value.model_dump(exclude={"tenant_id"}))


class CaseResolutionEventResponse(_Response):
    id: str
    case_id: str
    resolution_id: str
    sequence: int
    event_type: ResolutionEventType
    from_status: ResolutionStatus | None
    to_status: ResolutionStatus
    human_decision_id: str | None
    external_action_intent_id: str | None
    payload: dict[str, object]
    created_at: datetime

    @classmethod
    def from_domain(cls, value: CaseResolutionEvent) -> "CaseResolutionEventResponse":
        return cls.model_validate(value.model_dump(exclude={"tenant_id"}))


class ExternalActionIntentResponse(_Response):
    id: str
    case_id: str
    resolution_id: str
    human_decision_id: str
    action_type: ExternalActionType
    mode: str
    order_ref: str
    product_ref: str | None
    amount: str | None
    currency: str | None
    quantity: int | None
    shipping_address_ref: str | None
    mapping_name: str
    mapping_version: str
    intent_schema_version: str
    content_hash: str
    created_at: datetime

    @classmethod
    def from_domain(cls, value: ExternalActionIntent) -> "ExternalActionIntentResponse":
        return cls.model_validate(value.model_dump(exclude={"tenant_id"}))


class ExternalActionSimulationAttemptResponse(_Response):
    id: str
    case_id: str
    resolution_id: str
    external_action_intent_id: str
    attempt_number: int
    status: SimulationAttemptStatus
    mode: ExternalActionMode
    started_at: datetime
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None

    @classmethod
    def from_domain(
        cls, value: ExternalActionSimulationAttempt
    ) -> "ExternalActionSimulationAttemptResponse":
        return cls.model_validate(value.model_dump(exclude={"tenant_id", "execution_token"}))


class ExternalActionSimulationResultResponse(_Response):
    id: str
    case_id: str
    resolution_id: str
    external_action_intent_id: str
    simulation_attempt_id: str
    outcome: SimulationOutcome
    mode: ExternalActionMode
    side_effects_performed: bool
    failure_code: str | None
    failure_message: str | None
    simulated_request: dict[str, object]
    simulated_response: dict[str, object]
    result_schema_version: str
    content_hash: str
    created_at: datetime

    @classmethod
    def from_domain(
        cls, value: ExternalActionSimulationResult
    ) -> "ExternalActionSimulationResultResponse":
        return cls.model_validate(value.model_dump(exclude={"tenant_id"}))


class CaseResolutionEventsResponse(_Response):
    items: tuple[CaseResolutionEventResponse, ...]


class ExternalActionIntentsResponse(_Response):
    items: tuple[ExternalActionIntentResponse, ...]


class ExternalActionIntentDetailResponse(_Response):
    intent: ExternalActionIntentResponse
    attempts: tuple[ExternalActionSimulationAttemptResponse, ...]
    results: tuple[ExternalActionSimulationResultResponse, ...]

    @classmethod
    def from_domain(cls, value: ExternalActionIntentDetail) -> "ExternalActionIntentDetailResponse":
        return cls(
            intent=ExternalActionIntentResponse.from_domain(value.intent),
            attempts=tuple(
                ExternalActionSimulationAttemptResponse.from_domain(item) for item in value.attempts
            ),
            results=tuple(
                ExternalActionSimulationResultResponse.from_domain(item) for item in value.results
            ),
        )


__all__ = [
    "CaseResolutionEventResponse",
    "CaseResolutionEventsResponse",
    "CaseResolutionResponse",
    "ExternalActionIntentDetailResponse",
    "ExternalActionIntentResponse",
    "ExternalActionIntentsResponse",
    "ExternalActionSimulationAttemptResponse",
    "ExternalActionSimulationResultResponse",
]
