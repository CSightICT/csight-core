"""SQLAlchemy adapter for append-only policy retrieval runs and provenance."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    AnalysisRunModel,
    CaseEvidenceModel,
    CaseModel,
    LLMExtractionResultV2Model,
    PolicyClauseModel,
    PolicyIndexVersionModel,
    PolicyQueryBuilderProfileModel,
    PolicyRetrievalOutboxEventModel,
    PolicyRetrievalRunHitModel,
    PolicyRetrievalRunModel,
    PolicyRetrievalRunQueryModel,
)
from app.adapters.persistence.policy_repositories import to_policy_clause_record
from app.platform.analysis.llm_v2 import (
    ActionConsistency,
    CompletenessResult,
    LLMTextExtractionResultV2,
    SystemMissingInformation,
)
from app.platform.errors import CaseNotFoundError, IdempotencyKeyReusedError, ValidationError
from app.platform.policy_retrieval import PolicySearchHit, stable_json_hash
from app.platform.query_builder import (
    MultiQueryHit,
    PolicyQuery,
    PolicyQueryBuilderInput,
    PolicyQueryPlan,
    PolicyQueryPurpose,
    PolicyRetrievalRun,
    QueryFilterHints,
    QueryRank,
    QueryStrategy,
    RetrievalRunStatus,
    TrustedCaseMetadata,
)
from app.ports.policy_query_runs import PolicyRetrievalExecutionSource, PolicyRetrievalRunDetail

_NAMESPACE = UUID("ebd83a36-7c53-4d31-9ea0-c9517878be48")


class SQLAlchemyPolicyRetrievalRunRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def create(
        self,
        *,
        tenant_id: str,
        case_id: str,
        analysis_run_id: str,
        strategy: str,
        as_of_date: str,
        top_k: int,
        requested_by: str,
        correlation_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[PolicyRetrievalRun, bool]:
        tenant_uuid, case_uuid, analysis_uuid = map(UUID, (tenant_id, case_id, analysis_run_id))
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            existing = session.scalar(
                select(PolicyRetrievalRunModel).where(
                    PolicyRetrievalRunModel.tenant_id == tenant_uuid,
                    PolicyRetrievalRunModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise IdempotencyKeyReusedError()
                return _to_run(existing), True
            case_row = session.scalar(
                select(CaseModel).where(
                    CaseModel.tenant_id == tenant_uuid, CaseModel.id == case_uuid
                )
            )
            if case_row is None:
                raise CaseNotFoundError()
            analysis = session.scalar(
                select(AnalysisRunModel).where(
                    AnalysisRunModel.tenant_id == tenant_uuid,
                    AnalysisRunModel.id == analysis_uuid,
                    AnalysisRunModel.case_id == case_uuid,
                    AnalysisRunModel.status.in_(("SUCCEEDED", "PARTIAL_SUCCESS")),
                )
            )
            if analysis is None:
                raise ValidationError("A successful v2 analysis run for this Case is required.")
            text_result = session.scalar(
                select(LLMExtractionResultV2Model).where(
                    LLMExtractionResultV2Model.tenant_id == tenant_uuid,
                    LLMExtractionResultV2Model.analysis_run_id == analysis_uuid,
                )
            )
            if text_result is None:
                raise ValidationError("Text Extraction v2 result is required; v1 is not accepted.")
            index = session.scalar(
                select(PolicyIndexVersionModel).where(
                    PolicyIndexVersionModel.tenant_id == tenant_uuid,
                    PolicyIndexVersionModel.status == "ACTIVE",
                )
            )
            if index is None:
                raise ValidationError("An active policy index is required.")
            profile = _ensure_profile(session, QueryStrategy(strategy))
            run_row = PolicyRetrievalRunModel(
                id=uuid4(),
                tenant_id=tenant_uuid,
                case_id=case_uuid,
                analysis_run_id=analysis_uuid,
                text_result_id=text_result.id,
                strategy=strategy,
                status="QUEUED",
                as_of_date=date.fromisoformat(as_of_date),
                top_k=top_k,
                query_builder_profile_id=profile.id,
                base_index_version_id=index.id,
                base_retrieval_profile_hash=stable_json_hash(
                    {
                        "index_version": index.index_version,
                        "lexical": [index.lexical_profile_name, index.lexical_profile_version],
                        "dense": str(index.embedding_profile_id),
                        "fusion": [index.fusion_profile_name, index.fusion_profile_version],
                    }
                ),
                multi_query_fusion_profile="policy_multi_query_rrf",
                multi_query_fusion_version="1.0.0",
                requested_by=UUID(requested_by),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                started_at=None,
                completed_at=None,
                failure_code=None,
                failure_message=None,
                created_at=now,
            )
            session.add(run_row)
            session.flush()
            session.add(
                PolicyRetrievalOutboxEventModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    retrieval_run_id=run_row.id,
                    correlation_id=correlation_id,
                    status="PENDING",
                    attempt_count=0,
                    available_at=now,
                    created_at=now,
                )
            )
            session.flush()
            return _to_run(run_row), False

    def list(self, *, tenant_id: str, case_id: str) -> tuple[PolicyRetrievalRun, ...]:
        with self._factory() as session:
            rows = session.scalars(
                select(PolicyRetrievalRunModel)
                .where(
                    PolicyRetrievalRunModel.tenant_id == UUID(tenant_id),
                    PolicyRetrievalRunModel.case_id == UUID(case_id),
                )
                .order_by(PolicyRetrievalRunModel.created_at.desc(), PolicyRetrievalRunModel.id)
            ).all()
        return tuple(_to_run(row) for row in rows)

    def get(self, *, tenant_id: str, case_id: str, run_id: str) -> PolicyRetrievalRunDetail | None:
        with self._factory() as session:
            row = session.scalar(
                select(PolicyRetrievalRunModel).where(
                    PolicyRetrievalRunModel.tenant_id == UUID(tenant_id),
                    PolicyRetrievalRunModel.case_id == UUID(case_id),
                    PolicyRetrievalRunModel.id == UUID(run_id),
                )
            )
            if row is None:
                return None
            index = session.get(PolicyIndexVersionModel, row.base_index_version_id)
            queries = session.scalars(
                select(PolicyRetrievalRunQueryModel)
                .where(
                    PolicyRetrievalRunQueryModel.tenant_id == row.tenant_id,
                    PolicyRetrievalRunQueryModel.retrieval_run_id == row.id,
                )
                .order_by(PolicyRetrievalRunQueryModel.position)
            ).all()
            case_message = session.scalar(
                select(CaseModel.customer_message).where(CaseModel.id == row.case_id)
            )
            plan = _to_plan(queries, case_message) if queries else None
            hit_rows = session.execute(
                select(PolicyRetrievalRunHitModel, PolicyClauseModel)
                .join(
                    PolicyClauseModel,
                    PolicyClauseModel.id == PolicyRetrievalRunHitModel.policy_clause_row_id,
                )
                .where(
                    PolicyRetrievalRunHitModel.tenant_id == row.tenant_id,
                    PolicyRetrievalRunHitModel.retrieval_run_id == row.id,
                )
                .order_by(PolicyRetrievalRunHitModel.rank)
            ).all()
            hits = tuple(_to_hit(hit, clause) for hit, clause in hit_rows)
            assert index is not None
            return PolicyRetrievalRunDetail(
                run=_to_run(row),
                query_plan=plan,
                hits=hits,
                index_version=index.index_version,
                base_retrieval_profile_hash=row.base_retrieval_profile_hash,
                multi_query_fusion_profile=(
                    f"{row.multi_query_fusion_profile}:{row.multi_query_fusion_version}"
                ),
            )

    def claim(self, *, tenant_id: str, run_id: str) -> PolicyRetrievalExecutionSource | None:
        tenant_uuid, run_uuid = UUID(tenant_id), UUID(run_id)
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            claimed = session.execute(
                update(PolicyRetrievalRunModel)
                .where(
                    PolicyRetrievalRunModel.tenant_id == tenant_uuid,
                    PolicyRetrievalRunModel.id == run_uuid,
                    PolicyRetrievalRunModel.status == "QUEUED",
                )
                .values(status="RUNNING", started_at=now)
                .returning(PolicyRetrievalRunModel.id)
            ).scalar_one_or_none()
            if claimed is None:
                return None
            row = session.get(PolicyRetrievalRunModel, run_uuid)
            assert row is not None
            case = session.get(CaseModel, row.case_id)
            result = session.get(LLMExtractionResultV2Model, row.text_result_id)
            assert case is not None and result is not None
            image_count = session.scalar(
                select(func.count())
                .select_from(CaseEvidenceModel)
                .where(
                    CaseEvidenceModel.tenant_id == tenant_uuid,
                    CaseEvidenceModel.case_id == row.case_id,
                    CaseEvidenceModel.evidence_type == "IMAGE",
                    CaseEvidenceModel.upload_status == "AVAILABLE",
                )
            )
            extraction = LLMTextExtractionResultV2.model_validate(
                {
                    "schema_version": result.schema_version,
                    "language": result.language,
                    "issue_types": result.issue_types,
                    "claims": result.claims,
                    "requested_actions": result.requested_actions,
                    "text_ambiguities": result.text_ambiguities,
                    "summary": result.summary,
                }
            )
            attributes = case.attributes
            return PolicyRetrievalExecutionSource(
                run=_to_run(row),
                customer_message=case.customer_message,
                builder_input=PolicyQueryBuilderInput(
                    extraction=extraction,
                    completeness=CompletenessResult(
                        system_missing_information=tuple(
                            SystemMissingInformation(value)
                            for value in result.system_missing_information
                        ),
                        action_consistency=ActionConsistency(result.action_consistency),
                    ),
                    trusted_metadata=TrustedCaseMetadata(
                        product_category=str(attributes.get("product_category", "GENERAL")),
                        days_since_purchase=_optional_int(attributes.get("days_since_purchase")),
                        available_image_count=int(image_count or 0),
                        exception_context=bool(attributes.get("exception_context", False)),
                        escalation_context=bool(attributes.get("escalation_context", False)),
                    ),
                ),
            )

    def succeed(
        self,
        *,
        tenant_id: str,
        run_id: str,
        plan: PolicyQueryPlan,
        hits: tuple[MultiQueryHit, ...],
        raw_query_hash: str | None,
    ) -> None:
        tenant_uuid, run_uuid = UUID(tenant_id), UUID(run_id)
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            for position, query in enumerate(plan.queries, start=1):
                raw = raw_query_hash is not None and position == 1
                session.add(
                    PolicyRetrievalRunQueryModel(
                        id=uuid4(),
                        tenant_id=tenant_uuid,
                        retrieval_run_id=run_uuid,
                        query_id=query.query_id,
                        purpose=query.purpose.value,
                        query_text=None if raw else query.text,
                        query_source="CASE_CUSTOMER_MESSAGE" if raw else "GENERATED",
                        query_hash=raw_query_hash
                        if raw
                        else hashlib.sha256(query.text.encode()).hexdigest(),
                        position=position,
                        filter_hints=plan.filter_hints.model_dump(mode="json"),
                        created_at=now,
                    )
                )
            for hit in hits:
                session.add(
                    PolicyRetrievalRunHitModel(
                        id=uuid4(),
                        tenant_id=tenant_uuid,
                        retrieval_run_id=run_uuid,
                        rank=hit.rank,
                        policy_clause_row_id=UUID(hit.hit.clause.row_id),
                        fusion_score=hit.fusion_score,
                        best_query_rank=hit.best_query_rank,
                        matched_query_ids=list(hit.matched_query_ids),
                        per_query_ranks=[
                            value.model_dump(mode="json") for value in hit.per_query_ranks
                        ],
                        created_at=now,
                    )
                )
            session.execute(
                update(PolicyRetrievalRunModel)
                .where(
                    PolicyRetrievalRunModel.tenant_id == tenant_uuid,
                    PolicyRetrievalRunModel.id == run_uuid,
                    PolicyRetrievalRunModel.status == "RUNNING",
                )
                .values(status="SUCCEEDED", completed_at=now)
            )

    def fail(self, *, tenant_id: str, run_id: str, code: str, message: str) -> None:
        with self._factory.begin() as session:
            session.execute(
                update(PolicyRetrievalRunModel)
                .where(
                    PolicyRetrievalRunModel.tenant_id == UUID(tenant_id),
                    PolicyRetrievalRunModel.id == UUID(run_id),
                    PolicyRetrievalRunModel.status == "RUNNING",
                )
                .values(
                    status="FAILED",
                    completed_at=datetime.now(UTC),
                    failure_code=code[:128],
                    failure_message=message[:1000],
                )
            )


def _ensure_profile(session: Session, strategy: QueryStrategy) -> PolicyQueryBuilderProfileModel:
    profile_id = uuid5(_NAMESPACE, f"policy-query-builder:{strategy.value}:1.0.0")
    row = session.get(PolicyQueryBuilderProfileModel, profile_id)
    if row is not None:
        return row
    values = {
        "strategy": strategy.value,
        "schema_version": "1.0",
        "max_queries": 3,
        "max_query_tokens": 256,
        "filter_hint_policy": "validated_soft_only_not_applied",
        "filter_hint_policy_version": "1.0.0",
    }
    profile_hash = stable_json_hash(values)
    row = PolicyQueryBuilderProfileModel(
        id=profile_id,
        profile_name="policy_query_builder",
        profile_version=f"1.0.0-{strategy.value.lower()}",
        provider_name="vllm" if strategy is QueryStrategy.LLM else None,
        model_artifact="Qwen/Qwen3.8-27B" if strategy is QueryStrategy.LLM else None,
        model_revision=None,
        prompt_name="policy_query_builder" if strategy is QueryStrategy.LLM else None,
        prompt_version="1.1.0" if strategy is QueryStrategy.LLM else None,
        prompt_hash=None,
        rule_name="deterministic_policy_query" if strategy is QueryStrategy.DETERMINISTIC else None,
        rule_version="1.0.0" if strategy is QueryStrategy.DETERMINISTIC else None,
        rule_hash=None,
        profile_hash=profile_hash,
        created_at=datetime.now(UTC),
        **values,
    )
    session.add(row)
    session.flush()
    return row


def _to_run(row: PolicyRetrievalRunModel) -> PolicyRetrievalRun:
    return PolicyRetrievalRun(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        case_id=str(row.case_id),
        analysis_run_id=str(row.analysis_run_id),
        text_result_id=str(row.text_result_id),
        strategy=QueryStrategy(row.strategy),
        status=RetrievalRunStatus(row.status),
        as_of_date=row.as_of_date,
        top_k=row.top_k,
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        correlation_id=row.correlation_id,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        failure_code=row.failure_code,
        failure_message=row.failure_message,
    )


def _to_plan(
    rows: Sequence[PolicyRetrievalRunQueryModel], case_message: str | None
) -> PolicyQueryPlan:
    hints = QueryFilterHints.model_validate(rows[0].filter_hints)
    return PolicyQueryPlan(
        queries=tuple(
            PolicyQuery(
                query_id=row.query_id,
                purpose=PolicyQueryPurpose(row.purpose),
                text=(case_message or "Unavailable raw Case query")
                if row.query_text is None
                else row.query_text,
            )
            for row in rows
        ),
        filter_hints=hints,
    )


def _to_hit(row: PolicyRetrievalRunHitModel, clause: PolicyClauseModel) -> MultiQueryHit:
    return MultiQueryHit(
        hit=PolicySearchHit(
            clause=to_policy_clause_record(clause),
            fusion_rank=row.rank,
            fusion_score=row.fusion_score,
        ),
        rank=row.rank,
        fusion_score=row.fusion_score,
        best_query_rank=row.best_query_rank,
        matched_query_ids=tuple(str(value) for value in row.matched_query_ids),
        per_query_ranks=tuple(QueryRank.model_validate(value) for value in row.per_query_ranks),
    )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


__all__ = ["SQLAlchemyPolicyRetrievalRunRepository"]
