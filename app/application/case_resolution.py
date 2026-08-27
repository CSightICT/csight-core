"""Case Resolution orchestration and tenant-scoped read use cases."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.case_resolution import (
    CaseResolution,
    CaseResolutionEvent,
    CaseResolutionNotFoundError,
    ExternalActionIntent,
    ExternalActionIntentDetail,
    ExternalActionIntentNotFoundError,
)
from app.platform.tenant import Permission, Principal
from app.ports.case_resolution import (
    CaseResolutionReader,
    CaseResolutionRepository,
    ExternalActionSimulationAdapter,
)


class _Command(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CaseResolutionRequestedCommand(_Command):
    event_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    resolution_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1, max_length=128)

    @field_validator("event_id", "tenant_id", "case_id", "resolution_id")
    @classmethod
    def validate_uuid_identifiers(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as error:
            raise ValueError("worker identifiers must be UUIDs") from error
        return value


class ExternalActionSimulationRequestedCommand(_Command):
    event_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    external_action_intent_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1, max_length=128)

    @field_validator("event_id", "tenant_id", "case_id", "external_action_intent_id")
    @classmethod
    def validate_uuid_identifiers(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as error:
            raise ValueError("worker identifiers must be UUIDs") from error
        return value


class ProcessCaseResolution:
    def __init__(self, repository: CaseResolutionRepository) -> None:
        self._repository = repository

    def execute(self, command: CaseResolutionRequestedCommand) -> str:
        return self._repository.process_requested(**command.model_dump())

    def record_failure(
        self, command: CaseResolutionRequestedCommand, *, code: str, message: str
    ) -> None:
        self._repository.record_resolution_failure(
            event_id=command.event_id,
            code=code,
            message=message,
        )

    def record_poison_event(self, *, event_id: str) -> None:
        self._repository.record_resolution_failure(
            event_id=event_id,
            code="CASE_RESOLUTION_QUEUE_PAYLOAD_INVALID",
            message="Case Resolution queue payload failed UUID validation.",
        )


class ExecuteExternalActionSimulation:
    def __init__(
        self,
        repository: CaseResolutionRepository,
        adapter: ExternalActionSimulationAdapter,
    ) -> None:
        self._repository = repository
        self._adapter = adapter
        self._active_execution_token: str | None = None

    @property
    def active_execution_token(self) -> str | None:
        """Return the lease token acquired by this use-case invocation, if any."""

        return self._active_execution_token

    def execute(self, command: ExternalActionSimulationRequestedCommand) -> str:
        self._active_execution_token = None
        claim = self._repository.prepare_simulation(**command.model_dump())
        if claim is None:
            return "NOOP"
        self._active_execution_token = claim.execution_token
        result = self._adapter.simulate(claim.intent)
        disposition = self._repository.complete_simulation(claim=claim, result=result)
        self._active_execution_token = None
        return disposition

    def record_failure(
        self,
        command: ExternalActionSimulationRequestedCommand,
        *,
        code: str,
        message: str,
        expected_execution_token: str | None = None,
    ) -> None:
        self._repository.record_simulation_failure(
            event_id=command.event_id,
            code=code,
            message=message,
            expected_execution_token=expected_execution_token,
        )

    def record_poison_event(self, *, event_id: str) -> None:
        self._repository.record_simulation_failure(
            event_id=event_id,
            code="EXTERNAL_ACTION_SIMULATION_QUEUE_PAYLOAD_INVALID",
            message="External Action simulation queue payload failed UUID validation.",
        )


class GetCaseResolution:
    def __init__(self, repository: CaseResolutionReader) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> CaseResolution:
        principal.require(Permission.HUMAN_REVIEW_READ)
        result = self._repository.get_resolution(
            tenant_id=principal.tenant_id,
            case_id=case_id,
        )
        if result is None:
            raise CaseResolutionNotFoundError()
        return result


class ListCaseResolutionEvents:
    def __init__(self, repository: CaseResolutionReader) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> tuple[CaseResolutionEvent, ...]:
        principal.require(Permission.HUMAN_REVIEW_READ)
        return self._repository.list_events(
            tenant_id=principal.tenant_id,
            case_id=case_id,
        )


class ListCaseExternalActionIntents:
    def __init__(self, repository: CaseResolutionReader) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> tuple[ExternalActionIntent, ...]:
        principal.require(Permission.HUMAN_REVIEW_READ)
        return self._repository.list_intents(
            tenant_id=principal.tenant_id,
            case_id=case_id,
        )


class GetExternalActionIntent:
    def __init__(self, repository: CaseResolutionReader) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, intent_id: str) -> ExternalActionIntentDetail:
        principal.require(Permission.HUMAN_REVIEW_READ)
        result = self._repository.get_intent(
            tenant_id=principal.tenant_id,
            intent_id=intent_id,
        )
        if result is None:
            raise ExternalActionIntentNotFoundError()
        return result


__all__ = [
    "CaseResolutionRequestedCommand",
    "ExecuteExternalActionSimulation",
    "ExternalActionSimulationRequestedCommand",
    "GetCaseResolution",
    "GetExternalActionIntent",
    "ListCaseExternalActionIntents",
    "ListCaseResolutionEvents",
    "ProcessCaseResolution",
]
