"""SQLAlchemy adapter for append-only policy retrieval runs and provenance."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.async_events import (
    begin_consumer_attempt,
    consumer_failure_may_terminalize_run,
    event_allows_completion,
    mark_event_consumed,
    mark_event_failed,
    record_rejected_dispatch_recovery,
    recover_dispatch_failure,
    validate_request_event,
)
from app.adapters.persistence.models import (
    AnalysisRunModel,
    CaseEvidenceModel,
    CaseModel,
    CaseSensitivePayloadModel,
    LLMExtractionResultV2Model,
    PolicyClauseModel,
    PolicyIndexVersionModel,
    PolicyQueryBuilderProfileModel,
    PolicyRetrievalOutboxEventModel,
    PolicyRetrievalRunHitModel,
    PolicyRetrievalRunModel,
    PolicyRetrievalRunQueryModel,
    PolicyRetrievalSimilarityModel,
)
from app.adapters.persistence.policy_repositories import to_policy_clause_record
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.analysis.llm_v2 import (
    ActionConsistency,
    CompletenessResult,
    LLMTextExtractionResultV2,
    SystemMissingInformation,
)
from app.platform.async_reliability import (
    AsyncEventIntegrityError,
    ExecutionAttemptsExhaustedError,
    ExecutionLeaseActiveError,
)
from app.platform.errors import (
    CaseNotFoundError,
    IdempotencyKeyReusedError,
    InconsistentPersistenceStateError,
    SensitivePayloadUnavailableError,
    ValidationError,
)
from app.platform.policy_retrieval import PolicySearchHit, stable_json_hash
from app.platform.privacy_lifecycle import PURGED_CUSTOMER_MESSAGE, is_purged_customer_message
from app.platform.query_builder import (
    MultiQueryHit,
    PolicyQuery,
    PolicyQueryBuilderInput,
    PolicyQueryPlan,
    PolicyQueryPurpose,
    PolicyRetrievalRun,
    PolicySimilarityDiagnostic,
    PolicySimilarityGroup,
    QueryFilterHints,
    QueryRank,
    QueryStrategy,
    RetrievalRunStatus,
    TrustedCaseMetadata,
)
from app.ports.policy_query_runs import (
    PolicyQueryBuildClaim,
    PolicyRetrievalExecutionSource,
    PolicyRetrievalRunDetail,
    PolicySearchExecutionSource,
)

_NAMESPACE = UUID("ebd83a36-7c53-4d31-9ea0-c9517878be48")


def _tenant_case_statement(*, tenant_id: UUID, case_id: UUID) -> Select[tuple[CaseModel]]:
    """Build the mandatory tenant-scoped Case lookup used by read and claim paths."""

    return select(CaseModel).where(
        CaseModel.tenant_id == tenant_id,
        CaseModel.id == case_id,
    )


def _tenant_case_message_statement(*, tenant_id: UUID, case_id: UUID) -> Select[tuple[str | None]]:
    """Build the tenant-scoped sensitive-message lookup for a retrieval detail."""

    return select(CaseSensitivePayloadModel.customer_message).where(
        CaseSensitivePayloadModel.tenant_id == tenant_id,
        CaseSensitivePayloadModel.case_id == case_id,
    )


class SQLAlchemyPolicyRetrievalRunRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        lease_ttl: timedelta = timedelta(minutes=5),
        max_execution_attempts: int = 4,
    ) -> None:
        self._factory = session_factory
        if lease_ttl.total_seconds() <= 0:
            raise ValueError("lease_ttl must be positive")
        self._lease_ttl = lease_ttl
        if max_execution_attempts <= 0:
            raise ValueError("max_execution_attempts must be positive")
        self._max_execution_attempts = max_execution_attempts

    def get_by_idempotency_key(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> PolicyRetrievalRun | None:
        with self._factory() as session:
            existing = session.scalar(
                select(PolicyRetrievalRunModel).where(
                    PolicyRetrievalRunModel.tenant_id == UUID(tenant_id),
                    PolicyRetrievalRunModel.idempotency_key == idempotency_key,
                )
            )
        if existing is None:
            return None
        if existing.request_hash != request_hash:
            raise IdempotencyKeyReusedError()
        return _to_run(existing)

    def get_execution_mode(
        self,
        *,
        tenant_id: str,
        case_id: str,
        analysis_run_id: str,
    ) -> AnalysisExecutionMode:
        with self._factory() as session:
            analysis = session.scalar(
                select(AnalysisRunModel).where(
                    AnalysisRunModel.tenant_id == UUID(tenant_id),
                    AnalysisRunModel.case_id == UUID(case_id),
                    AnalysisRunModel.id == UUID(analysis_run_id),
                    AnalysisRunModel.status.in_(("SUCCEEDED", "PARTIAL_SUCCESS")),
                )
            )
        if analysis is None:
            raise ValidationError("A successful v2 analysis run for this Case is required.")
        return AnalysisExecutionMode(analysis.execution_mode)

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
        execution_mode: AnalysisExecutionMode,
        model_route_plan_id: str | None,
        route_enforcement_contract_version: str | None,
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
            payload_row = session.scalar(
                select(CaseSensitivePayloadModel).where(
                    CaseSensitivePayloadModel.tenant_id == tenant_uuid,
                    CaseSensitivePayloadModel.case_id == case_uuid,
                )
            )
            if payload_row is None:
                raise InconsistentPersistenceStateError(
                    "The Case is missing its required sensitive-payload lifecycle record."
                )
            if payload_row.purged_at is not None:
                raise SensitivePayloadUnavailableError()
            if payload_row.customer_message is None:
                raise InconsistentPersistenceStateError(
                    "The active sensitive-payload lifecycle record has no content."
                )
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
            if AnalysisExecutionMode(analysis.execution_mode) is not execution_mode:
                raise ValidationError("The analysis execution mode changed before run creation.")
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
                execution_mode=execution_mode.value,
                model_route_plan_id=(
                    UUID(model_route_plan_id) if model_route_plan_id is not None else None
                ),
                route_enforcement_contract_version=route_enforcement_contract_version,
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
                    event_type="policy_query_build.requested.v2",
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
                _tenant_case_message_statement(
                    tenant_id=row.tenant_id,
                    case_id=row.case_id,
                )
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
            similarity_rows = session.execute(
                select(PolicyRetrievalSimilarityModel, PolicyClauseModel)
                .join(
                    PolicyClauseModel,
                    PolicyClauseModel.id == PolicyRetrievalSimilarityModel.policy_clause_row_id,
                )
                .where(
                    PolicyRetrievalSimilarityModel.tenant_id == row.tenant_id,
                    PolicyRetrievalSimilarityModel.retrieval_run_id == row.id,
                )
                .order_by(
                    PolicyRetrievalSimilarityModel.similarity_group,
                    PolicyRetrievalSimilarityModel.rank,
                )
            ).all()
            assert index is not None
            return PolicyRetrievalRunDetail(
                run=_to_run(row),
                query_plan=plan,
                hits=hits,
                policy_similarity=tuple(
                    PolicySimilarityDiagnostic(
                        hit=PolicySearchHit(
                            clause=to_policy_clause_record(clause),
                            dense_score=evidence.cosine_similarity,
                        ),
                        group=PolicySimilarityGroup(evidence.similarity_group),
                        rank=evidence.rank,
                        cosine_similarity=evidence.cosine_similarity,
                        reference_threshold=evidence.reference_threshold,
                        threshold_version=evidence.threshold_version,
                        matched_query_ids=tuple(str(value) for value in evidence.matched_query_ids),
                        reason_codes=tuple(str(value) for value in evidence.reason_codes),
                    )
                    for evidence, clause in similarity_rows
                ),
                index_version=index.index_version,
                base_retrieval_profile_hash=row.base_retrieval_profile_hash,
                multi_query_fusion_profile=(
                    f"{row.multi_query_fusion_profile}:{row.multi_query_fusion_version}"
                ),
            )

    def claim(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        run_id: str,
        correlation_id: str,
        expected_event_types: frozenset[str] = frozenset({"policy_retrieval.requested.v1"}),
        claimable_statuses: frozenset[str] = frozenset({"QUEUED", "RUNNING"}),
    ) -> PolicyRetrievalExecutionSource | None:
        event_uuid, tenant_uuid, case_uuid, run_uuid = map(
            UUID, (event_id, tenant_id, case_id, run_id)
        )
        now = datetime.now(UTC)
        claim_token = uuid4()
        deferred_error: RuntimeError | None = None
        source: PolicyRetrievalExecutionSource | None = None
        with self._factory.begin() as session:
            event = session.scalar(
                select(PolicyRetrievalOutboxEventModel)
                .where(PolicyRetrievalOutboxEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None:
                raise AsyncEventIntegrityError(
                    code="POLICY_RETRIEVAL_EVENT_NOT_FOUND",
                    message="The policy retrieval request event was not found.",
                )
            dispatch_failure = (
                event.status == "FAILED" and event.failure_code == "POLICY_RETRIEVAL_OUTBOX_FAILED"
            )
            integrity_error = (
                AsyncEventIntegrityError(
                    code="POLICY_RETRIEVAL_EVENT_TYPE_MISMATCH",
                    message="The policy retrieval event type does not match this worker.",
                )
                if event.event_type not in expected_event_types
                else validate_request_event(
                    event,
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    correlation_id=correlation_id,
                    run_id=run_uuid,
                    run_attribute="retrieval_run_id",
                )
            )
            if (
                dispatch_failure
                and integrity_error is not None
                and integrity_error.code == "ASYNC_EVENT_STATE_INVALID"
            ):
                recover_dispatch_failure(
                    event,
                    now=now,
                    dispatch_failure_code="POLICY_RETRIEVAL_OUTBOX_FAILED",
                )
                integrity_error = validate_request_event(
                    event,
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    correlation_id=correlation_id,
                    run_id=run_uuid,
                    run_attribute="retrieval_run_id",
                )
            if event.status == "CONSUMED" or (event.status == "FAILED" and not dispatch_failure):
                return None
            begin_consumer_attempt(event)
            if integrity_error is not None:
                actual_run = session.scalar(
                    select(PolicyRetrievalRunModel)
                    .where(
                        PolicyRetrievalRunModel.tenant_id == event.tenant_id,
                        PolicyRetrievalRunModel.id == event.retrieval_run_id,
                    )
                    .with_for_update()
                )
                may_terminalize = actual_run is None or consumer_failure_may_terminalize_run(
                    status=actual_run.status,
                    lease_expires_at=actual_run.lease_expires_at,
                    now=now,
                )
                if actual_run is not None and may_terminalize:
                    actual_run.status = "FAILED"
                    actual_run.started_at = actual_run.started_at or now
                    actual_run.completed_at = now
                    actual_run.failure_code = "POLICY_RETRIEVAL_EVENT_INTEGRITY_FAILED"
                    actual_run.failure_message = "Policy retrieval event integrity failed."
                    actual_run.claim_token = None
                    actual_run.lease_expires_at = None
                if not may_terminalize:
                    event.consumer_last_error = (
                        "Rejected mismatched delivery while a newer execution lease is active."
                    )
                elif dispatch_failure:
                    record_rejected_dispatch_recovery(event, message=str(integrity_error))
                else:
                    mark_event_failed(
                        event,
                        now=now,
                        code=integrity_error.code,
                        message=str(integrity_error),
                    )
                deferred_error = integrity_error
            else:
                row = session.scalar(
                    select(PolicyRetrievalRunModel)
                    .where(
                        PolicyRetrievalRunModel.tenant_id == tenant_uuid,
                        PolicyRetrievalRunModel.id == run_uuid,
                    )
                    .with_for_update()
                )
                if row is None or row.case_id != case_uuid:
                    error = AsyncEventIntegrityError(
                        code="POLICY_RETRIEVAL_RUN_MISMATCH",
                        message="The policy retrieval run does not match the request event.",
                    )
                    mark_event_failed(event, now=now, code=error.code, message=str(error))
                    deferred_error = error
                elif row.status in {"SUCCEEDED", "FAILED"}:
                    mark_event_consumed(event, now=now)
                elif row.status not in claimable_statuses:
                    source = None
                elif (
                    row.status == "RUNNING"
                    and row.lease_expires_at is not None
                    and row.lease_expires_at > now
                ):
                    event.consumer_last_error = "Execution lease is still active."
                    deferred_error = ExecutionLeaseActiveError(retry_at=row.lease_expires_at)
                elif row.execution_attempt_count >= self._max_execution_attempts:
                    row.status = "FAILED"
                    row.completed_at = now
                    row.failure_code = "POLICY_RETRIEVAL_WORKER_ATTEMPTS_EXHAUSTED"
                    row.failure_message = "Policy retrieval worker recovery attempts exhausted."
                    row.claim_token = None
                    row.lease_expires_at = None
                    mark_event_failed(
                        event,
                        now=now,
                        code="POLICY_RETRIEVAL_WORKER_ATTEMPTS_EXHAUSTED",
                        message="Policy retrieval worker recovery attempts exhausted.",
                    )
                    deferred_error = ExecutionAttemptsExhaustedError(
                        code="POLICY_RETRIEVAL_WORKER_ATTEMPTS_EXHAUSTED"
                    )
                else:
                    row.status = "RUNNING"
                    row.started_at = row.started_at or now
                    row.claim_token = claim_token
                    row.lease_expires_at = now + self._lease_ttl
                    row.execution_attempt_count += 1
                    case = session.scalar(
                        _tenant_case_statement(
                            tenant_id=tenant_uuid,
                            case_id=row.case_id,
                        )
                    )
                    payload = session.scalar(
                        select(CaseSensitivePayloadModel).where(
                            CaseSensitivePayloadModel.tenant_id == tenant_uuid,
                            CaseSensitivePayloadModel.case_id == row.case_id,
                        )
                    )
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
                        ),
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
                    customer_message = (
                        payload.customer_message
                        if payload is not None
                        and payload.purged_at is None
                        and payload.customer_message is not None
                        else PURGED_CUSTOMER_MESSAGE
                    )
                    source = PolicyRetrievalExecutionSource(
                        run=_to_run(row),
                        claim_token=str(claim_token),
                        customer_message=customer_message,
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
                                days_since_purchase=_optional_int(
                                    attributes.get("days_since_purchase")
                                ),
                                available_image_count=int(image_count or 0),
                                exception_context=bool(attributes.get("exception_context", False)),
                                escalation_context=bool(
                                    attributes.get("escalation_context", False)
                                ),
                            ),
                        ),
                    )
        if deferred_error is not None:
            raise deferred_error
        return source

    def claim_query_build(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        run_id: str,
        correlation_id: str,
    ) -> PolicyQueryBuildClaim:
        source = self.claim(
            event_id=event_id,
            tenant_id=tenant_id,
            case_id=case_id,
            run_id=run_id,
            correlation_id=correlation_id,
            expected_event_types=frozenset({"policy_query_build.requested.v2"}),
            claimable_statuses=frozenset({"QUEUED", "RUNNING"}),
        )
        if source is not None:
            return PolicyQueryBuildClaim(disposition="CLAIMED", source=source)
        with self._factory() as session:
            status = session.scalar(
                select(PolicyRetrievalRunModel.status).where(
                    PolicyRetrievalRunModel.tenant_id == UUID(tenant_id),
                    PolicyRetrievalRunModel.id == UUID(run_id),
                )
            )
        if status == "SEARCH_QUEUED":
            return PolicyQueryBuildClaim(disposition="SEARCH_QUEUED")
        return PolicyQueryBuildClaim(disposition="NOOP")

    def complete_query_build(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_id: str,
        claim_token: str,
        plan: PolicyQueryPlan,
        raw_query_hash: str | None,
    ) -> bool:
        tenant_uuid, run_uuid = UUID(tenant_id), UUID(run_id)
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            event = session.scalar(
                select(PolicyRetrievalOutboxEventModel)
                .where(
                    PolicyRetrievalOutboxEventModel.tenant_id == tenant_uuid,
                    PolicyRetrievalOutboxEventModel.id == UUID(event_id),
                    PolicyRetrievalOutboxEventModel.retrieval_run_id == run_uuid,
                    PolicyRetrievalOutboxEventModel.event_type == "policy_query_build.requested.v2",
                )
                .with_for_update()
            )
            if event is None or not event_allows_completion(
                event,
                dispatch_failure_code="POLICY_RETRIEVAL_OUTBOX_FAILED",
            ):
                return False
            run = session.scalar(
                select(PolicyRetrievalRunModel)
                .where(
                    PolicyRetrievalRunModel.tenant_id == tenant_uuid,
                    PolicyRetrievalRunModel.id == run_uuid,
                    PolicyRetrievalRunModel.status == "RUNNING",
                    PolicyRetrievalRunModel.claim_token == UUID(claim_token),
                )
                .with_for_update()
            )
            if run is None:
                return False
            _persist_query_plan(
                session,
                tenant_id=tenant_uuid,
                run_id=run_uuid,
                plan=plan,
                raw_query_hash=raw_query_hash,
                now=now,
            )
            run.status = "SEARCH_QUEUED"
            run.claim_token = None
            run.lease_expires_at = None
            mark_event_consumed(event, now=now)
            session.add(
                PolicyRetrievalOutboxEventModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    case_id=run.case_id,
                    retrieval_run_id=run_uuid,
                    event_type="policy_search.requested.v2",
                    correlation_id=run.correlation_id,
                    status="PENDING",
                    attempt_count=0,
                    available_at=now,
                    created_at=now,
                )
            )
            return True

    def claim_search(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        run_id: str,
        correlation_id: str,
    ) -> PolicySearchExecutionSource | None:
        source = self.claim(
            event_id=event_id,
            tenant_id=tenant_id,
            case_id=case_id,
            run_id=run_id,
            correlation_id=correlation_id,
            expected_event_types=frozenset({"policy_search.requested.v2"}),
            claimable_statuses=frozenset({"SEARCH_QUEUED", "RUNNING"}),
        )
        if source is None:
            return None
        with self._factory() as session:
            rows = session.scalars(
                select(PolicyRetrievalRunQueryModel)
                .where(
                    PolicyRetrievalRunQueryModel.tenant_id == UUID(tenant_id),
                    PolicyRetrievalRunQueryModel.retrieval_run_id == UUID(run_id),
                )
                .order_by(PolicyRetrievalRunQueryModel.position)
            ).all()
        if not rows:
            self.fail(
                tenant_id=source.run.tenant_id,
                run_id=source.run.id,
                event_id=event_id,
                claim_token=source.claim_token,
                code="POLICY_SEARCH_QUERY_PLAN_MISSING",
                message="The policy search run has no durable query plan.",
            )
            return None
        if any(row.query_text is None for row in rows) and is_purged_customer_message(
            source.customer_message
        ):
            self.fail(
                tenant_id=source.run.tenant_id,
                run_id=source.run.id,
                event_id=event_id,
                claim_token=source.claim_token,
                code="POLICY_SEARCH_SENSITIVE_PAYLOAD_UNAVAILABLE",
                message="The raw policy query expired before search execution.",
            )
            return None
        return PolicySearchExecutionSource(
            run=source.run,
            claim_token=source.claim_token,
            plan=_to_plan(rows, source.customer_message),
            builder_input=source.builder_input,
        )

    def complete_search(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_id: str,
        claim_token: str,
        hits: tuple[MultiQueryHit, ...],
        diagnostics: tuple[PolicySimilarityDiagnostic, ...] = (),
    ) -> bool:
        tenant_uuid, run_uuid = UUID(tenant_id), UUID(run_id)
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            event = session.scalar(
                select(PolicyRetrievalOutboxEventModel)
                .where(
                    PolicyRetrievalOutboxEventModel.tenant_id == tenant_uuid,
                    PolicyRetrievalOutboxEventModel.id == UUID(event_id),
                    PolicyRetrievalOutboxEventModel.retrieval_run_id == run_uuid,
                    PolicyRetrievalOutboxEventModel.event_type == "policy_search.requested.v2",
                )
                .with_for_update()
            )
            if event is None or not event_allows_completion(
                event,
                dispatch_failure_code="POLICY_RETRIEVAL_OUTBOX_FAILED",
            ):
                return False
            run = session.scalar(
                select(PolicyRetrievalRunModel)
                .where(
                    PolicyRetrievalRunModel.tenant_id == tenant_uuid,
                    PolicyRetrievalRunModel.id == run_uuid,
                    PolicyRetrievalRunModel.status == "RUNNING",
                    PolicyRetrievalRunModel.claim_token == UUID(claim_token),
                )
                .with_for_update()
            )
            if run is None:
                return False
            _persist_search_results(
                session,
                tenant_id=tenant_uuid,
                run_id=run_uuid,
                hits=hits,
                diagnostics=diagnostics,
                now=now,
            )
            run.status = "SUCCEEDED"
            run.completed_at = now
            run.claim_token = None
            run.lease_expires_at = None
            mark_event_consumed(event, now=now)
            return True

    def succeed(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_id: str,
        claim_token: str,
        plan: PolicyQueryPlan,
        hits: tuple[MultiQueryHit, ...],
        raw_query_hash: str | None,
        diagnostics: tuple[PolicySimilarityDiagnostic, ...] = (),
    ) -> bool:
        tenant_uuid, run_uuid = UUID(tenant_id), UUID(run_id)
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            event = session.scalar(
                select(PolicyRetrievalOutboxEventModel)
                .where(
                    PolicyRetrievalOutboxEventModel.tenant_id == tenant_uuid,
                    PolicyRetrievalOutboxEventModel.id == UUID(event_id),
                    PolicyRetrievalOutboxEventModel.retrieval_run_id == run_uuid,
                )
                .with_for_update()
            )
            if event is None or not event_allows_completion(
                event,
                dispatch_failure_code="POLICY_RETRIEVAL_OUTBOX_FAILED",
            ):
                return False
            run = session.scalar(
                select(PolicyRetrievalRunModel)
                .where(
                    PolicyRetrievalRunModel.tenant_id == tenant_uuid,
                    PolicyRetrievalRunModel.id == run_uuid,
                    PolicyRetrievalRunModel.status == "RUNNING",
                    PolicyRetrievalRunModel.claim_token == UUID(claim_token),
                )
                .with_for_update()
            )
            if run is None:
                return False
            _persist_query_plan(
                session,
                tenant_id=tenant_uuid,
                run_id=run_uuid,
                plan=plan,
                raw_query_hash=raw_query_hash,
                now=now,
            )
            _persist_search_results(
                session,
                tenant_id=tenant_uuid,
                run_id=run_uuid,
                hits=hits,
                diagnostics=diagnostics,
                now=now,
            )
            run.status = "SUCCEEDED"
            run.completed_at = now
            run.claim_token = None
            run.lease_expires_at = None
            mark_event_consumed(event, now=now)
            return True

    def fail(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_id: str,
        claim_token: str,
        code: str,
        message: str,
    ) -> bool:
        with self._factory.begin() as session:
            now = datetime.now(UTC)
            event = session.scalar(
                select(PolicyRetrievalOutboxEventModel)
                .where(
                    PolicyRetrievalOutboxEventModel.tenant_id == UUID(tenant_id),
                    PolicyRetrievalOutboxEventModel.id == UUID(event_id),
                    PolicyRetrievalOutboxEventModel.retrieval_run_id == UUID(run_id),
                )
                .with_for_update()
            )
            if event is None or not event_allows_completion(
                event,
                dispatch_failure_code="POLICY_RETRIEVAL_OUTBOX_FAILED",
            ):
                return False
            run = session.scalar(
                select(PolicyRetrievalRunModel)
                .where(
                    PolicyRetrievalRunModel.tenant_id == UUID(tenant_id),
                    PolicyRetrievalRunModel.id == UUID(run_id),
                    PolicyRetrievalRunModel.status == "RUNNING",
                    PolicyRetrievalRunModel.claim_token == UUID(claim_token),
                )
                .with_for_update()
            )
            if run is None:
                return False
            run.status = "FAILED"
            run.completed_at = now
            run.failure_code = code[:128]
            run.failure_message = message[:1000]
            run.claim_token = None
            run.lease_expires_at = None
            mark_event_consumed(event, now=now)
            return True

    def record_consumer_failure(
        self,
        *,
        event_id: str,
        code: str,
        message: str,
    ) -> None:
        try:
            event_uuid = UUID(event_id)
        except ValueError:
            return
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            event = session.scalar(
                select(PolicyRetrievalOutboxEventModel)
                .where(PolicyRetrievalOutboxEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None:
                return
            run = session.scalar(
                select(PolicyRetrievalRunModel)
                .where(
                    PolicyRetrievalRunModel.tenant_id == event.tenant_id,
                    PolicyRetrievalRunModel.id == event.retrieval_run_id,
                )
                .with_for_update()
            )
            if event.status == "CONSUMED":
                return
            if event.status == "FAILED":
                if event.failure_code == "POLICY_RETRIEVAL_OUTBOX_FAILED":
                    record_rejected_dispatch_recovery(event, message=message)
                return
            if run is not None and not consumer_failure_may_terminalize_run(
                status=run.status,
                lease_expires_at=run.lease_expires_at,
                now=now,
            ):
                if run.status == "RUNNING":
                    event.consumer_last_error = (
                        "Ignored stale terminal failure while a newer execution lease is active."
                    )
                return
            if run is not None:
                run.status = "FAILED"
                run.started_at = run.started_at or now
                run.completed_at = now
                run.failure_code = code[:128]
                run.failure_message = message[:1000]
                run.claim_token = None
                run.lease_expires_at = None
            mark_event_failed(event, now=now, code=code, message=message)


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


def _persist_query_plan(
    session: Session,
    *,
    tenant_id: UUID,
    run_id: UUID,
    plan: PolicyQueryPlan,
    raw_query_hash: str | None,
    now: datetime,
) -> None:
    for position, query in enumerate(plan.queries, start=1):
        raw = raw_query_hash is not None and position == 1
        session.add(
            PolicyRetrievalRunQueryModel(
                id=uuid4(),
                tenant_id=tenant_id,
                retrieval_run_id=run_id,
                query_id=query.query_id,
                purpose=query.purpose.value,
                query_text=None if raw else query.text,
                query_source="CASE_CUSTOMER_MESSAGE" if raw else "GENERATED",
                query_hash=(
                    raw_query_hash if raw else hashlib.sha256(query.text.encode()).hexdigest()
                ),
                position=position,
                filter_hints=plan.filter_hints.model_dump(mode="json"),
                created_at=now,
            )
        )


def _persist_search_results(
    session: Session,
    *,
    tenant_id: UUID,
    run_id: UUID,
    hits: tuple[MultiQueryHit, ...],
    diagnostics: tuple[PolicySimilarityDiagnostic, ...],
    now: datetime,
) -> None:
    for hit in hits:
        session.add(
            PolicyRetrievalRunHitModel(
                id=uuid4(),
                tenant_id=tenant_id,
                retrieval_run_id=run_id,
                rank=hit.rank,
                policy_clause_row_id=UUID(hit.hit.clause.row_id),
                fusion_score=hit.fusion_score,
                best_query_rank=hit.best_query_rank,
                matched_query_ids=list(hit.matched_query_ids),
                per_query_ranks=[value.model_dump(mode="json") for value in hit.per_query_ranks],
                created_at=now,
            )
        )
    for diagnostic in diagnostics:
        session.add(
            PolicyRetrievalSimilarityModel(
                id=uuid4(),
                tenant_id=tenant_id,
                retrieval_run_id=run_id,
                policy_clause_row_id=UUID(diagnostic.hit.clause.row_id),
                similarity_group=diagnostic.group.value,
                rank=diagnostic.rank,
                cosine_similarity=diagnostic.cosine_similarity,
                reference_threshold=diagnostic.reference_threshold,
                threshold_version=diagnostic.threshold_version,
                matched_query_ids=list(diagnostic.matched_query_ids),
                reason_codes=list(diagnostic.reason_codes),
                created_at=now,
            )
        )


def _to_run(row: PolicyRetrievalRunModel) -> PolicyRetrievalRun:
    return PolicyRetrievalRun(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        case_id=str(row.case_id),
        analysis_run_id=str(row.analysis_run_id),
        text_result_id=str(row.text_result_id),
        strategy=QueryStrategy(row.strategy),
        execution_mode=AnalysisExecutionMode(row.execution_mode),
        model_route_plan_id=(
            str(row.model_route_plan_id) if row.model_route_plan_id is not None else None
        ),
        route_enforcement_contract_version=row.route_enforcement_contract_version,
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
