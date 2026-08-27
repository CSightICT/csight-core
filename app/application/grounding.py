"""Citation-grounded explanation use cases composed only from ports."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.analysis.models import ProviderExecutionMetadata
from app.platform.analysis.prompts import PromptManifest
from app.platform.errors import CaseNotFoundError
from app.platform.grounding import (
    GroundedExplanationInput,
    GroundedExplanationRun,
    validate_grounded_explanation,
)
from app.platform.tenant import Permission, Principal
from app.ports.grounding import GroundedExplanationRunDetail, GroundedExplanationRunRepository
from app.ports.llm import LLMProvider


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class StartGroundedExplanationCommand(_DTO):
    retrieval_run_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=255, repr=False)
    correlation_id: str = Field(min_length=1, max_length=128)


class StartGroundedExplanationResult(_DTO):
    run: GroundedExplanationRun
    replayed: bool


class ExecuteGroundedExplanationCommand(_DTO):
    event_id: str
    tenant_id: str
    case_id: str
    grounded_explanation_run_id: str
    correlation_id: str

    @field_validator("event_id", "tenant_id", "case_id", "grounded_explanation_run_id")
    @classmethod
    def validate_uuid_identifiers(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as error:
            raise ValueError("worker identifiers must be UUIDs") from error
        return value


def canonical_request_hash(
    case_id: str,
    command: StartGroundedExplanationCommand,
    prompt: PromptManifest,
) -> str:
    payload = {
        "case_id": case_id,
        "retrieval_run_id": command.retrieval_run_id,
        "prompt_name": prompt.name,
        "prompt_version": prompt.version,
        "prompt_hash": prompt.content_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class StartGroundedExplanation:
    def __init__(
        self,
        repository: GroundedExplanationRunRepository,
        llm: LLMProvider,
        prompt: PromptManifest,
    ) -> None:
        self._repository = repository
        self._llm = llm
        self._prompt = prompt

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        command: StartGroundedExplanationCommand,
    ) -> StartGroundedExplanationResult:
        principal.require(Permission.ANALYSIS_CREATE)
        metadata = self._llm.provider_metadata
        execution_metadata = ProviderExecutionMetadata(
            provider_name=metadata.provider,
            model_name=metadata.name,
            model_version=metadata.version,
            model_revision=metadata.revision,
            latency_ms=0,
        )
        run, replayed = self._repository.create(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            retrieval_run_id=command.retrieval_run_id,
            requested_by=principal.user_id,
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
            request_hash=canonical_request_hash(case_id, command, self._prompt),
            provider=execution_metadata,
            prompt_name=self._prompt.name,
            prompt_version=self._prompt.version,
            prompt_hash=self._prompt.content_hash,
        )
        return StartGroundedExplanationResult(run=run, replayed=replayed)


class ListGroundedExplanationRuns:
    def __init__(self, repository: GroundedExplanationRunRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> tuple[GroundedExplanationRun, ...]:
        principal.require(Permission.POLICY_READ)
        return self._repository.list(tenant_id=principal.tenant_id, case_id=case_id)


class GetGroundedExplanationRun:
    def __init__(self, repository: GroundedExplanationRunRepository) -> None:
        self._repository = repository

    def execute(
        self, *, principal: Principal, case_id: str, run_id: str
    ) -> GroundedExplanationRunDetail:
        principal.require(Permission.POLICY_READ)
        detail = self._repository.get(tenant_id=principal.tenant_id, case_id=case_id, run_id=run_id)
        if detail is None:
            raise CaseNotFoundError("The requested grounded explanation run was not found.")
        return detail


class ExecuteGroundedExplanation:
    def __init__(
        self,
        *,
        repository: GroundedExplanationRunRepository,
        llm: LLMProvider,
        prompt: PromptManifest,
    ) -> None:
        self._repository = repository
        self._llm = llm
        self._prompt = prompt

    def execute(self, command: ExecuteGroundedExplanationCommand) -> str:
        source = self._repository.claim(
            event_id=command.event_id,
            tenant_id=command.tenant_id,
            case_id=command.case_id,
            run_id=command.grounded_explanation_run_id,
            correlation_id=command.correlation_id,
        )
        if source is None:
            return "NOOP"
        try:
            response = self._llm.explain_policy_grounded(
                GroundedExplanationInput(
                    case_summary=source.case_summary,
                    citation_pack=source.citation_pack,
                ),
                self._prompt,
            )
            metrics = validate_grounded_explanation(response.explanation, source.citation_pack)
        except Exception as error:
            code = str(getattr(error, "code", "GROUNDED_EXPLANATION_FAILED"))
            code = {
                "LLM_PROVIDER_UNAVAILABLE": "GROUNDED_EXPLANATION_PROVIDER_UNAVAILABLE",
                "LLM_PROVIDER_TIMEOUT": "GROUNDED_EXPLANATION_TIMEOUT",
                "LLM_INVALID_STRUCTURED_OUTPUT": "GROUNDED_EXPLANATION_INVALID_OUTPUT",
            }.get(code, code)
            persisted = self._repository.fail(
                tenant_id=source.run.tenant_id,
                run_id=source.run.id,
                event_id=command.event_id,
                claim_token=source.claim_token,
                code=code,
                message="Grounded explanation execution failed.",
            )
            return "FAILED" if persisted else "FENCED"
        persisted = self._repository.succeed(
            tenant_id=source.run.tenant_id,
            run_id=source.run.id,
            event_id=command.event_id,
            claim_token=source.claim_token,
            explanation=response.explanation,
            metrics=metrics,
            provider=response.metadata,
            prompt_name=self._prompt.name,
            prompt_version=self._prompt.version,
            prompt_hash=self._prompt.content_hash,
        )
        return "SUCCEEDED" if persisted else "FENCED"

    def record_failure(
        self,
        command: ExecuteGroundedExplanationCommand,
        *,
        code: str,
        message: str,
    ) -> None:
        self._repository.record_consumer_failure(
            event_id=command.event_id,
            code=code,
            message=message,
        )

    def record_poison_event(self, *, event_id: str) -> None:
        self._repository.record_consumer_failure(
            event_id=event_id,
            code="GROUNDED_EXPLANATION_QUEUE_PAYLOAD_INVALID",
            message="Grounded explanation queue payload failed UUID validation.",
        )


__all__ = [
    "ExecuteGroundedExplanation",
    "ExecuteGroundedExplanationCommand",
    "GetGroundedExplanationRun",
    "ListGroundedExplanationRuns",
    "StartGroundedExplanation",
    "StartGroundedExplanationCommand",
    "StartGroundedExplanationResult",
    "canonical_request_hash",
]
