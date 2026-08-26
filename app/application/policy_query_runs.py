"""Case-to-policy retrieval run use cases composed only from ports."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.application.policy_retrieval import SearchPolicyClauses
from app.domains.product_defect_cs.query_builder import build_deterministic_query_plan
from app.platform.analysis.prompts import PromptManifest
from app.platform.errors import CaseNotFoundError
from app.platform.policy_retrieval import PolicySearchFilters, PolicySearchQuery, RetrievalMode
from app.platform.query_builder import (
    MultiQueryFusionProfile,
    PolicyQuery,
    PolicyQueryBuilderInvalidOutputError,
    PolicyQueryPlan,
    PolicyQueryPurpose,
    PolicyRetrievalRun,
    QueryFilterHints,
    QueryStrategy,
    fuse_multi_query_hits,
)
from app.platform.tenant import Permission, Principal, Role
from app.ports.llm import LLMProvider
from app.ports.policy_query_runs import PolicyRetrievalRunDetail, PolicyRetrievalRunRepository

CREATE_OPERATION = "policy_retrieval_run.create.v1"


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class StartPolicyRetrievalRunCommand(_DTO):
    analysis_run_id: str = Field(min_length=1)
    strategy: QueryStrategy
    as_of_date: date
    top_k: int = Field(default=10, ge=1, le=20)
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
    def __init__(self, repository: PolicyRetrievalRunRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        command: StartPolicyRetrievalRunCommand,
    ) -> StartPolicyRetrievalRunResult:
        principal.require(Permission.ANALYSIS_CREATE)
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
            request_hash=canonical_request_hash(case_id, command),
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
    ) -> None:
        self._repository = repository
        self._search = search
        self._llm = llm
        self._prompt = prompt

    def execute(self, command: ExecutePolicyRetrievalRunCommand) -> str:
        source = self._repository.claim(
            tenant_id=command.tenant_id, run_id=command.retrieval_run_id
        )
        if source is None:
            return "NOOP"
        raw_hash: str | None = None
        try:
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
                plan = self._llm.build_policy_queries(source.builder_input, self._prompt).plan
            principal = Principal(
                user_id="policy-retrieval-worker",
                tenant_id=source.run.tenant_id,
                email="policy-retrieval-worker@local.invalid",
                display_name="Policy Retrieval Worker",
                roles=frozenset({Role.ADMIN}),
            )
            per_query = []
            for query in plan.queries:
                result = self._search.execute(
                    principal=principal,
                    query=PolicySearchQuery(
                        tenant_id=source.run.tenant_id,
                        query=query.text,
                        as_of_date=source.run.as_of_date,
                        mode=RetrievalMode.HYBRID,
                        top_k=20,
                        filters=PolicySearchFilters(
                            product_categories=(
                                source.builder_input.trusted_metadata.product_category,
                            )
                        ),
                    ),
                )
                per_query.append((query.query_id, result.hits))
            hits = fuse_multi_query_hits(
                results=tuple(per_query),
                profile=MultiQueryFusionProfile(),
                top_k=source.run.top_k,
            )
            self._repository.succeed(
                tenant_id=source.run.tenant_id,
                run_id=source.run.id,
                plan=plan,
                hits=hits,
                raw_query_hash=raw_hash,
            )
            return "SUCCEEDED"
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
            self._repository.fail(
                tenant_id=source.run.tenant_id,
                run_id=source.run.id,
                code=str(code),
                message="Policy retrieval execution failed.",
            )
            return "FAILED"


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
