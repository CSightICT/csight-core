"""Case-to-policy retrieval run use cases composed only from ports."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.application.policy_retrieval import SearchPolicyClauses
from app.domains.product_defect_cs.query_builder import build_deterministic_query_plan
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.analysis.prompts import PromptManifest
from app.platform.errors import CaseNotFoundError
from app.platform.model_activation import ModelReleaseTask
from app.platform.model_routing import (
    MODEL_ROUTE_ENFORCEMENT_CONTRACT_VERSION,
    PinnedModelRoutePlanRequiredError,
)
from app.platform.policy_retrieval import PolicySearchFilters, PolicySearchQuery, RetrievalMode
from app.platform.privacy_lifecycle import is_purged_customer_message
from app.platform.query_builder import (
    MultiQueryFusionProfile,
    PolicyQuery,
    PolicyQueryBuilderInvalidOutputError,
    PolicyQueryPlan,
    PolicyQueryPurpose,
    PolicyRetrievalRun,
    QueryFilterHints,
    QueryStrategy,
    build_policy_similarity_diagnostics,
    fuse_multi_query_hits,
)
from app.platform.tenant import Permission, Principal, Role
from app.ports.llm import LLMProvider
from app.ports.model_routing import ActiveModelRouteResolver, PinnedModelRouteExecutionGuard
from app.ports.policy_query_runs import PolicyRetrievalRunDetail, PolicyRetrievalRunRepository

CREATE_OPERATION = "policy_retrieval_run.create.v1"


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class StartPolicyRetrievalRunCommand(_DTO):
    analysis_run_id: str = Field(min_length=1)
    strategy: QueryStrategy = QueryStrategy.RAW
    as_of_date: date
    top_k: int = Field(default=3, ge=1, le=20)
    idempotency_key: str = Field(min_length=1, max_length=255, repr=False)
    correlation_id: str = Field(min_length=1, max_length=128)


class StartPolicyRetrievalRunResult(_DTO):
    run: PolicyRetrievalRun
    replayed: bool


class ExecutePolicyRetrievalRunCommand(_DTO):
    event_id: str
    tenant_id: str
    case_id: str
    retrieval_run_id: str
    correlation_id: str

    @field_validator("event_id", "tenant_id", "case_id", "retrieval_run_id")
    @classmethod
    def validate_uuid_identifiers(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as error:
            raise ValueError("worker identifiers must be UUIDs") from error
        return value


def canonical_request_hash(case_id: str, command: StartPolicyRetrievalRunCommand) -> str:
    payload = {
        "case_id": case_id,
        "analysis_run_id": command.analysis_run_id,
        "strategy": command.strategy.value,
        "as_of_date": command.as_of_date.isoformat(),
        "top_k": command.top_k,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class StartPolicyRetrievalRun:
    def __init__(
        self,
        repository: PolicyRetrievalRunRepository,
        *,
        model_route_resolver: ActiveModelRouteResolver | None = None,
    ) -> None:
        self._repository = repository
        self._model_route_resolver = model_route_resolver

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        command: StartPolicyRetrievalRunCommand,
    ) -> StartPolicyRetrievalRunResult:
        principal.require(Permission.ANALYSIS_CREATE)
        request_hash = canonical_request_hash(case_id, command)
        replay = self._repository.get_by_idempotency_key(
            tenant_id=principal.tenant_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return StartPolicyRetrievalRunResult(run=replay, replayed=True)
        execution_mode = self._repository.get_execution_mode(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            analysis_run_id=command.analysis_run_id,
        )
        route_plan_id: str | None = None
        route_contract: str | None = None
        if command.strategy is QueryStrategy.LLM and self._model_route_resolver is not None:
            route = self._model_route_resolver.execute(
                tenant_id=principal.tenant_id,
                task=ModelReleaseTask.POLICY_QUERY_BUILDER_V1,
                execution_mode=execution_mode,
            )
            route_plan_id = route.route_plan.id
            route_contract = MODEL_ROUTE_ENFORCEMENT_CONTRACT_VERSION
        run, replayed = self._repository.create(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            analysis_run_id=command.analysis_run_id,
            strategy=command.strategy.value,
            as_of_date=command.as_of_date.isoformat(),
            top_k=command.top_k,
            requested_by=principal.user_id,
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            execution_mode=execution_mode,
            model_route_plan_id=route_plan_id,
            route_enforcement_contract_version=route_contract,
        )
        return StartPolicyRetrievalRunResult(run=run, replayed=replayed)


class ListPolicyRetrievalRuns:
    def __init__(self, repository: PolicyRetrievalRunRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> tuple[PolicyRetrievalRun, ...]:
        principal.require(Permission.POLICY_READ)
        return self._repository.list(tenant_id=principal.tenant_id, case_id=case_id)


class GetPolicyRetrievalRun:
    def __init__(self, repository: PolicyRetrievalRunRepository) -> None:
        self._repository = repository

    def execute(
        self, *, principal: Principal, case_id: str, run_id: str
    ) -> PolicyRetrievalRunDetail:
        principal.require(Permission.POLICY_READ)
        detail = self._repository.get(tenant_id=principal.tenant_id, case_id=case_id, run_id=run_id)
        if detail is None:
            raise CaseNotFoundError("The requested policy retrieval run was not found.")
        return detail


class ExecutePolicyRetrievalRun:
    """Thin orchestration: strategy, fixed HYBRID retrieval, fusion, persistence."""

    def __init__(
        self,
        *,
        repository: PolicyRetrievalRunRepository,
        search: SearchPolicyClauses,
        llm: LLMProvider,
        prompt: PromptManifest,
        model_route_guard: PinnedModelRouteExecutionGuard | None = None,
    ) -> None:
        self._repository = repository
        self._search = search
        self._llm = llm
        self._prompt = prompt
        self._model_route_guard = model_route_guard

    def execute(self, command: ExecutePolicyRetrievalRunCommand) -> str:
        source = self._repository.claim(
            event_id=command.event_id,
            tenant_id=command.tenant_id,
            case_id=command.case_id,
            run_id=command.retrieval_run_id,
            correlation_id=command.correlation_id,
        )
        if source is None:
            return "NOOP"
        raw_hash: str | None = None
        try:
            if is_purged_customer_message(source.customer_message):
                raise ValueError("sensitive payload unavailable under retention policy")
            if source.run.strategy is QueryStrategy.RAW:
                plan = PolicyQueryPlan(
                    queries=(
                        PolicyQuery(
                            query_id="Q1",
                            purpose=PolicyQueryPurpose.PRIMARY_POLICY,
                            text=source.customer_message,
                        ),
                    ),
                    filter_hints=QueryFilterHints(
                        product_categories=(source.builder_input.trusted_metadata.product_category,)
                    ),
                )
                raw_hash = hashlib.sha256(source.customer_message.encode()).hexdigest()
            elif source.run.strategy is QueryStrategy.DETERMINISTIC:
                plan = build_deterministic_query_plan(source.builder_input)
            else:
                route_plan_id = getattr(source.run, "model_route_plan_id", None)
                if route_plan_id is not None:
                    if self._model_route_guard is None:
                        raise PinnedModelRoutePlanRequiredError()
                    self._model_route_guard.execute(
                        tenant_id=source.run.tenant_id,
                        route_plan_id=route_plan_id,
                        task=ModelReleaseTask.POLICY_QUERY_BUILDER_V1,
                        execution_mode=getattr(
                            source.run,
                            "execution_mode",
                            AnalysisExecutionMode.PRIMARY,
                        ),
                    )
                elif self._model_route_guard is not None:
                    raise PinnedModelRoutePlanRequiredError()
                plan = self._llm.build_policy_queries(source.builder_input, self._prompt).plan
            principal = Principal(
                user_id="policy-retrieval-worker",
                tenant_id=source.run.tenant_id,
                email="policy-retrieval-worker@local.invalid",
                display_name="Policy Retrieval Worker",
                roles=frozenset({Role.ADMIN}),
            )
            per_query = []
            per_query_nearest = []
            per_query_least = []
            for query in plan.queries:
                result = self._search.execute(
                    principal=principal,
                    query=PolicySearchQuery(
                        tenant_id=source.run.tenant_id,
                        query=query.text,
                        as_of_date=source.run.as_of_date,
                        mode=RetrievalMode.HYBRID,
                        top_k=20,
                        least_similar_k=3,
                        filters=PolicySearchFilters(
                            product_categories=(
                                source.builder_input.trusted_metadata.product_category,
                            )
                        ),
                    ),
                )
                per_query.append((query.query_id, result.hits))
                per_query_nearest.append(
                    (query.query_id, getattr(result, "nearest_dense_hits", ()))
                )
                per_query_least.append((query.query_id, getattr(result, "least_similar_hits", ())))
            hits = fuse_multi_query_hits(
                results=tuple(per_query),
                profile=MultiQueryFusionProfile(),
                top_k=source.run.top_k,
            )
            diagnostics = build_policy_similarity_diagnostics(
                nearest_results=tuple(per_query_nearest),
                least_results=tuple(per_query_least),
            )
        except Exception as error:
            code = getattr(error, "code", "POLICY_RETRIEVAL_FAILED")
            if code.startswith("LLM_"):
                code = {
                    "LLM_PROVIDER_UNAVAILABLE": "POLICY_QUERY_BUILDER_PROVIDER_UNAVAILABLE",
                    "LLM_PROVIDER_TIMEOUT": "POLICY_QUERY_BUILDER_TIMEOUT",
                    "LLM_INVALID_STRUCTURED_OUTPUT": "POLICY_QUERY_BUILDER_INVALID_OUTPUT",
                }.get(code, code)
            if isinstance(error, PolicyQueryBuilderInvalidOutputError):
                code = error.code
            persisted = self._repository.fail(
                tenant_id=source.run.tenant_id,
                run_id=source.run.id,
                event_id=command.event_id,
                claim_token=source.claim_token,
                code=str(code),
                message="Policy retrieval execution failed.",
            )
            return "FAILED" if persisted else "FENCED"
        persisted = self._repository.succeed(
            tenant_id=source.run.tenant_id,
            run_id=source.run.id,
            event_id=command.event_id,
            claim_token=source.claim_token,
            plan=plan,
            hits=hits,
            raw_query_hash=raw_hash,
            diagnostics=diagnostics,
        )
        return "SUCCEEDED" if persisted else "FENCED"

    def record_failure(
        self,
        command: ExecutePolicyRetrievalRunCommand,
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
            code="POLICY_RETRIEVAL_QUEUE_PAYLOAD_INVALID",
            message="Policy retrieval queue payload failed UUID validation.",
        )


__all__ = [
    "ExecutePolicyRetrievalRun",
    "ExecutePolicyRetrievalRunCommand",
    "GetPolicyRetrievalRun",
    "ListPolicyRetrievalRuns",
    "StartPolicyRetrievalRun",
    "StartPolicyRetrievalRunCommand",
    "StartPolicyRetrievalRunResult",
    "canonical_request_hash",
]
