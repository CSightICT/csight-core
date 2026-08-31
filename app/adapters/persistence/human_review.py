"""SQLAlchemy adapter for immutable packets and human-only review actions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import case as sql_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.async_events import (
    begin_consumer_attempt,
    mark_event_consumed,
    mark_event_failed,
    record_rejected_dispatch_recovery,
    recover_dispatch_failure,
    validate_request_event,
)
from app.adapters.persistence.grounding import load_verified_citation_pack
from app.adapters.persistence.models import (
    AnalysisRunEvidenceModel,
    CaseAssignmentModel,
    CaseEvidenceModel,
    CaseModel,
    CaseResolutionEventModel,
    CaseResolutionModel,
    CaseResolutionRequestEventModel,
    GroundedExplanationResultModel,
    GroundedExplanationRunModel,
    HumanReviewActionModel,
    HumanReviewAssignmentModel,
    HumanReviewDecisionBasisModel,
    HumanReviewDecisionModel,
    HumanReviewPacketModel,
    HumanReviewRequestEventModel,
    HumanReviewTaskModel,
    LLMExtractionResultV2Model,
    PolicyCitationPackItemModel,
    PolicyCitationPackModel,
    PolicyClauseModel,
    PolicyEvaluationEffectModel,
    PolicyEvaluationInputSnapshotModel,
    PolicyEvaluationRunModel,
    PolicyRetrievalRunModel,
    PolicyRetrievalSimilarityModel,
    PolicyRuleEvaluationResultModel,
    PolicyRuleSetModel,
    RoleModel,
    UserModel,
    UserRoleModel,
    VisionAnalysisResultModel,
)
from app.platform.async_reliability import AsyncEventIntegrityError
from app.platform.case_resolution import (
    ACTION_MAPPING_NAME,
    ACTION_MAPPING_VERSION,
    RESOLUTION_SCHEMA_VERSION,
    ResolutionStatus,
)
from app.platform.errors import ForbiddenError
from app.platform.errors import ValidationError as PlatformValidationError
from app.platform.human_review import (
    DECISION_SCHEMA_VERSION,
    OUTCOME_RELATION_RULE_VERSION,
    PACKET_SCHEMA_VERSION,
    TASK_MAPPING_NAME,
    TASK_MAPPING_VERSION,
    AdditionalEvidenceReason,
    AssignmentType,
    DecisionBasisReference,
    DecisionBasisType,
    DuplicateHumanDecisionError,
    EscalationReason,
    HumanDecision,
    HumanDecisionRequest,
    InvalidDecisionBasisError,
    InvalidReviewTransitionError,
    ReviewAction,
    ReviewActionType,
    ReviewAssignee,
    ReviewPacket,
    ReviewPacketIntegrityError,
    ReviewTask,
    ReviewTaskAlreadyClaimedError,
    ReviewTaskNotFoundError,
    ReviewTaskStatus,
    ReviewTaskType,
    ReviewTaskVersionConflictError,
    actor_role,
    can_claim,
    canonical_hash,
    compute_outcome_relation,
    map_policy_effects,
    transition,
)
from app.platform.policy_engine import EvaluationSummary, PolicyEffect
from app.platform.tenant import Role
from app.ports.human_review import ReviewQueueQuery, ReviewTaskDetail


class SQLAlchemyHumanReviewRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def create_from_policy_evaluation(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        policy_evaluation_run_id: str,
        correlation_id: str,
    ) -> tuple[ReviewTask, bool]:
        try:
            result = self._create_from_policy_evaluation_once(
                event_id=event_id,
                tenant_id=tenant_id,
                case_id=case_id,
                policy_evaluation_run_id=policy_evaluation_run_id,
                correlation_id=correlation_id,
            )
        except ReviewPacketIntegrityError as error:
            self.record_consumer_failure(
                event_id=event_id,
                code="HUMAN_REVIEW_SOURCE_INTEGRITY_FAILED",
                message=str(error),
            )
            raise
        if isinstance(result, AsyncEventIntegrityError):
            raise result
        return result

    def _create_from_policy_evaluation_once(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        policy_evaluation_run_id: str,
        correlation_id: str,
    ) -> tuple[ReviewTask, bool] | AsyncEventIntegrityError:
        event_uuid = UUID(event_id)
        tenant_uuid = UUID(tenant_id)
        run_uuid = UUID(policy_evaluation_run_id)
        case_uuid = UUID(case_id)
        with self._factory.begin() as session:
            event = session.scalar(
                select(HumanReviewRequestEventModel)
                .where(HumanReviewRequestEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None:
                return AsyncEventIntegrityError(
                    code="HUMAN_REVIEW_EVENT_NOT_FOUND",
                    message="The human review request event was not found.",
                )
            dispatch_failure = (
                event.status == "FAILED" and event.failure_code == "HUMAN_REVIEW_OUTBOX_FAILED"
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
                    now=datetime.now(UTC),
                    dispatch_failure_code="HUMAN_REVIEW_OUTBOX_FAILED",
                )
                integrity_error = validate_request_event(
                    event,
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    correlation_id=correlation_id,
                    run_id=run_uuid,
                    run_attribute="policy_evaluation_run_id",
                )
            if event.status == "CONSUMED":
                existing = session.scalar(
                    select(HumanReviewTaskModel).where(
                        HumanReviewTaskModel.tenant_id == tenant_uuid,
                        HumanReviewTaskModel.policy_evaluation_run_id == run_uuid,
                    )
                )
                identity_matches = integrity_error is None or (
                    integrity_error.code == "ASYNC_EVENT_STATE_INVALID"
                )
                if identity_matches and existing is not None:
                    return _to_task(existing), True
                return integrity_error or AsyncEventIntegrityError(
                    code="HUMAN_REVIEW_EVENT_CONSUMED_WITHOUT_TASK",
                    message="The consumed human review event has no matching task.",
                )
            if event.status == "FAILED" and not dispatch_failure:
                return integrity_error or AsyncEventIntegrityError(
                    code=event.failure_code or "HUMAN_REVIEW_EVENT_FAILED",
                    message="The human review request event has already failed.",
                )
            begin_consumer_attempt(event)
            if integrity_error is not None:
                if dispatch_failure:
                    record_rejected_dispatch_recovery(event, message=str(integrity_error))
                else:
                    mark_event_failed(
                        event,
                        now=datetime.now(UTC),
                        code=integrity_error.code,
                        message=str(integrity_error),
                    )
                return integrity_error
            existing = session.scalar(
                select(HumanReviewTaskModel).where(
                    HumanReviewTaskModel.tenant_id == tenant_uuid,
                    HumanReviewTaskModel.policy_evaluation_run_id == run_uuid,
                )
            )
            if existing is not None:
                if event.status in {"PROCESSING", "PUBLISHED"}:
                    mark_event_consumed(event, now=datetime.now(UTC))
                elif event.status != "CONSUMED":
                    raise ReviewPacketIntegrityError(
                        "The human review request event has a terminal failure."
                    )
                return _to_task(existing), True
            if event.status not in {"PROCESSING", "PUBLISHED"}:
                raise ReviewPacketIntegrityError(
                    "The human review request event is not consumable."
                )
            run = session.scalar(
                select(PolicyEvaluationRunModel).where(
                    PolicyEvaluationRunModel.tenant_id == tenant_uuid,
                    PolicyEvaluationRunModel.case_id == case_uuid,
                    PolicyEvaluationRunModel.id == run_uuid,
                    PolicyEvaluationRunModel.status == "SUCCEEDED",
                )
            )
            if run is None or run.summary_status is None:
                raise ReviewPacketIntegrityError("A successful policy evaluation was not found.")
            owned_case = session.scalar(
                select(CaseModel)
                .where(CaseModel.tenant_id == tenant_uuid, CaseModel.id == case_uuid)
                .with_for_update()
            )
            if owned_case is None:
                raise ReviewPacketIntegrityError("The policy evaluation Case was not found.")
            inherited_case_assignment = None
            if owned_case.current_assignee_id is not None:
                inherited_case_assignment = session.scalar(
                    select(CaseAssignmentModel).where(
                        CaseAssignmentModel.tenant_id == tenant_uuid,
                        CaseAssignmentModel.case_id == case_uuid,
                        CaseAssignmentModel.released_at.is_(None),
                    )
                )
                if inherited_case_assignment is None:
                    raise ReviewPacketIntegrityError(
                        "The Case assignment projection has no active assignment record."
                    )
            snapshot = session.scalar(
                select(PolicyEvaluationInputSnapshotModel).where(
                    PolicyEvaluationInputSnapshotModel.tenant_id == tenant_uuid,
                    PolicyEvaluationInputSnapshotModel.policy_evaluation_run_id == run.id,
                )
            )
            rule_set = session.scalar(
                select(PolicyRuleSetModel).where(
                    PolicyRuleSetModel.tenant_id == tenant_uuid,
                    PolicyRuleSetModel.id == run.rule_set_id,
                )
            )
            if (
                snapshot is None
                or canonical_hash(
                    {
                        "values": snapshot.input_values,
                        "qualifications": snapshot.source_qualification_metadata,
                    }
                )
                != snapshot.snapshot_hash
                or rule_set is None
                or rule_set.content_hash != run.rule_set_hash
            ):
                raise ReviewPacketIntegrityError("Policy snapshot or rule-set hash is invalid.")
            extraction = session.scalar(
                select(LLMExtractionResultV2Model).where(
                    LLMExtractionResultV2Model.tenant_id == tenant_uuid,
                    LLMExtractionResultV2Model.id == snapshot.llm_extraction_result_v2_id,
                    LLMExtractionResultV2Model.analysis_run_id == run.analysis_run_id,
                )
            )
            if extraction is None:
                raise ReviewPacketIntegrityError(
                    "The extraction result is outside the policy evaluation analysis run."
                )
            effect_rows = session.scalars(
                select(PolicyEvaluationEffectModel)
                .join(
                    PolicyRuleEvaluationResultModel,
                    PolicyRuleEvaluationResultModel.id
                    == PolicyEvaluationEffectModel.policy_rule_evaluation_result_id,
                )
                .where(
                    PolicyEvaluationEffectModel.tenant_id == tenant_uuid,
                    PolicyRuleEvaluationResultModel.policy_evaluation_run_id == run.id,
                )
                .order_by(PolicyEvaluationEffectModel.effect_type, PolicyEvaluationEffectModel.id)
            ).all()
            effects = tuple(
                PolicyEffect.model_validate({"type": row.effect_type, "value": row.effect_value})
                for row in effect_rows
            )
            task_type, priority = map_policy_effects(effects)
            grounding = session.execute(
                select(GroundedExplanationRunModel, GroundedExplanationResultModel)
                .join(
                    GroundedExplanationResultModel,
                    GroundedExplanationResultModel.grounded_explanation_run_id
                    == GroundedExplanationRunModel.id,
                )
                .join(
                    PolicyRetrievalRunModel,
                    PolicyRetrievalRunModel.id == GroundedExplanationRunModel.retrieval_run_id,
                )
                .where(
                    GroundedExplanationRunModel.tenant_id == tenant_uuid,
                    GroundedExplanationRunModel.case_id == case_uuid,
                    GroundedExplanationRunModel.status == "SUCCEEDED",
                    PolicyRetrievalRunModel.analysis_run_id == run.analysis_run_id,
                )
                .order_by(GroundedExplanationRunModel.completed_at.desc())
                .limit(1)
            ).one_or_none()
            grounded_run = grounding[0] if grounding is not None else None
            grounded_result = grounding[1] if grounding is not None else None
            if grounded_run is not None:
                _verify_citation_pack(
                    session,
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    pack_id=grounded_run.citation_pack_id,
                )
            vision_ids = tuple(
                str(value)
                for value in session.scalars(
                    select(VisionAnalysisResultModel.id)
                    .where(
                        VisionAnalysisResultModel.tenant_id == tenant_uuid,
                        VisionAnalysisResultModel.analysis_run_id == run.analysis_run_id,
                    )
                    .order_by(VisionAnalysisResultModel.id)
                ).all()
            )
            allowed_metadata = {
                key: snapshot.input_values.get(key)
                for key in (
                    "case.days_since_purchase",
                    "case.order_amount",
                    "case.product_category",
                    "case.declared_requested_action",
                    "case.has_order_reference",
                    "case.has_product_reference",
                    "evidence.available_image_count",
                )
            }
            qualifications = {
                source: {
                    "scope": snapshot.source_qualification_metadata.get(source, "NOT_AVAILABLE")
                }
                for source in ("llm", "vision", "alignment")
            }
            qualifications["grounding"] = {
                "scope": (
                    "LOCAL_POC"
                    if grounded_result is not None and grounded_result.provider_name == "mlx"
                    else "NOT_AVAILABLE"
                ),
                "model_family": (
                    grounded_result.model_name if grounded_result is not None else None
                ),
                "model_revision": (
                    grounded_result.model_revision if grounded_result is not None else None
                ),
            }
            now = datetime.now(UTC)
            task_id = uuid4()
            packet_id = uuid4()
            packet_payload = {
                "tenant_id": tenant_id,
                "review_task_id": str(task_id),
                "case_id": case_id,
                "analysis_run_id": str(run.analysis_run_id),
                "policy_evaluation_run_id": policy_evaluation_run_id,
                "rule_set_id": str(run.rule_set_id),
                "rule_set_version": run.rule_set_version,
                "rule_set_hash": run.rule_set_hash,
                "llm_extraction_result_v2_id": str(snapshot.llm_extraction_result_v2_id),
                "completeness_result_id": str(snapshot.llm_extraction_result_v2_id),
                "vision_result_ids": vision_ids,
                "alignment_result_id": (
                    str(snapshot.alignment_result_id) if snapshot.alignment_result_id else None
                ),
                "citation_pack_id": (
                    str(grounded_run.citation_pack_id) if grounded_run is not None else None
                ),
                "grounding_result_id": (
                    str(grounded_result.id) if grounded_result is not None else None
                ),
                "case_metadata_snapshot": allowed_metadata,
                "qualification_snapshot": qualifications,
                "policy_effects": [item.model_dump(mode="json") for item in effects],
                "policy_summary_status": run.summary_status,
                "packet_schema_version": PACKET_SCHEMA_VERSION,
            }
            task = HumanReviewTaskModel(
                id=task_id,
                tenant_id=tenant_uuid,
                case_id=case_uuid,
                policy_evaluation_run_id=run.id,
                task_type=task_type.value,
                priority=priority.value,
                status=(
                    ReviewTaskStatus.CLAIMED.value
                    if owned_case.current_assignee_id is not None
                    else ReviewTaskStatus.PENDING.value
                ),
                current_assignee_id=owned_case.current_assignee_id,
                version=1,
                mapping_rule_name=TASK_MAPPING_NAME,
                mapping_rule_version=TASK_MAPPING_VERSION,
                resolved_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            # The task is the aggregate root for the immutable packet and action log.
            # Flush it first because these models deliberately avoid ORM relationships.
            session.flush()
            session.add(
                HumanReviewPacketModel(
                    id=packet_id,
                    tenant_id=tenant_uuid,
                    review_task_id=task_id,
                    case_id=case_uuid,
                    analysis_run_id=run.analysis_run_id,
                    policy_evaluation_run_id=run.id,
                    rule_set_id=run.rule_set_id,
                    rule_set_version=run.rule_set_version,
                    rule_set_hash=run.rule_set_hash,
                    llm_extraction_result_v2_id=snapshot.llm_extraction_result_v2_id,
                    completeness_result_id=snapshot.llm_extraction_result_v2_id,
                    vision_result_ids=list(vision_ids),
                    alignment_result_id=snapshot.alignment_result_id,
                    citation_pack_id=(grounded_run.citation_pack_id if grounded_run else None),
                    grounding_result_id=(grounded_result.id if grounded_result else None),
                    case_metadata_snapshot=allowed_metadata,
                    qualification_snapshot=qualifications,
                    policy_effects=[item.model_dump(mode="json") for item in effects],
                    policy_summary_status=run.summary_status,
                    packet_schema_version=PACKET_SCHEMA_VERSION,
                    packet_hash=canonical_hash(packet_payload),
                    created_at=now,
                )
            )
            session.add(
                HumanReviewActionModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    review_task_id=task_id,
                    action_type=ReviewActionType.CREATED.value,
                    from_status=None,
                    to_status=task.status,
                    actor_id=None,
                    actor_role=None,
                    reason_codes=[],
                    rationale=None,
                    action_payload={
                        "mapping_version": TASK_MAPPING_VERSION,
                        "case_assignment_version": owned_case.assignment_version,
                        "inherited_case_assignment": owned_case.current_assignee_id is not None,
                    },
                    expected_task_version=0,
                    resulting_task_version=1,
                    created_at=now,
                )
            )
            if inherited_case_assignment is not None:
                session.add(
                    HumanReviewAssignmentModel(
                        id=uuid4(),
                        tenant_id=tenant_uuid,
                        review_task_id=task_id,
                        assignee_id=inherited_case_assignment.assignee_id,
                        assigned_by=inherited_case_assignment.assigned_by,
                        assignment_type=AssignmentType.CASE_ASSIGNMENT_INHERITANCE.value,
                        assigned_at=now,
                        released_at=None,
                        created_at=now,
                    )
                )
            mark_event_consumed(event, now=now)
            session.flush()
            return _to_task(task), False

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
        with self._factory.begin() as session:
            event = session.scalar(
                select(HumanReviewRequestEventModel)
                .where(HumanReviewRequestEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None or event.status == "CONSUMED":
                return
            if event.status == "FAILED":
                if event.failure_code == "HUMAN_REVIEW_OUTBOX_FAILED":
                    record_rejected_dispatch_recovery(event, message=message)
                return
            mark_event_failed(
                event,
                now=datetime.now(UTC),
                code=code,
                message=message,
            )

    def list(
        self, *, tenant_id: str, actor_id: str, query: ReviewQueueQuery
    ) -> tuple[ReviewTask, ...]:
        statement = select(HumanReviewTaskModel).where(
            HumanReviewTaskModel.tenant_id == UUID(tenant_id)
        )
        if query.status is not None:
            statement = statement.where(HumanReviewTaskModel.status == query.status.value)
        if query.task_type is not None:
            statement = statement.where(HumanReviewTaskModel.task_type == query.task_type.value)
        if query.priority is not None:
            statement = statement.where(HumanReviewTaskModel.priority == query.priority.value)
        if query.assigned_to_me:
            statement = statement.where(HumanReviewTaskModel.current_assignee_id == UUID(actor_id))
        if query.unassigned_only:
            statement = statement.where(HumanReviewTaskModel.current_assignee_id.is_(None))
        if query.created_from is not None:
            statement = statement.where(HumanReviewTaskModel.created_at >= query.created_from)
        if query.created_to is not None:
            statement = statement.where(HumanReviewTaskModel.created_at <= query.created_to)
        if query.case_id is not None:
            statement = statement.where(HumanReviewTaskModel.case_id == UUID(query.case_id))
        priority_order = sql_case(
            (HumanReviewTaskModel.priority == "CRITICAL", 4),
            (HumanReviewTaskModel.priority == "HIGH", 3),
            (HumanReviewTaskModel.priority == "NORMAL", 2),
            else_=1,
        )
        statement = (
            statement.order_by(
                priority_order.desc(), HumanReviewTaskModel.created_at, HumanReviewTaskModel.id
            )
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        with self._factory() as session:
            return tuple(_to_task(row) for row in session.scalars(statement).all())

    def get(self, *, tenant_id: str, task_id: str) -> ReviewTaskDetail | None:
        tenant_uuid, task_uuid = UUID(tenant_id), UUID(task_id)
        with self._factory() as session:
            task = session.scalar(
                select(HumanReviewTaskModel).where(
                    HumanReviewTaskModel.tenant_id == tenant_uuid,
                    HumanReviewTaskModel.id == task_uuid,
                )
            )
            if task is None:
                return None
            packet = session.scalar(
                select(HumanReviewPacketModel).where(
                    HumanReviewPacketModel.tenant_id == tenant_uuid,
                    HumanReviewPacketModel.review_task_id == task_uuid,
                )
            )
            assert packet is not None
            _verify_packet_hash(packet)
            if packet.citation_pack_id is not None:
                _verify_citation_pack(
                    session,
                    tenant_id=tenant_uuid,
                    case_id=packet.case_id,
                    pack_id=packet.citation_pack_id,
                )
            actions = session.scalars(
                select(HumanReviewActionModel)
                .where(
                    HumanReviewActionModel.tenant_id == tenant_uuid,
                    HumanReviewActionModel.review_task_id == task_uuid,
                )
                .order_by(HumanReviewActionModel.resulting_task_version)
            ).all()
            decision_row = session.scalar(
                select(HumanReviewDecisionModel).where(
                    HumanReviewDecisionModel.tenant_id == tenant_uuid,
                    HumanReviewDecisionModel.review_task_id == task_uuid,
                )
            )
            basis_rows: list[HumanReviewDecisionBasisModel] = (
                list(
                    session.scalars(
                        select(HumanReviewDecisionBasisModel).where(
                            HumanReviewDecisionBasisModel.tenant_id == tenant_uuid,
                            HumanReviewDecisionBasisModel.human_review_decision_id
                            == decision_row.id,
                        )
                    ).all()
                )
                if decision_row is not None
                else []
            )
            rule_rows = session.scalars(
                select(PolicyRuleEvaluationResultModel)
                .where(
                    PolicyRuleEvaluationResultModel.tenant_id == tenant_uuid,
                    PolicyRuleEvaluationResultModel.policy_evaluation_run_id
                    == packet.policy_evaluation_run_id,
                )
                .order_by(PolicyRuleEvaluationResultModel.rule_id)
            ).all()
            citation_rows = (
                session.scalars(
                    select(PolicyCitationPackItemModel)
                    .where(
                        PolicyCitationPackItemModel.tenant_id == tenant_uuid,
                        PolicyCitationPackItemModel.citation_pack_id == packet.citation_pack_id,
                    )
                    .order_by(PolicyCitationPackItemModel.rank)
                ).all()
                if packet.citation_pack_id is not None
                else []
            )
            grounded = (
                session.get(GroundedExplanationResultModel, packet.grounding_result_id)
                if packet.grounding_result_id is not None
                else None
            )
            extraction = session.get(LLMExtractionResultV2Model, packet.llm_extraction_result_v2_id)
            citation_pack = (
                session.get(PolicyCitationPackModel, packet.citation_pack_id)
                if packet.citation_pack_id is not None
                else None
            )
            similarity_rows = (
                session.execute(
                    select(PolicyRetrievalSimilarityModel, PolicyClauseModel)
                    .join(
                        PolicyClauseModel,
                        PolicyClauseModel.id == PolicyRetrievalSimilarityModel.policy_clause_row_id,
                    )
                    .where(
                        PolicyRetrievalSimilarityModel.tenant_id == tenant_uuid,
                        PolicyRetrievalSimilarityModel.retrieval_run_id
                        == citation_pack.retrieval_run_id,
                    )
                    .order_by(
                        PolicyRetrievalSimilarityModel.similarity_group,
                        PolicyRetrievalSimilarityModel.rank,
                    )
                ).all()
                if citation_pack is not None
                else []
            )
            return ReviewTaskDetail(
                task=_to_task(task),
                packet=_to_packet(packet),
                actions=tuple(_to_action(row) for row in actions),
                decision=(
                    _to_decision(session, decision_row, basis_rows)
                    if decision_row is not None
                    else None
                ),
                rule_results=tuple(
                    {
                        "id": str(row.id),
                        "rule_id": row.rule_id,
                        "rule_version": row.rule_version,
                        "status": row.rule_status,
                        "source_clause_ids": tuple(row.source_clause_ids),
                    }
                    for row in rule_rows
                ),
                citation_items=tuple(
                    {
                        "id": str(row.id),
                        "citation_id": row.citation_id,
                        "rank": row.rank,
                        "policy_clause_id": row.policy_clause_id,
                        "document_id": row.document_id,
                        "document_version": row.document_version,
                        "title": row.title,
                        "text": row.clause_text,
                        "section_path": tuple(row.section_path),
                        "source_type": row.source_type,
                    }
                    for row in citation_rows
                ),
                grounded_explanation=(
                    {
                        "summary": grounded.summary,
                        "policy_statements": grounded.policy_statements,
                        "unresolved_conditions": grounded.unresolved_conditions,
                        "advisory": True,
                    }
                    if grounded is not None
                    else None
                ),
                inquiry_summary=extraction.summary if extraction is not None else None,
                policy_similarity=tuple(
                    {
                        "group": evidence.similarity_group,
                        "rank": evidence.rank,
                        "cosine_similarity": evidence.cosine_similarity,
                        "reference_threshold": evidence.reference_threshold,
                        "threshold_version": evidence.threshold_version,
                        "matched_query_ids": tuple(evidence.matched_query_ids),
                        "reason_codes": tuple(evidence.reason_codes),
                        "policy_clause_id": clause.clause_id,
                        "document_id": clause.document_id,
                        "document_version": clause.document_version,
                        "title": clause.title,
                        "section_path": tuple(clause.section_path),
                        "text": clause.text,
                    }
                    for evidence, clause in similarity_rows
                ),
            )

    def list_assignees(self, *, tenant_id: str) -> tuple[ReviewAssignee, ...]:
        tenant_uuid = UUID(tenant_id)
        with self._factory() as session:
            rows = session.execute(
                select(UserModel, RoleModel.name)
                .join(
                    UserRoleModel,
                    (UserRoleModel.tenant_id == UserModel.tenant_id)
                    & (UserRoleModel.user_id == UserModel.id),
                )
                .join(RoleModel, RoleModel.id == UserRoleModel.role_id)
                .where(
                    UserModel.tenant_id == tenant_uuid,
                    UserModel.is_active.is_(True),
                    RoleModel.name.in_((Role.ADMIN.value, Role.REVIEWER.value)),
                )
                .order_by(UserModel.display_name, UserModel.email, RoleModel.name)
            ).all()
        grouped: dict[UUID, tuple[UserModel, set[Role]]] = {}
        for user, role_name in rows:
            if user.id not in grouped:
                grouped[user.id] = (user, set())
            grouped[user.id][1].add(Role(role_name))
        return tuple(
            ReviewAssignee(
                user_id=str(user.id),
                display_name=user.display_name,
                email=user.email,
                roles=tuple(sorted(roles, key=lambda item: item.value)),
            )
            for user, roles in grouped.values()
        )

    def assign(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        assignee_id: str,
        rationale: str,
    ) -> ReviewTask:
        if Role.ADMIN not in roles:
            raise ForbiddenError()
        tenant_uuid = UUID(tenant_id)
        assignee_uuid = UUID(assignee_id)
        with self._factory.begin() as session:
            task = _lock_task(session, tenant_id, task_id)
            _check_version(task, expected_version)
            status = ReviewTaskStatus(task.status)
            if status not in {
                ReviewTaskStatus.PENDING,
                ReviewTaskStatus.CLAIMED,
                ReviewTaskStatus.ESCALATED,
            }:
                raise InvalidReviewTransitionError()
            if task.current_assignee_id == assignee_uuid:
                raise PlatformValidationError("The review task is already assigned to this user.")

            assignee = session.scalar(
                select(UserModel).where(
                    UserModel.tenant_id == tenant_uuid,
                    UserModel.id == assignee_uuid,
                    UserModel.is_active.is_(True),
                )
            )
            assignee_roles = frozenset(
                Role(value)
                for value in session.scalars(
                    select(RoleModel.name)
                    .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
                    .where(
                        UserRoleModel.tenant_id == tenant_uuid,
                        UserRoleModel.user_id == assignee_uuid,
                    )
                ).all()
            )
            if assignee is None or not assignee_roles.intersection({Role.ADMIN, Role.REVIEWER}):
                raise PlatformValidationError("The selected user is not an active review assignee.")
            if (
                task.task_type
                in {
                    ReviewTaskType.MANAGER_REVIEW.value,
                    ReviewTaskType.POLICY_EXCEPTION_REVIEW.value,
                    ReviewTaskType.SAFETY_REVIEW.value,
                }
                and Role.ADMIN not in assignee_roles
            ):
                raise PlatformValidationError(
                    "This review type must be assigned to an administrator."
                )

            now = datetime.now(UTC)
            previous_assignee = task.current_assignee_id
            action = (
                ReviewActionType.REASSIGNED
                if status is ReviewTaskStatus.CLAIMED
                else ReviewActionType.ASSIGNED
            )
            if previous_assignee is not None:
                _release_assignment(session, task, now)
            _append_action(
                session,
                task=task,
                action=action,
                to_status=ReviewTaskStatus.CLAIMED,
                actor_id=UUID(actor_id),
                actor_role_value=Role.ADMIN,
                expected_version=expected_version,
                payload={
                    "assignment_type": AssignmentType.ADMIN_ASSIGNMENT.value,
                    "assignee_id": assignee_id,
                    "previous_assignee_id": (
                        str(previous_assignee) if previous_assignee is not None else None
                    ),
                },
                rationale=rationale,
                now=now,
            )
            task.status = ReviewTaskStatus.CLAIMED.value
            task.current_assignee_id = assignee_uuid
            task.version += 1
            task.updated_at = now
            session.add(
                HumanReviewAssignmentModel(
                    id=uuid4(),
                    tenant_id=task.tenant_id,
                    review_task_id=task.id,
                    assignee_id=assignee_uuid,
                    assigned_by=UUID(actor_id),
                    assignment_type=AssignmentType.ADMIN_ASSIGNMENT.value,
                    assigned_at=now,
                    released_at=None,
                    created_at=now,
                )
            )
            session.flush()
            return _to_task(task)

    def claim(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
    ) -> ReviewTask:
        with self._factory.begin() as session:
            task = _lock_task(session, tenant_id, task_id)
            if task.status == ReviewTaskStatus.CLAIMED.value:
                raise ReviewTaskAlreadyClaimedError()
            _check_version(task, expected_version)
            status = ReviewTaskStatus(task.status)
            if not can_claim(task_type=_to_task(task).task_type, status=status, roles=roles):
                if Role.ADMIN not in roles and Role.REVIEWER not in roles:
                    raise ForbiddenError()
                if status in {ReviewTaskStatus.PENDING, ReviewTaskStatus.ESCALATED}:
                    raise ForbiddenError()
                raise InvalidReviewTransitionError()
            next_status = transition(status, ReviewActionType.CLAIMED)
            now = datetime.now(UTC)
            role = actor_role(roles)
            assignment_type = (
                AssignmentType.ESCALATION_CLAIM
                if status is ReviewTaskStatus.ESCALATED
                else AssignmentType.SELF_CLAIM
            )
            _append_action(
                session,
                task=task,
                action=ReviewActionType.CLAIMED,
                to_status=next_status,
                actor_id=UUID(actor_id),
                actor_role_value=role,
                expected_version=expected_version,
                payload={"assignment_type": assignment_type.value},
                now=now,
            )
            task.status = next_status.value
            task.current_assignee_id = UUID(actor_id)
            task.version += 1
            task.updated_at = now
            session.add(
                HumanReviewAssignmentModel(
                    id=uuid4(),
                    tenant_id=task.tenant_id,
                    review_task_id=task.id,
                    assignee_id=UUID(actor_id),
                    assigned_by=UUID(actor_id),
                    assignment_type=assignment_type.value,
                    assigned_at=now,
                    released_at=None,
                    created_at=now,
                )
            )
            session.flush()
            return _to_task(task)

    def release(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        reason_code: str | None,
        rationale: str | None,
    ) -> ReviewTask:
        return self._assigned_transition(
            tenant_id=tenant_id,
            task_id=task_id,
            actor_id=actor_id,
            roles=roles,
            expected_version=expected_version,
            action=ReviewActionType.RELEASED,
            reason_codes=((reason_code,) if reason_code is not None else ()),
            rationale=rationale,
            payload={},
        )

    def request_additional_evidence(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        reason_codes: tuple[AdditionalEvidenceReason, ...],
        instructions: str,
        rationale: str | None,
    ) -> ReviewTask:
        return self._assigned_transition(
            tenant_id=tenant_id,
            task_id=task_id,
            actor_id=actor_id,
            roles=roles,
            expected_version=expected_version,
            action=ReviewActionType.EVIDENCE_REQUESTED,
            reason_codes=tuple(item.value for item in reason_codes),
            rationale=rationale,
            payload={"instructions": instructions},
        )

    def resume(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        rationale: str | None,
    ) -> ReviewTask:
        with self._factory.begin() as session:
            task = _lock_task(session, tenant_id, task_id)
            _check_version(task, expected_version)
            if ReviewTaskStatus(task.status) is not ReviewTaskStatus.WAITING_FOR_EVIDENCE:
                raise InvalidReviewTransitionError()
            actor_uuid = UUID(actor_id)
            if task.current_assignee_id is None:
                raise ReviewPacketIntegrityError("Waiting task has no retained assignee.")
            if task.current_assignee_id != actor_uuid and Role.ADMIN not in roles:
                raise ForbiddenError()
            packet = session.scalar(
                select(HumanReviewPacketModel).where(
                    HumanReviewPacketModel.tenant_id == task.tenant_id,
                    HumanReviewPacketModel.review_task_id == task.id,
                )
            )
            assert packet is not None
            new_evidence = session.scalar(
                select(func.count())
                .select_from(CaseEvidenceModel)
                .where(
                    CaseEvidenceModel.tenant_id == task.tenant_id,
                    CaseEvidenceModel.case_id == task.case_id,
                    CaseEvidenceModel.upload_status == "AVAILABLE",
                    CaseEvidenceModel.created_at > packet.created_at,
                )
            )
            if not new_evidence and not (Role.ADMIN in roles and (rationale or "").strip()):
                raise InvalidReviewTransitionError(
                    "New available evidence or an explicit administrator reason is required."
                )
            now = datetime.now(UTC)
            next_status = transition(ReviewTaskStatus(task.status), ReviewActionType.RESUMED)
            _append_action(
                session,
                task=task,
                action=ReviewActionType.RESUMED,
                to_status=next_status,
                actor_id=UUID(actor_id),
                actor_role_value=actor_role(roles),
                expected_version=expected_version,
                rationale=rationale,
                payload={"new_available_evidence": int(new_evidence or 0)},
                now=now,
            )
            task.status = next_status.value
            task.version += 1
            task.updated_at = now
            session.flush()
            return _to_task(task)

    def escalate(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        reason_codes: tuple[EscalationReason, ...],
        rationale: str,
    ) -> ReviewTask:
        return self._assigned_transition(
            tenant_id=tenant_id,
            task_id=task_id,
            actor_id=actor_id,
            roles=roles,
            expected_version=expected_version,
            action=ReviewActionType.ESCALATED,
            reason_codes=tuple(item.value for item in reason_codes),
            rationale=rationale,
            payload={},
        )

    def _assigned_transition(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        action: ReviewActionType,
        reason_codes: tuple[str, ...],
        rationale: str | None,
        payload: dict[str, object],
    ) -> ReviewTask:
        with self._factory.begin() as session:
            task = _lock_task(session, tenant_id, task_id)
            _check_version(task, expected_version)
            if ReviewTaskStatus(task.status) is not ReviewTaskStatus.CLAIMED:
                raise InvalidReviewTransitionError()
            actor_uuid = UUID(actor_id)
            is_admin_override = Role.ADMIN in roles and task.current_assignee_id != actor_uuid
            if task.current_assignee_id != actor_uuid and Role.ADMIN not in roles:
                raise ForbiddenError()
            now = datetime.now(UTC)
            next_status = transition(ReviewTaskStatus(task.status), action)
            _append_action(
                session,
                task=task,
                action=action,
                to_status=next_status,
                actor_id=actor_uuid,
                actor_role_value=actor_role(roles),
                expected_version=expected_version,
                reason_codes=reason_codes,
                rationale=rationale,
                payload={**payload, "admin_override": is_admin_override},
                now=now,
            )
            preserve_assignment = action is ReviewActionType.EVIDENCE_REQUESTED
            if not preserve_assignment:
                _release_assignment(session, task, now)
            task.status = next_status.value
            if not preserve_assignment:
                task.current_assignee_id = None
            task.version += 1
            task.updated_at = now
            session.flush()
            return _to_task(task)

    def resolve(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        request: HumanDecisionRequest,
        correlation_id: str = "human-review-resolve",
    ) -> tuple[ReviewTask, HumanDecision]:
        with self._factory.begin() as session:
            task = _lock_task(session, tenant_id, task_id)
            existing_decision = session.scalar(
                select(HumanReviewDecisionModel).where(
                    HumanReviewDecisionModel.tenant_id == task.tenant_id,
                    HumanReviewDecisionModel.review_task_id == task.id,
                )
            )
            if existing_decision is not None:
                existing_basis = list(
                    session.scalars(
                        select(HumanReviewDecisionBasisModel).where(
                            HumanReviewDecisionBasisModel.tenant_id == task.tenant_id,
                            HumanReviewDecisionBasisModel.human_review_decision_id
                            == existing_decision.id,
                        )
                    ).all()
                )
                _verify_decision_hash(session, existing_decision, existing_basis)
                raise DuplicateHumanDecisionError()
            _check_version(task, expected_version)
            if ReviewTaskStatus(task.status) is not ReviewTaskStatus.CLAIMED:
                raise InvalidReviewTransitionError()
            if (
                task.task_type
                in {
                    "MANAGER_REVIEW",
                    "SAFETY_REVIEW",
                }
                and Role.ADMIN not in roles
            ):
                raise ForbiddenError("Only an administrator may resolve this review task type.")
            actor_uuid = UUID(actor_id)
            admin_override = Role.ADMIN in roles and task.current_assignee_id != actor_uuid
            if task.current_assignee_id != actor_uuid and Role.ADMIN not in roles:
                raise ForbiddenError()
            packet = session.scalar(
                select(HumanReviewPacketModel).where(
                    HumanReviewPacketModel.tenant_id == task.tenant_id,
                    HumanReviewPacketModel.review_task_id == task.id,
                )
            )
            assert packet is not None
            _verify_packet_hash(packet)
            if packet.citation_pack_id is not None:
                _verify_citation_pack(
                    session,
                    tenant_id=task.tenant_id,
                    case_id=task.case_id,
                    pack_id=packet.citation_pack_id,
                )
            canonical_basis = tuple(
                sorted(request.basis, key=lambda item: (item.type.value, item.reference_id))
            )
            resolved_basis = _validate_basis(
                session,
                task=task,
                packet=packet,
                basis=canonical_basis,
            )
            effects = tuple(PolicyEffect.model_validate(item) for item in packet.policy_effects)
            relation = compute_outcome_relation(
                summary=EvaluationSummary(packet.policy_summary_status),
                effects=effects,
                decision=request.decision,
            )
            now = datetime.now(UTC)
            decision_id = uuid4()
            decision_row = HumanReviewDecisionModel(
                id=decision_id,
                tenant_id=task.tenant_id,
                review_task_id=task.id,
                decision_type=request.decision.value,
                reason_codes=[item.value for item in request.reason_codes],
                rationale=request.rationale,
                outcome_relation=relation.value,
                outcome_relation_rule_version=OUTCOME_RELATION_RULE_VERSION,
                decided_by=actor_uuid,
                decided_at=now,
                decision_schema_version=DECISION_SCHEMA_VERSION,
                content_hash="0" * 64,
                created_at=now,
            )
            basis_rows = [
                HumanReviewDecisionBasisModel(
                    id=uuid4(),
                    tenant_id=task.tenant_id,
                    human_review_decision_id=decision_id,
                    basis_type=reference.type.value,
                    reference_id=reference.reference_id,
                    **columns,
                    created_at=now,
                )
                for reference, columns in resolved_basis
            ]
            decision_row.content_hash = compute_human_decision_content_hash(
                decision_row,
                basis_rows,
            )
            session.add(decision_row)
            # Basis rows reference the immutable decision aggregate directly.
            session.flush()
            session.add_all(basis_rows)
            next_status = transition(ReviewTaskStatus(task.status), ReviewActionType.RESOLVED)
            _append_action(
                session,
                task=task,
                action=ReviewActionType.RESOLVED,
                to_status=next_status,
                actor_id=actor_uuid,
                actor_role_value=actor_role(roles),
                expected_version=expected_version,
                reason_codes=tuple(item.value for item in request.reason_codes),
                rationale=request.rationale,
                payload={"decision_id": str(decision_id), "admin_override": admin_override},
                now=now,
            )
            _release_assignment(session, task, now)
            task.status = next_status.value
            task.version += 1
            task.updated_at = now
            task.resolved_at = now
            task.current_assignee_id = None
            _record_case_resolution_request(
                session,
                task=task,
                decision=decision_row,
                correlation_id=correlation_id,
                now=now,
            )
            session.flush()
            return _to_task(task), _to_decision(
                session,
                decision_row,
                list(
                    session.scalars(
                        select(HumanReviewDecisionBasisModel).where(
                            HumanReviewDecisionBasisModel.human_review_decision_id == decision_id
                        )
                    ).all()
                ),
            )


def verify_human_decision_integrity(
    session: Session,
    *,
    tenant_id: UUID,
    decision_id: UUID,
) -> HumanReviewDecisionModel:
    """Load and verify one immutable Human Decision inside the caller transaction."""

    decision = session.scalar(
        select(HumanReviewDecisionModel).where(
            HumanReviewDecisionModel.tenant_id == tenant_id,
            HumanReviewDecisionModel.id == decision_id,
        )
    )
    if decision is None:
        raise ReviewPacketIntegrityError("The source Human Decision is missing.")
    basis = list(
        session.scalars(
            select(HumanReviewDecisionBasisModel).where(
                HumanReviewDecisionBasisModel.tenant_id == tenant_id,
                HumanReviewDecisionBasisModel.human_review_decision_id == decision_id,
            )
        ).all()
    )
    _verify_decision_hash(session, decision, basis)
    return decision


def _record_case_resolution_request(
    session: Session,
    *,
    task: HumanReviewTaskModel,
    decision: HumanReviewDecisionModel,
    correlation_id: str,
    now: datetime,
) -> None:
    """Atomically create the Case Resolution projection and exact request event."""

    case = session.scalar(
        select(CaseModel)
        .where(CaseModel.tenant_id == task.tenant_id, CaseModel.id == task.case_id)
        .with_for_update()
    )
    if case is None:
        raise ReviewPacketIntegrityError("The review task Case is missing.")
    resolution = session.scalar(
        select(CaseResolutionModel)
        .where(
            CaseResolutionModel.tenant_id == task.tenant_id,
            CaseResolutionModel.case_id == task.case_id,
        )
        .with_for_update()
    )
    if resolution is None:
        resolution_id = uuid4()
        resolution = CaseResolutionModel(
            id=resolution_id,
            tenant_id=task.tenant_id,
            case_id=task.case_id,
            source_review_task_id=task.id,
            source_human_decision_id=decision.id,
            status=ResolutionStatus.DECISION_RECORDED.value,
            version=1,
            mapping_name=ACTION_MAPPING_NAME,
            mapping_version=ACTION_MAPPING_VERSION,
            resolution_schema_version=RESOLUTION_SCHEMA_VERSION,
            missing_fields=[],
            invalid_fields=[],
            failure_code=None,
            failure_message=None,
            execution_attempt_count=0,
            claim_token=None,
            lease_expires_at=None,
            correlation_id=correlation_id,
            created_at=now,
            updated_at=now,
        )
        session.add(resolution)
        session.flush()
        session.add(
            CaseResolutionEventModel(
                id=uuid4(),
                tenant_id=task.tenant_id,
                case_id=task.case_id,
                resolution_id=resolution_id,
                sequence=1,
                event_type=ResolutionStatus.DECISION_RECORDED.value,
                from_status=None,
                to_status=ResolutionStatus.DECISION_RECORDED.value,
                human_decision_id=decision.id,
                external_action_intent_id=None,
                payload={
                    "review_task_id": str(task.id),
                    "human_decision_id": str(decision.id),
                    "mapping_name": ACTION_MAPPING_NAME,
                    "mapping_version": ACTION_MAPPING_VERSION,
                },
                created_at=now,
            )
        )
    session.add(
        CaseResolutionRequestEventModel(
            id=uuid4(),
            tenant_id=task.tenant_id,
            case_id=task.case_id,
            resolution_id=resolution.id,
            human_decision_id=decision.id,
            correlation_id=correlation_id,
            status="PENDING",
            attempt_count=0,
            available_at=now,
            claimed_at=None,
            claim_token=None,
            claimed_by=None,
            published_at=None,
            last_error=None,
            consumed_at=None,
            consumer_attempt_count=0,
            consumer_last_error=None,
            failure_code=None,
            failed_at=None,
            created_at=now,
        )
    )


def _lock_task(session: Session, tenant_id: str, task_id: str) -> HumanReviewTaskModel:
    task = session.scalar(
        select(HumanReviewTaskModel)
        .where(
            HumanReviewTaskModel.tenant_id == UUID(tenant_id),
            HumanReviewTaskModel.id == UUID(task_id),
        )
        .with_for_update()
    )
    if task is None:
        raise ReviewTaskNotFoundError()
    return task


def _check_version(task: HumanReviewTaskModel, expected: int) -> None:
    if task.version != expected:
        raise ReviewTaskVersionConflictError(details={"current_version": task.version})


def _append_action(
    session: Session,
    *,
    task: HumanReviewTaskModel,
    action: ReviewActionType,
    to_status: ReviewTaskStatus,
    actor_id: UUID,
    actor_role_value: Role,
    expected_version: int,
    payload: dict[str, object],
    now: datetime,
    reason_codes: tuple[str, ...] = (),
    rationale: str | None = None,
) -> None:
    session.add(
        HumanReviewActionModel(
            id=uuid4(),
            tenant_id=task.tenant_id,
            review_task_id=task.id,
            action_type=action.value,
            from_status=task.status,
            to_status=to_status.value,
            actor_id=actor_id,
            actor_role=actor_role_value.value,
            reason_codes=list(reason_codes),
            rationale=rationale,
            action_payload=payload,
            expected_task_version=expected_version,
            resulting_task_version=expected_version + 1,
            created_at=now,
        )
    )


def _release_assignment(session: Session, task: HumanReviewTaskModel, now: datetime) -> None:
    assignment = session.scalar(
        select(HumanReviewAssignmentModel).where(
            HumanReviewAssignmentModel.tenant_id == task.tenant_id,
            HumanReviewAssignmentModel.review_task_id == task.id,
            HumanReviewAssignmentModel.released_at.is_(None),
        )
    )
    if assignment is None:
        raise ReviewPacketIntegrityError("Claimed task has no active assignment.")
    assignment.released_at = now


def _validate_basis(
    session: Session,
    *,
    task: HumanReviewTaskModel,
    packet: HumanReviewPacketModel,
    basis: tuple[DecisionBasisReference, ...],
) -> list[tuple[DecisionBasisReference, dict[str, UUID | None]]]:
    if len({(item.type, item.reference_id) for item in basis}) != len(basis):
        raise InvalidDecisionBasisError("Duplicate decision basis reference.")
    resolved: list[tuple[DecisionBasisReference, dict[str, UUID | None]]] = []
    empty = {
        "policy_rule_result_id": None,
        "policy_clause_row_id": None,
        "citation_item_id": None,
        "case_evidence_id": None,
        "analysis_result_id": None,
    }
    for item in basis:
        columns: dict[str, UUID | None] = dict(empty)
        if item.type is DecisionBasisType.POLICY_RULE_RESULT:
            try:
                reference_uuid = UUID(item.reference_id)
            except ValueError as error:
                raise InvalidDecisionBasisError("Policy rule result ID is invalid.") from error
            row = session.scalar(
                select(PolicyRuleEvaluationResultModel).where(
                    PolicyRuleEvaluationResultModel.tenant_id == task.tenant_id,
                    PolicyRuleEvaluationResultModel.id == reference_uuid,
                    PolicyRuleEvaluationResultModel.policy_evaluation_run_id
                    == packet.policy_evaluation_run_id,
                )
            )
            if row is None:
                raise InvalidDecisionBasisError("Policy rule result belongs to another run.")
            columns["policy_rule_result_id"] = row.id
        elif item.type is DecisionBasisType.POLICY_CITATION:
            if packet.citation_pack_id is None:
                raise InvalidDecisionBasisError("The review packet has no citation pack.")
            row = session.scalar(
                select(PolicyCitationPackItemModel).where(
                    PolicyCitationPackItemModel.tenant_id == task.tenant_id,
                    PolicyCitationPackItemModel.citation_pack_id == packet.citation_pack_id,
                    PolicyCitationPackItemModel.citation_id == item.reference_id,
                )
            )
            if row is None:
                raise InvalidDecisionBasisError("Citation is outside the review packet.")
            columns["citation_item_id"] = row.id
            columns["policy_clause_row_id"] = row.policy_clause_row_id
        elif item.type is DecisionBasisType.CASE_EVIDENCE:
            try:
                reference_uuid = UUID(item.reference_id)
            except ValueError as error:
                raise InvalidDecisionBasisError("Case evidence ID is invalid.") from error
            row = session.scalar(
                select(CaseEvidenceModel)
                .join(
                    AnalysisRunEvidenceModel,
                    AnalysisRunEvidenceModel.evidence_id == CaseEvidenceModel.id,
                )
                .where(
                    CaseEvidenceModel.tenant_id == task.tenant_id,
                    CaseEvidenceModel.case_id == task.case_id,
                    CaseEvidenceModel.id == reference_uuid,
                    CaseEvidenceModel.upload_status == "AVAILABLE",
                    AnalysisRunEvidenceModel.analysis_run_id == packet.analysis_run_id,
                )
            )
            if row is None:
                raise InvalidDecisionBasisError("Evidence is outside the frozen analysis run.")
            columns["case_evidence_id"] = row.id
        else:
            if item.reference_id != str(packet.llm_extraction_result_v2_id):
                raise InvalidDecisionBasisError("Analysis result is outside the review packet.")
            row = session.scalar(
                select(LLMExtractionResultV2Model).where(
                    LLMExtractionResultV2Model.tenant_id == task.tenant_id,
                    LLMExtractionResultV2Model.id == packet.llm_extraction_result_v2_id,
                )
            )
            if row is None:
                raise InvalidDecisionBasisError()
            columns["analysis_result_id"] = row.id
        resolved.append((item, columns))
    return resolved


def _to_task(row: HumanReviewTaskModel) -> ReviewTask:
    return ReviewTask.model_validate(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "case_id": str(row.case_id),
            "policy_evaluation_run_id": str(row.policy_evaluation_run_id),
            "task_type": row.task_type,
            "priority": row.priority,
            "status": row.status,
            "current_assignee_id": (
                str(row.current_assignee_id) if row.current_assignee_id else None
            ),
            "version": row.version,
            "mapping_rule_name": row.mapping_rule_name,
            "mapping_rule_version": row.mapping_rule_version,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "resolved_at": row.resolved_at,
        }
    )


def _to_packet(row: HumanReviewPacketModel) -> ReviewPacket:
    _verify_packet_hash(row)
    return ReviewPacket.model_validate(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "review_task_id": str(row.review_task_id),
            "case_id": str(row.case_id),
            "analysis_run_id": str(row.analysis_run_id),
            "policy_evaluation_run_id": str(row.policy_evaluation_run_id),
            "rule_set_id": str(row.rule_set_id),
            "rule_set_version": row.rule_set_version,
            "rule_set_hash": row.rule_set_hash,
            "llm_extraction_result_v2_id": str(row.llm_extraction_result_v2_id),
            "completeness_result_id": str(row.completeness_result_id),
            "vision_result_ids": tuple(str(item) for item in row.vision_result_ids),
            "alignment_result_id": (
                str(row.alignment_result_id) if row.alignment_result_id else None
            ),
            "citation_pack_id": str(row.citation_pack_id) if row.citation_pack_id else None,
            "grounding_result_id": (
                str(row.grounding_result_id) if row.grounding_result_id else None
            ),
            "case_metadata_snapshot": row.case_metadata_snapshot,
            "qualification_snapshot": row.qualification_snapshot,
            "policy_effects": tuple(
                PolicyEffect.model_validate(item) for item in row.policy_effects
            ),
            "policy_summary_status": row.policy_summary_status,
            "packet_schema_version": row.packet_schema_version,
            "packet_hash": row.packet_hash,
            "created_at": row.created_at,
        }
    )


def _to_action(row: HumanReviewActionModel) -> ReviewAction:
    return ReviewAction.model_validate(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "review_task_id": str(row.review_task_id),
            "action_type": row.action_type,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "actor_role": row.actor_role,
            "reason_codes": tuple(str(item) for item in row.reason_codes),
            "rationale": row.rationale,
            "action_payload": row.action_payload,
            "expected_task_version": row.expected_task_version,
            "resulting_task_version": row.resulting_task_version,
            "created_at": row.created_at,
        }
    )


def _verify_citation_pack(
    session: Session,
    *,
    tenant_id: UUID,
    case_id: UUID,
    pack_id: UUID,
) -> None:
    try:
        pack = load_verified_citation_pack(session, tenant_id, pack_id)
    except (PlatformValidationError, ValueError) as error:
        raise ReviewPacketIntegrityError(
            "The immutable citation pack failed integrity validation."
        ) from error
    if UUID(pack.case_id) != case_id:
        raise ReviewPacketIntegrityError("The citation pack belongs to another case.")


def _to_decision(
    session: Session,
    row: HumanReviewDecisionModel,
    basis_rows: Sequence[HumanReviewDecisionBasisModel],
) -> HumanDecision:
    _verify_decision_hash(session, row, basis_rows)
    ordered_basis = sorted(basis_rows, key=lambda item: (item.basis_type, item.reference_id))
    return HumanDecision.model_validate(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "review_task_id": str(row.review_task_id),
            "decision_type": row.decision_type,
            "reason_codes": tuple(str(item) for item in row.reason_codes),
            "rationale": row.rationale,
            "basis": tuple(
                {"type": item.basis_type, "reference_id": item.reference_id}
                for item in ordered_basis
            ),
            "outcome_relation": row.outcome_relation,
            "outcome_relation_rule_version": row.outcome_relation_rule_version,
            "decided_by": str(row.decided_by),
            "decided_at": row.decided_at,
            "decision_schema_version": row.decision_schema_version,
            "content_hash": row.content_hash,
        }
    )


def _packet_hash_payload(row: HumanReviewPacketModel) -> dict[str, object]:
    return {
        "tenant_id": str(row.tenant_id),
        "review_task_id": str(row.review_task_id),
        "case_id": str(row.case_id),
        "analysis_run_id": str(row.analysis_run_id),
        "policy_evaluation_run_id": str(row.policy_evaluation_run_id),
        "rule_set_id": str(row.rule_set_id),
        "rule_set_version": row.rule_set_version,
        "rule_set_hash": row.rule_set_hash,
        "llm_extraction_result_v2_id": str(row.llm_extraction_result_v2_id),
        "completeness_result_id": str(row.completeness_result_id),
        "vision_result_ids": tuple(str(item) for item in row.vision_result_ids),
        "alignment_result_id": str(row.alignment_result_id) if row.alignment_result_id else None,
        "citation_pack_id": str(row.citation_pack_id) if row.citation_pack_id else None,
        "grounding_result_id": str(row.grounding_result_id) if row.grounding_result_id else None,
        "case_metadata_snapshot": row.case_metadata_snapshot,
        "qualification_snapshot": row.qualification_snapshot,
        "policy_effects": row.policy_effects,
        "policy_summary_status": row.policy_summary_status,
        "packet_schema_version": row.packet_schema_version,
    }


def _verify_packet_hash(row: HumanReviewPacketModel) -> None:
    if canonical_hash(_packet_hash_payload(row)) != row.packet_hash:
        raise ReviewPacketIntegrityError("The immutable review packet hash does not match.")


def _decision_hash_payload(
    row: HumanReviewDecisionModel,
    *,
    reason_codes: Sequence[str],
    basis_rows: Sequence[HumanReviewDecisionBasisModel],
) -> dict[str, object]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "review_task_id": str(row.review_task_id),
        "decision_type": row.decision_type,
        "reason_codes": list(reason_codes),
        "rationale": row.rationale,
        "basis": [_basis_hash_payload(item) for item in basis_rows],
        "outcome_relation": row.outcome_relation,
        "outcome_relation_rule_version": row.outcome_relation_rule_version,
        "decided_by": str(row.decided_by),
        "decided_at": _canonical_datetime(row.decided_at),
        "decision_schema_version": row.decision_schema_version,
    }


def compute_human_decision_content_hash(
    row: HumanReviewDecisionModel,
    basis_rows: Sequence[HumanReviewDecisionBasisModel],
) -> str:
    """Return the canonical persisted aggregate hash for a human decision."""

    return canonical_hash(
        _decision_hash_payload(
            row,
            reason_codes=sorted(str(item) for item in row.reason_codes),
            basis_rows=sorted(
                basis_rows,
                key=lambda item: (item.basis_type, item.reference_id),
            ),
        )
    )


def _basis_hash_payload(row: HumanReviewDecisionBasisModel) -> dict[str, object]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "human_review_decision_id": str(row.human_review_decision_id),
        "type": row.basis_type,
        "reference_id": row.reference_id,
        "policy_rule_result_id": (
            str(row.policy_rule_result_id) if row.policy_rule_result_id else None
        ),
        "policy_clause_row_id": (
            str(row.policy_clause_row_id) if row.policy_clause_row_id else None
        ),
        "citation_item_id": str(row.citation_item_id) if row.citation_item_id else None,
        "case_evidence_id": str(row.case_evidence_id) if row.case_evidence_id else None,
        "analysis_result_id": str(row.analysis_result_id) if row.analysis_result_id else None,
    }


def _legacy_decision_hash_payload(
    row: HumanReviewDecisionModel,
    *,
    reason_codes: Sequence[str],
    basis_rows: Sequence[HumanReviewDecisionBasisModel],
) -> dict[str, object]:
    return {
        "review_task_id": str(row.review_task_id),
        "decision_type": row.decision_type,
        "reason_codes": list(reason_codes),
        "rationale": row.rationale,
        "basis": [
            {"type": item.basis_type, "reference_id": item.reference_id} for item in basis_rows
        ],
        "outcome_relation": row.outcome_relation,
        "outcome_relation_rule_version": row.outcome_relation_rule_version,
        "decided_by": str(row.decided_by),
        "decision_schema_version": row.decision_schema_version,
    }


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _verify_decision_hash(
    session: Session,
    row: HumanReviewDecisionModel,
    basis_rows: Sequence[HumanReviewDecisionBasisModel],
) -> None:
    _verify_decision_basis_links(session, row, basis_rows)
    ordered_basis = sorted(basis_rows, key=lambda item: (item.basis_type, item.reference_id))
    stored_reasons = [str(item) for item in row.reason_codes]
    ordered_reasons = sorted(stored_reasons)
    strong_hash = compute_human_decision_content_hash(row, ordered_basis)
    if row.content_hash == strong_hash:
        return

    # Explicit pre-0012 compatibility: legacy hashes are accepted only after
    # all typed links and immutable packet/citation sources have been verified,
    # and only when the legacy audit timestamps retain their creation invariant.
    legacy_candidates = {
        canonical_hash(
            _legacy_decision_hash_payload(
                row,
                reason_codes=reasons,
                basis_rows=basis,
            )
        )
        for reasons in (stored_reasons, ordered_reasons)
        for basis in (basis_rows, ordered_basis)
    }
    if (
        row.content_hash in legacy_candidates
        and row.decision_schema_version == "1.0.0"
        and _canonical_datetime(row.created_at) == _canonical_datetime(row.decided_at)
    ):
        return
    raise ReviewPacketIntegrityError("The immutable human decision hash does not match.")


def _verify_decision_basis_links(
    session: Session,
    decision: HumanReviewDecisionModel,
    basis_rows: Sequence[HumanReviewDecisionBasisModel],
) -> None:
    packet = session.scalar(
        select(HumanReviewPacketModel).where(
            HumanReviewPacketModel.tenant_id == decision.tenant_id,
            HumanReviewPacketModel.review_task_id == decision.review_task_id,
        )
    )
    if packet is None:
        raise ReviewPacketIntegrityError("The decision review packet was not found.")
    _verify_packet_hash(packet)
    if packet.citation_pack_id is not None:
        _verify_citation_pack(
            session,
            tenant_id=decision.tenant_id,
            case_id=packet.case_id,
            pack_id=packet.citation_pack_id,
        )

    for basis in basis_rows:
        if basis.tenant_id != decision.tenant_id or basis.human_review_decision_id != decision.id:
            raise ReviewPacketIntegrityError("Decision basis aggregate identity is invalid.")
        typed = {
            "policy_rule_result_id": basis.policy_rule_result_id,
            "policy_clause_row_id": basis.policy_clause_row_id,
            "citation_item_id": basis.citation_item_id,
            "case_evidence_id": basis.case_evidence_id,
            "analysis_result_id": basis.analysis_result_id,
        }
        expected_non_null = {
            DecisionBasisType.POLICY_RULE_RESULT.value: {"policy_rule_result_id"},
            DecisionBasisType.POLICY_CITATION.value: {
                "policy_clause_row_id",
                "citation_item_id",
            },
            DecisionBasisType.CASE_EVIDENCE.value: {"case_evidence_id"},
            DecisionBasisType.ANALYSIS_RESULT.value: {"analysis_result_id"},
        }.get(basis.basis_type)
        actual_non_null = {name for name, value in typed.items() if value is not None}
        if expected_non_null is None or actual_non_null != expected_non_null:
            raise ReviewPacketIntegrityError("Decision basis typed reference is invalid.")

        if basis.basis_type == DecisionBasisType.POLICY_RULE_RESULT.value:
            result = session.scalar(
                select(PolicyRuleEvaluationResultModel).where(
                    PolicyRuleEvaluationResultModel.tenant_id == decision.tenant_id,
                    PolicyRuleEvaluationResultModel.id == basis.policy_rule_result_id,
                    PolicyRuleEvaluationResultModel.policy_evaluation_run_id
                    == packet.policy_evaluation_run_id,
                )
            )
            valid = result is not None and basis.reference_id == str(result.id)
        elif basis.basis_type == DecisionBasisType.POLICY_CITATION.value:
            citation = session.scalar(
                select(PolicyCitationPackItemModel).where(
                    PolicyCitationPackItemModel.tenant_id == decision.tenant_id,
                    PolicyCitationPackItemModel.id == basis.citation_item_id,
                    PolicyCitationPackItemModel.citation_pack_id == packet.citation_pack_id,
                    PolicyCitationPackItemModel.policy_clause_row_id == basis.policy_clause_row_id,
                )
            )
            valid = citation is not None and basis.reference_id == citation.citation_id
        elif basis.basis_type == DecisionBasisType.CASE_EVIDENCE.value:
            evidence = session.scalar(
                select(CaseEvidenceModel)
                .join(
                    AnalysisRunEvidenceModel,
                    AnalysisRunEvidenceModel.evidence_id == CaseEvidenceModel.id,
                )
                .where(
                    CaseEvidenceModel.tenant_id == decision.tenant_id,
                    CaseEvidenceModel.id == basis.case_evidence_id,
                    CaseEvidenceModel.case_id == packet.case_id,
                    AnalysisRunEvidenceModel.analysis_run_id == packet.analysis_run_id,
                )
            )
            valid = evidence is not None and basis.reference_id == str(evidence.id)
        else:
            analysis = session.scalar(
                select(LLMExtractionResultV2Model).where(
                    LLMExtractionResultV2Model.tenant_id == decision.tenant_id,
                    LLMExtractionResultV2Model.id == basis.analysis_result_id,
                    LLMExtractionResultV2Model.id == packet.llm_extraction_result_v2_id,
                )
            )
            valid = analysis is not None and basis.reference_id == str(analysis.id)
        if not valid:
            raise ReviewPacketIntegrityError("Decision basis target link is invalid.")


__all__ = ["SQLAlchemyHumanReviewRepository", "compute_human_decision_content_hash"]
