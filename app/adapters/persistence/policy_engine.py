"""SQLAlchemy adapter for immutable policy rules and append-only evaluations."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
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
    AnalysisStageRunModel,
    CaseEvidenceModel,
    CaseModel,
    HumanReviewRequestEventModel,
    LLMExtractionResultV2Model,
    PolicyClauseModel,
    PolicyConditionEvaluationResultModel,
    PolicyEvaluationEffectModel,
    PolicyEvaluationInputSnapshotModel,
    PolicyEvaluationOutboxEventModel,
    PolicyEvaluationRunModel,
    PolicyRuleEvaluationResultModel,
    PolicyRuleModel,
    PolicyRuleSetActivationModel,
    PolicyRuleSetModel,
    PolicyRuleSourceClauseModel,
    TenantModel,
    UserModel,
)
from app.platform.analysis import (
    AnalysisExecutionMode,
    ShadowAnalysisDownstreamForbiddenError,
)
from app.platform.async_reliability import (
    AsyncEventIntegrityError,
    ExecutionAttemptsExhaustedError,
    ExecutionLeaseActiveError,
)
from app.platform.errors import CaseNotFoundError, IdempotencyKeyReusedError, ValidationError
from app.platform.policy_engine import (
    ConditionEvaluation,
    ConditionStatus,
    EvaluationSummary,
    PolicyEffect,
    PolicyEffectType,
    PolicyEvaluation,
    PolicyEvaluationInput,
    PolicyEvaluationRun,
    PolicyEvaluationRunStatus,
    PolicyRule,
    PolicyRuleSet,
    PolicySourceReference,
    RuleEvaluation,
    RuleStatus,
    SourceQualification,
    canonical_hash,
)
from app.ports.policy_engine import PolicyEvaluationExecutionSource, PolicyEvaluationRunDetail


def _source_reference_key(source: PolicySourceReference) -> tuple[str, str, str, str]:
    return (
        source.clause_id,
        source.document_id,
        source.document_version,
        source.source_hash,
    )


def _require_canonical_rule_set_order(value: PolicyRuleSet) -> None:
    rule_keys = tuple((item.rule_id, item.rule_version) for item in value.rules)
    if rule_keys != tuple(sorted(rule_keys)):
        raise ValidationError("Policy rules must use canonical identity order.")
    for rule in value.rules:
        source_keys = tuple(_source_reference_key(item) for item in rule.source_references)
        if len(source_keys) != len(set(source_keys)) or source_keys != tuple(sorted(source_keys)):
            raise ValidationError("Policy rule sources must use unique canonical order.")


class SQLAlchemyPolicyEngineRepository:
    def get_analysis_execution_mode(
        self, *, tenant_id: str, case_id: str, analysis_run_id: str
    ) -> AnalysisExecutionMode | None:
        with self._factory() as session:
            value = session.scalar(
                select(AnalysisRunModel.execution_mode).where(
                    AnalysisRunModel.tenant_id == UUID(tenant_id),
                    AnalysisRunModel.case_id == UUID(case_id),
                    AnalysisRunModel.id == UUID(analysis_run_id),
                )
            )
        return AnalysisExecutionMode(value) if value is not None else None

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        lease_ttl: timedelta = timedelta(minutes=5),
        max_execution_attempts: int = 4,
        shadow_feedback_enabled: bool = False,
    ) -> None:
        self._factory = session_factory
        self._shadow_feedback_enabled = shadow_feedback_enabled
        if lease_ttl.total_seconds() <= 0:
            raise ValueError("lease_ttl must be positive")
        self._lease_ttl = lease_ttl
        if max_execution_attempts <= 0:
            raise ValueError("max_execution_attempts must be positive")
        self._max_execution_attempts = max_execution_attempts

    def ingest(self, rule_sets: tuple[PolicyRuleSet, ...]) -> tuple[int, int]:
        for value in rule_sets:
            _require_canonical_rule_set_order(value)
        inserted_sets = inserted_rules = 0
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            for value in rule_sets:
                tenant = session.scalar(
                    select(TenantModel).where(TenantModel.slug == value.tenant_slug)
                )
                if tenant is None:
                    raise ValidationError(f"Unknown policy tenant: {value.tenant_slug}")
                existing = session.scalar(
                    select(PolicyRuleSetModel).where(
                        PolicyRuleSetModel.tenant_id == tenant.id,
                        PolicyRuleSetModel.rule_set_name == value.rule_set_name,
                        PolicyRuleSetModel.rule_set_version == value.rule_set_version,
                    )
                )
                if existing is not None:
                    if existing.content_hash != value.content_hash:
                        raise ValidationError("Policy rule-set version content mismatch.")
                    continue
                row = PolicyRuleSetModel(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    rule_set_name=value.rule_set_name,
                    rule_set_version=value.rule_set_version,
                    effective_from=value.effective_from,
                    effective_to=value.effective_to,
                    source_corpus_name=value.source_corpus_name,
                    source_corpus_version=value.source_corpus_version,
                    source_corpus_hash=value.source_corpus_hash,
                    source_type=value.source_type,
                    rule_schema_version=value.rule_schema_version,
                    field_registry_version=value.field_registry_version,
                    operator_registry_version=value.operator_registry_version,
                    aggregation_version=value.aggregation_version,
                    content_hash=value.content_hash,
                    created_at=now,
                )
                session.add(row)
                session.flush()
                for rule in value.rules:
                    rule_row = PolicyRuleModel(
                        id=uuid4(),
                        tenant_id=tenant.id,
                        rule_set_id=row.id,
                        rule_id=rule.rule_id,
                        rule_version=rule.rule_version,
                        category=rule.category.value,
                        priority=rule.priority,
                        conditions=[item.model_dump(mode="json") for item in rule.conditions],
                        effects=[item.model_dump(mode="json") for item in rule.effects],
                        requires_human_review=rule.requires_human_review,
                        prohibit_final_decision=rule.prohibit_final_decision,
                        content_hash=rule.content_hash,
                        created_at=now,
                    )
                    session.add(rule_row)
                    session.flush()
                    for source in rule.source_references:
                        effective_end_condition = (
                            PolicyClauseModel.effective_to.is_(None)
                            if value.effective_to is None
                            else (
                                PolicyClauseModel.effective_to.is_(None)
                                | (PolicyClauseModel.effective_to >= value.effective_to)
                            )
                        )
                        clause = session.scalar(
                            select(PolicyClauseModel).where(
                                PolicyClauseModel.tenant_id == tenant.id,
                                PolicyClauseModel.clause_id == source.clause_id,
                                PolicyClauseModel.document_id == source.document_id,
                                PolicyClauseModel.document_version == source.document_version,
                                PolicyClauseModel.source_hash == source.source_hash,
                                PolicyClauseModel.document_status == "ACTIVE",
                                PolicyClauseModel.effective_from <= value.effective_from,
                                effective_end_condition,
                            )
                        )
                        if clause is None:
                            raise ValidationError("Policy rule source clause mismatch.")
                        session.add(
                            PolicyRuleSourceClauseModel(
                                id=uuid4(),
                                tenant_id=tenant.id,
                                policy_rule_id=rule_row.id,
                                policy_clause_row_id=clause.id,
                                document_id=source.document_id,
                                document_version=source.document_version,
                                clause_id=source.clause_id,
                                source_hash=source.source_hash,
                                created_at=now,
                            )
                        )
                    inserted_rules += 1
                actor = session.scalar(
                    select(UserModel).where(
                        UserModel.tenant_id == tenant.id, UserModel.is_active.is_(True)
                    )
                )
                if actor is None:
                    raise ValidationError("Policy rule activation requires an active tenant user.")
                session.execute(
                    update(PolicyRuleSetActivationModel)
                    .where(
                        PolicyRuleSetActivationModel.tenant_id == tenant.id,
                        PolicyRuleSetActivationModel.rule_set_name == value.rule_set_name,
                        PolicyRuleSetActivationModel.retired_at.is_(None),
                    )
                    .values(retired_at=now)
                )
                session.add(
                    PolicyRuleSetActivationModel(
                        id=uuid4(),
                        tenant_id=tenant.id,
                        rule_set_id=row.id,
                        rule_set_name=value.rule_set_name,
                        activated_at=now,
                        retired_at=None,
                        activation_reason="synthetic_rule_set_ingestion",
                        created_by=actor.id,
                        created_at=now,
                    )
                )
                inserted_sets += 1
        return inserted_sets, inserted_rules

    def create(
        self,
        *,
        tenant_id: str,
        case_id: str,
        analysis_run_id: str,
        as_of_date: date,
        requested_by: str,
        correlation_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[PolicyEvaluationRun, bool]:
        tenant_uuid, case_uuid, analysis_uuid = map(UUID, (tenant_id, case_id, analysis_run_id))
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            existing = session.scalar(
                select(PolicyEvaluationRunModel).where(
                    PolicyEvaluationRunModel.tenant_id == tenant_uuid,
                    PolicyEvaluationRunModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise IdempotencyKeyReusedError()
                return _to_run(session, existing), True
            case = session.scalar(
                select(CaseModel).where(
                    CaseModel.tenant_id == tenant_uuid, CaseModel.id == case_uuid
                )
            )
            analysis = session.scalar(
                select(AnalysisRunModel).where(
                    AnalysisRunModel.tenant_id == tenant_uuid,
                    AnalysisRunModel.case_id == case_uuid,
                    AnalysisRunModel.id == analysis_uuid,
                    AnalysisRunModel.status == "SUCCEEDED",
                )
            )
            if (
                analysis is not None
                and analysis.execution_mode == AnalysisExecutionMode.SHADOW.value
                and not self._shadow_feedback_enabled
            ):
                raise ShadowAnalysisDownstreamForbiddenError()
            extraction = session.scalar(
                select(LLMExtractionResultV2Model).where(
                    LLMExtractionResultV2Model.tenant_id == tenant_uuid,
                    LLMExtractionResultV2Model.analysis_run_id == analysis_uuid,
                )
            )
            if case is None or analysis is None or extraction is None:
                raise CaseNotFoundError(
                    "A successful matching Extraction v2 analysis was not found."
                )
            rule_set_row = session.scalar(
                select(PolicyRuleSetModel)
                .join(
                    PolicyRuleSetActivationModel,
                    PolicyRuleSetActivationModel.rule_set_id == PolicyRuleSetModel.id,
                )
                .where(
                    PolicyRuleSetModel.tenant_id == tenant_uuid,
                    PolicyRuleSetActivationModel.retired_at.is_(None),
                    PolicyRuleSetModel.effective_from <= as_of_date,
                    (
                        PolicyRuleSetModel.effective_to.is_(None)
                        | (PolicyRuleSetModel.effective_to >= as_of_date)
                    ),
                )
            )
            if rule_set_row is None:
                raise ValidationError("No active policy rule set is valid for as_of_date.")
            stage = session.get(AnalysisStageRunModel, extraction.stage_run_id)
            provider = stage.execution_provider_name if stage is not None else None
            llm_scope = (
                {
                    "mlx": "LOCAL_POC",
                    "llama_cpp": "LOCAL_POC",
                    "vllm": "PRODUCTION_QUALIFIED",
                    "mock": "MOCK_QUALIFIED",
                }.get(provider, "NOT_AVAILABLE")
                if provider is not None
                else "NOT_AVAILABLE"
            )
            image_count = (
                session.scalar(
                    select(func.count(CaseEvidenceModel.id)).where(
                        CaseEvidenceModel.tenant_id == tenant_uuid,
                        CaseEvidenceModel.case_id == case_uuid,
                        CaseEvidenceModel.evidence_type == "IMAGE",
                        CaseEvidenceModel.upload_status == "AVAILABLE",
                    )
                )
                or 0
            )
            attrs = case.attributes
            values: dict[str, object] = {
                "case.declared_requested_action": case.requested_action,
                "case.has_order_reference": bool(case.order_ref),
                "case.has_product_reference": bool(case.product_ref),
                "evidence.available_image_count": int(image_count),
                "completeness.system_missing_information": extraction.system_missing_information,
                "extraction.issue_types": extraction.issue_types,
                "extraction.claim_count": len(extraction.claims),
                "vision.qualification_status": "MOCK_QUALIFIED",
            }
            for key in ("days_since_purchase", "order_amount", "product_category"):
                if key in attrs:
                    values[f"case.{key}"] = attrs[key]
            qualifications = {
                "llm": llm_scope,
                "vision": "MOCK_QUALIFIED",
                "alignment": "NOT_AVAILABLE",
            }
            if analysis.execution_mode == AnalysisExecutionMode.SHADOW.value:
                qualifications["llm"] = "LOCAL_POC" if provider != "mock" else "MOCK_QUALIFIED"
                qualifications["analysis_execution_mode"] = "SHADOW"
                qualifications["usage_scope"] = "INTERNAL_HUMAN_FEEDBACK"
            snapshot_hash = canonical_hash({"values": values, "qualifications": qualifications})
            run = PolicyEvaluationRunModel(
                id=uuid4(),
                tenant_id=tenant_uuid,
                case_id=case_uuid,
                analysis_run_id=analysis_uuid,
                shadow_feedback_allowed=(
                    analysis.execution_mode == AnalysisExecutionMode.SHADOW.value
                    and self._shadow_feedback_enabled
                ),
                rule_set_id=rule_set_row.id,
                rule_set_version=rule_set_row.rule_set_version,
                rule_set_hash=rule_set_row.content_hash,
                as_of_date=as_of_date,
                status="QUEUED",
                summary_status=None,
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
            session.add(run)
            session.flush()
            session.add(
                PolicyEvaluationInputSnapshotModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    policy_evaluation_run_id=run.id,
                    llm_extraction_result_v2_id=extraction.id,
                    vision_analysis_run_id=None,
                    alignment_result_id=None,
                    input_values=values,
                    source_qualification_metadata=qualifications,
                    snapshot_hash=snapshot_hash,
                    created_at=now,
                )
            )
            session.add(
                PolicyEvaluationOutboxEventModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    policy_evaluation_run_id=run.id,
                    correlation_id=correlation_id,
                    status="PENDING",
                    attempt_count=0,
                    available_at=now,
                    created_at=now,
                )
            )
            session.flush()
            return _to_run(session, run), False

    def list(self, *, tenant_id: str, case_id: str) -> tuple[PolicyEvaluationRun, ...]:
        with self._factory() as session:
            rows = session.scalars(
                select(PolicyEvaluationRunModel)
                .where(
                    PolicyEvaluationRunModel.tenant_id == UUID(tenant_id),
                    PolicyEvaluationRunModel.case_id == UUID(case_id),
                )
                .order_by(PolicyEvaluationRunModel.created_at.desc(), PolicyEvaluationRunModel.id)
            ).all()
            return tuple(_to_run(session, row) for row in rows)

    def get(self, *, tenant_id: str, case_id: str, run_id: str) -> PolicyEvaluationRunDetail | None:
        with self._factory() as session:
            row = session.scalar(
                select(PolicyEvaluationRunModel).where(
                    PolicyEvaluationRunModel.tenant_id == UUID(tenant_id),
                    PolicyEvaluationRunModel.case_id == UUID(case_id),
                    PolicyEvaluationRunModel.id == UUID(run_id),
                )
            )
            if row is None:
                return None
            snapshot = session.scalar(
                select(PolicyEvaluationInputSnapshotModel).where(
                    PolicyEvaluationInputSnapshotModel.tenant_id == row.tenant_id,
                    PolicyEvaluationInputSnapshotModel.policy_evaluation_run_id == row.id,
                )
            )
            assert snapshot is not None
            return PolicyEvaluationRunDetail(
                run=_to_run(session, row),
                input_qualification={
                    str(k): str(v) for k, v in snapshot.source_qualification_metadata.items()
                },
                evaluation=_load_evaluation(session, row) if row.status == "SUCCEEDED" else None,
            )

    def claim(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        run_id: str,
        correlation_id: str,
    ) -> PolicyEvaluationExecutionSource | None:
        event_uuid, tenant_uuid, case_uuid, run_uuid = map(
            UUID, (event_id, tenant_id, case_id, run_id)
        )
        now = datetime.now(UTC)
        claim_token = uuid4()
        deferred_error: RuntimeError | None = None
        source: PolicyEvaluationExecutionSource | None = None
        with self._factory.begin() as session:
            event = session.scalar(
                select(PolicyEvaluationOutboxEventModel)
                .where(PolicyEvaluationOutboxEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None:
                raise AsyncEventIntegrityError(
                    code="POLICY_EVALUATION_EVENT_NOT_FOUND",
                    message="The policy evaluation request event was not found.",
                )
            dispatch_failure = (
                event.status == "FAILED" and event.failure_code == "POLICY_EVALUATION_OUTBOX_FAILED"
            )
            integrity_error = validate_request_event(
                event,
                tenant_id=tenant_uuid,
                case_id=case_uuid,
                correlation_id=correlation_id,
                run_id=run_uuid,
                run_attribute="policy_evaluation_run_id",
            )
            if (
                dispatch_failure
                and integrity_error is not None
                and integrity_error.code == "ASYNC_EVENT_STATE_INVALID"
            ):
                recover_dispatch_failure(
                    event,
                    now=now,
                    dispatch_failure_code="POLICY_EVALUATION_OUTBOX_FAILED",
                )
                integrity_error = validate_request_event(
                    event,
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    correlation_id=correlation_id,
                    run_id=run_uuid,
                    run_attribute="policy_evaluation_run_id",
                )
            if event.status == "CONSUMED" or (event.status == "FAILED" and not dispatch_failure):
                return None
            begin_consumer_attempt(event)
            if integrity_error is not None:
                actual_run = session.scalar(
                    select(PolicyEvaluationRunModel)
                    .where(
                        PolicyEvaluationRunModel.tenant_id == event.tenant_id,
                        PolicyEvaluationRunModel.id == event.policy_evaluation_run_id,
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
                    actual_run.failure_code = "POLICY_EVALUATION_EVENT_INTEGRITY_FAILED"
                    actual_run.failure_message = "Policy evaluation event integrity failed."
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
                    select(PolicyEvaluationRunModel)
                    .where(
                        PolicyEvaluationRunModel.tenant_id == tenant_uuid,
                        PolicyEvaluationRunModel.id == run_uuid,
                    )
                    .with_for_update()
                )
                if row is None or row.case_id != case_uuid:
                    error = AsyncEventIntegrityError(
                        code="POLICY_EVALUATION_RUN_MISMATCH",
                        message="The policy evaluation run does not match the request event.",
                    )
                    mark_event_failed(event, now=now, code=error.code, message=str(error))
                    deferred_error = error
                elif row.status in {"SUCCEEDED", "FAILED"}:
                    mark_event_consumed(event, now=now)
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
                    row.failure_code = "POLICY_EVALUATION_WORKER_ATTEMPTS_EXHAUSTED"
                    row.failure_message = "Policy evaluation worker recovery attempts exhausted."
                    row.claim_token = None
                    row.lease_expires_at = None
                    mark_event_failed(
                        event,
                        now=now,
                        code="POLICY_EVALUATION_WORKER_ATTEMPTS_EXHAUSTED",
                        message="Policy evaluation worker recovery attempts exhausted.",
                    )
                    deferred_error = ExecutionAttemptsExhaustedError(
                        code="POLICY_EVALUATION_WORKER_ATTEMPTS_EXHAUSTED"
                    )
                else:
                    snapshot = session.scalar(
                        select(PolicyEvaluationInputSnapshotModel).where(
                            PolicyEvaluationInputSnapshotModel.tenant_id == tenant_uuid,
                            PolicyEvaluationInputSnapshotModel.policy_evaluation_run_id == run_uuid,
                        )
                    )
                    if snapshot is None or (
                        canonical_hash(
                            {
                                "values": snapshot.input_values,
                                "qualifications": snapshot.source_qualification_metadata,
                            }
                        )
                        != snapshot.snapshot_hash
                    ):
                        row.status = "FAILED"
                        row.started_at = row.started_at or now
                        row.completed_at = now
                        row.failure_code = "POLICY_EVALUATION_SOURCE_INTEGRITY_FAILED"
                        row.failure_message = "Policy evaluation source integrity failed."
                        row.claim_token = None
                        row.lease_expires_at = None
                        mark_event_failed(
                            event,
                            now=now,
                            code="POLICY_EVALUATION_SOURCE_INTEGRITY_FAILED",
                            message="Policy evaluation source integrity failed.",
                        )
                        deferred_error = AsyncEventIntegrityError(
                            code="POLICY_EVALUATION_SOURCE_INTEGRITY_FAILED",
                            message="Policy evaluation source integrity failed.",
                        )
                    else:
                        rule_set = _load_rule_set(session, row.rule_set_id)
                        if rule_set.content_hash != row.rule_set_hash:
                            row.status = "FAILED"
                            row.started_at = row.started_at or now
                            row.completed_at = now
                            row.failure_code = "POLICY_EVALUATION_RULE_SET_HASH_MISMATCH"
                            row.failure_message = "Policy rule-set hash mismatch."
                            row.claim_token = None
                            row.lease_expires_at = None
                            mark_event_failed(
                                event,
                                now=now,
                                code="POLICY_EVALUATION_RULE_SET_HASH_MISMATCH",
                                message="Policy rule-set hash mismatch.",
                            )
                            deferred_error = AsyncEventIntegrityError(
                                code="POLICY_EVALUATION_RULE_SET_HASH_MISMATCH",
                                message="Policy rule-set hash mismatch.",
                            )
                        else:
                            row.status = "RUNNING"
                            row.started_at = row.started_at or now
                            row.claim_token = claim_token
                            row.lease_expires_at = now + self._lease_ttl
                            row.execution_attempt_count += 1
                            qualifications = snapshot.source_qualification_metadata
                            source = PolicyEvaluationExecutionSource(
                                run=_to_run(session, row),
                                claim_token=str(claim_token),
                                rule_set=rule_set,
                                input_snapshot=PolicyEvaluationInput(
                                    values=snapshot.input_values,
                                    llm_qualification=SourceQualification(
                                        str(qualifications["llm"])
                                    ),
                                    vision_qualification=SourceQualification(
                                        str(qualifications["vision"])
                                    ),
                                    alignment_qualification=SourceQualification(
                                        str(qualifications["alignment"])
                                    ),
                                ),
                            )
        if deferred_error is not None:
            raise deferred_error
        return source

    def succeed(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_id: str,
        claim_token: str,
        result: PolicyEvaluation,
    ) -> bool:
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            event = session.scalar(
                select(PolicyEvaluationOutboxEventModel)
                .where(
                    PolicyEvaluationOutboxEventModel.tenant_id == UUID(tenant_id),
                    PolicyEvaluationOutboxEventModel.id == UUID(event_id),
                    PolicyEvaluationOutboxEventModel.policy_evaluation_run_id == UUID(run_id),
                )
                .with_for_update()
            )
            if event is None or not event_allows_completion(
                event,
                dispatch_failure_code="POLICY_EVALUATION_OUTBOX_FAILED",
            ):
                return False
            run = session.scalar(
                select(PolicyEvaluationRunModel)
                .where(
                    PolicyEvaluationRunModel.tenant_id == UUID(tenant_id),
                    PolicyEvaluationRunModel.id == UUID(run_id),
                    PolicyEvaluationRunModel.status == "RUNNING",
                    PolicyEvaluationRunModel.claim_token == UUID(claim_token),
                )
                .with_for_update()
            )
            if run is None:
                return False
            rules = {
                row.rule_id: row
                for row in session.scalars(
                    select(PolicyRuleModel).where(
                        PolicyRuleModel.tenant_id == run.tenant_id,
                        PolicyRuleModel.rule_set_id == run.rule_set_id,
                    )
                ).all()
            }
            for item in result.rule_results:
                rule_row = rules[item.rule_id]
                result_row = PolicyRuleEvaluationResultModel(
                    id=uuid4(),
                    tenant_id=run.tenant_id,
                    policy_evaluation_run_id=run.id,
                    policy_rule_id=rule_row.id,
                    rule_id=item.rule_id,
                    rule_version=item.rule_version,
                    rule_status=item.status.value,
                    source_clause_ids=list(item.source_clause_ids),
                    created_at=now,
                )
                session.add(result_row)
                session.flush()
                for condition in item.condition_results:
                    session.add(
                        PolicyConditionEvaluationResultModel(
                            id=uuid4(),
                            tenant_id=run.tenant_id,
                            policy_rule_evaluation_result_id=result_row.id,
                            condition_index=condition.condition_index,
                            condition_status=condition.status.value,
                            actual_value=condition.actual_value,
                            reason_code=condition.reason_code,
                            created_at=now,
                        )
                    )
                for effect in item.effects:
                    session.add(
                        PolicyEvaluationEffectModel(
                            id=uuid4(),
                            tenant_id=run.tenant_id,
                            policy_rule_evaluation_result_id=result_row.id,
                            effect_type=effect.type.value,
                            effect_value=effect.value,
                            created_at=now,
                        )
                    )
            run.status = "SUCCEEDED"
            run.summary_status = result.summary_status.value
            run.completed_at = now
            run.claim_token = None
            run.lease_expires_at = None
            mark_event_consumed(event, now=now)
            review_effects = {
                PolicyEffectType.REQUIRE_HUMAN_REVIEW,
                PolicyEffectType.REQUIRE_ADDITIONAL_EVIDENCE,
                PolicyEffectType.REQUIRE_MANAGER_REVIEW,
                PolicyEffectType.FLAG_POLICY_EXCEPTION,
                PolicyEffectType.PROHIBIT_AUTOMATION,
            }
            if any(
                effect.type in review_effects
                for item in result.rule_results
                for effect in item.effects
            ):
                session.add(
                    HumanReviewRequestEventModel(
                        id=uuid4(),
                        tenant_id=run.tenant_id,
                        case_id=run.case_id,
                        policy_evaluation_run_id=run.id,
                        correlation_id=run.correlation_id,
                        status="PENDING",
                        attempt_count=0,
                        available_at=now,
                        created_at=now,
                    )
                )
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
                select(PolicyEvaluationOutboxEventModel)
                .where(
                    PolicyEvaluationOutboxEventModel.tenant_id == UUID(tenant_id),
                    PolicyEvaluationOutboxEventModel.id == UUID(event_id),
                    PolicyEvaluationOutboxEventModel.policy_evaluation_run_id == UUID(run_id),
                )
                .with_for_update()
            )
            if event is None or not event_allows_completion(
                event,
                dispatch_failure_code="POLICY_EVALUATION_OUTBOX_FAILED",
            ):
                return False
            run = session.scalar(
                select(PolicyEvaluationRunModel)
                .where(
                    PolicyEvaluationRunModel.tenant_id == UUID(tenant_id),
                    PolicyEvaluationRunModel.id == UUID(run_id),
                    PolicyEvaluationRunModel.status == "RUNNING",
                    PolicyEvaluationRunModel.claim_token == UUID(claim_token),
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
                select(PolicyEvaluationOutboxEventModel)
                .where(PolicyEvaluationOutboxEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None:
                return
            run = session.scalar(
                select(PolicyEvaluationRunModel)
                .where(
                    PolicyEvaluationRunModel.tenant_id == event.tenant_id,
                    PolicyEvaluationRunModel.id == event.policy_evaluation_run_id,
                )
                .with_for_update()
            )
            if event.status == "CONSUMED":
                return
            if event.status == "FAILED":
                if event.failure_code == "POLICY_EVALUATION_OUTBOX_FAILED":
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


def _reconstruct_rule_set(
    *,
    tenant_slug: str,
    row: PolicyRuleSetModel,
    rule_rows: tuple[PolicyRuleModel, ...],
    source_rows: tuple[PolicyRuleSourceClauseModel, ...],
) -> PolicyRuleSet:
    """Rebuild the immutable hash payload under the persistence ordering contract."""

    source_rows_by_rule: dict[UUID, list[PolicyRuleSourceClauseModel]] = {}
    for source in source_rows:
        source_rows_by_rule.setdefault(source.policy_rule_id, []).append(source)
    rules: list[PolicyRule] = []
    for rule in sorted(rule_rows, key=lambda item: (item.rule_id, item.rule_version)):
        sources = sorted(
            source_rows_by_rule.get(rule.id, []),
            key=lambda item: (
                item.clause_id,
                item.document_id,
                item.document_version,
                item.source_hash,
            ),
        )
        rules.append(
            PolicyRule.model_validate(
                {
                    "rule_id": rule.rule_id,
                    "rule_version": rule.rule_version,
                    "category": rule.category,
                    "priority": rule.priority,
                    "conditions": rule.conditions,
                    "effects": rule.effects,
                    "requires_human_review": rule.requires_human_review,
                    "prohibit_final_decision": rule.prohibit_final_decision,
                    "source_references": [
                        {
                            "clause_id": item.clause_id,
                            "document_id": item.document_id,
                            "document_version": item.document_version,
                            "source_hash": item.source_hash,
                        }
                        for item in sources
                    ],
                }
            )
        )
    result = PolicyRuleSet.model_validate(
        {
            "tenant_slug": tenant_slug,
            "rule_set_name": row.rule_set_name,
            "rule_set_version": row.rule_set_version,
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "source_corpus_name": row.source_corpus_name,
            "source_corpus_version": row.source_corpus_version,
            "source_corpus_hash": row.source_corpus_hash,
            "source_type": row.source_type,
            "rule_schema_version": row.rule_schema_version,
            "field_registry_version": row.field_registry_version,
            "operator_registry_version": row.operator_registry_version,
            "aggregation_version": row.aggregation_version,
            "rules": rules,
        }
    )
    if result.content_hash != row.content_hash:
        raise ValidationError("Immutable policy rule-set hash mismatch.")
    return result


def _load_rule_set(session: Session, rule_set_id: UUID) -> PolicyRuleSet:
    row = session.get(PolicyRuleSetModel, rule_set_id)
    assert row is not None
    rule_rows = tuple(
        session.scalars(
            select(PolicyRuleModel)
            .where(PolicyRuleModel.rule_set_id == row.id)
            .order_by(PolicyRuleModel.rule_id, PolicyRuleModel.rule_version)
        ).all()
    )
    source_rows: list[PolicyRuleSourceClauseModel] = []
    for rule in rule_rows:
        source_rows.extend(
            session.scalars(
                select(PolicyRuleSourceClauseModel)
                .where(PolicyRuleSourceClauseModel.policy_rule_id == rule.id)
                .order_by(
                    PolicyRuleSourceClauseModel.clause_id,
                    PolicyRuleSourceClauseModel.document_id,
                    PolicyRuleSourceClauseModel.document_version,
                    PolicyRuleSourceClauseModel.source_hash,
                )
            ).all()
        )
    tenant = session.get(TenantModel, row.tenant_id)
    assert tenant is not None
    return _reconstruct_rule_set(
        tenant_slug=tenant.slug,
        row=row,
        rule_rows=rule_rows,
        source_rows=tuple(source_rows),
    )


def _to_run(session: Session, row: PolicyEvaluationRunModel) -> PolicyEvaluationRun:
    rule_set = session.get(PolicyRuleSetModel, row.rule_set_id)
    assert rule_set is not None
    return PolicyEvaluationRun(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        case_id=str(row.case_id),
        analysis_run_id=str(row.analysis_run_id),
        rule_set_id=str(row.rule_set_id),
        rule_set_name=rule_set.rule_set_name,
        rule_set_version=row.rule_set_version,
        rule_set_hash=row.rule_set_hash,
        as_of_date=row.as_of_date,
        status=PolicyEvaluationRunStatus(row.status),
        summary_status=EvaluationSummary(row.summary_status) if row.summary_status else None,
        correlation_id=row.correlation_id,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        failure_code=row.failure_code,
        failure_message=row.failure_message,
    )


def _load_evaluation(session: Session, run: PolicyEvaluationRunModel) -> PolicyEvaluation:
    items: list[RuleEvaluation] = []
    for row in session.scalars(
        select(PolicyRuleEvaluationResultModel)
        .where(
            PolicyRuleEvaluationResultModel.tenant_id == run.tenant_id,
            PolicyRuleEvaluationResultModel.policy_evaluation_run_id == run.id,
        )
        .order_by(PolicyRuleEvaluationResultModel.rule_id)
    ).all():
        conditions = session.scalars(
            select(PolicyConditionEvaluationResultModel)
            .where(
                PolicyConditionEvaluationResultModel.tenant_id == run.tenant_id,
                PolicyConditionEvaluationResultModel.policy_rule_evaluation_result_id == row.id,
            )
            .order_by(PolicyConditionEvaluationResultModel.condition_index)
        ).all()
        effects = session.scalars(
            select(PolicyEvaluationEffectModel)
            .where(
                PolicyEvaluationEffectModel.tenant_id == run.tenant_id,
                PolicyEvaluationEffectModel.policy_rule_evaluation_result_id == row.id,
            )
            .order_by(PolicyEvaluationEffectModel.id)
        ).all()
        items.append(
            RuleEvaluation(
                rule_id=row.rule_id,
                rule_version=row.rule_version,
                status=RuleStatus(row.rule_status),
                condition_results=tuple(
                    ConditionEvaluation(
                        condition_index=item.condition_index,
                        status=ConditionStatus(item.condition_status),
                        actual_value=item.actual_value,
                        reason_code=item.reason_code,
                    )
                    for item in conditions
                ),
                effects=tuple(
                    PolicyEffect(type=PolicyEffectType(item.effect_type), value=item.effect_value)
                    for item in effects
                ),
                source_clause_ids=tuple(row.source_clause_ids),
            )
        )
    rule_set = session.get(PolicyRuleSetModel, run.rule_set_id)
    assert rule_set is not None and run.summary_status is not None
    return PolicyEvaluation(
        rule_set_name=rule_set.rule_set_name,
        rule_set_version=run.rule_set_version,
        rule_set_hash=run.rule_set_hash,
        summary_status=EvaluationSummary(run.summary_status),
        rule_results=tuple(items),
        evaluated_at=run.completed_at,
    )


__all__ = ["SQLAlchemyPolicyEngineRepository"]
