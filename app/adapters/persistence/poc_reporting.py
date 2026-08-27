"""SQLAlchemy adapter for immutable Review Reports and tenant-scoped PoC KPIs."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.human_review import verify_human_decision_integrity
from app.adapters.persistence.models import (
    AnalysisRunModel,
    CaseModel,
    CaseResolutionEventModel,
    CaseResolutionModel,
    ExternalActionIntentModel,
    ExternalActionSimulationResultModel,
    HumanReviewActionModel,
    HumanReviewAssignmentModel,
    HumanReviewDecisionBasisModel,
    HumanReviewDecisionModel,
    HumanReviewPacketModel,
    HumanReviewTaskModel,
    PolicyEvaluationRunModel,
    PolicyRuleSetModel,
    ReviewReportModel,
)
from app.platform.case.models import JsonValue
from app.platform.case_resolution import (
    CaseResolutionIntegrityError,
    ExternalActionIntent,
    action_intent_hash_payload,
    canonical_hash,
)
from app.platform.human_review import ReviewPacketIntegrityError
from app.platform.poc_reporting import MetricUnit, PocMetric, PocSummary, ReviewReport

_TERMINAL_RESOLUTION_STATUSES = frozenset(
    {
        "ACTION_NOT_REQUIRED",
        "MANUAL_FOLLOW_UP_REQUIRED",
        "ACTION_NEEDS_INPUT",
        "ACTION_DRY_RUN_VALIDATED",
        "ACTION_DRY_RUN_FAILED",
    }
)
_APPROVAL_DECISIONS = (
    "APPROVE_REFUND",
    "APPROVE_EXCHANGE",
    "APPROVE_RESHIPMENT",
    "APPROVE_REPAIR",
)
_COMPARABLE_RELATIONS = (
    "CONSISTENT_WITH_RECOMMENDATION",
    "DIFFERS_FROM_RECOMMENDATION",
)
_TERMINAL_ANALYSIS_STATUSES = ("SUCCEEDED", "FAILED", "PARTIAL_SUCCESS")


class SQLAlchemyPocReportingRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def get_review_report(self, *, tenant_id: str, case_id: str) -> ReviewReport | None:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        if tenant_uuid is None or case_uuid is None:
            return None
        with self._factory() as session:
            row = session.scalar(
                select(ReviewReportModel)
                .where(
                    ReviewReportModel.tenant_id == tenant_uuid,
                    ReviewReportModel.case_id == case_uuid,
                )
                .order_by(
                    ReviewReportModel.resolution_version.desc(),
                    ReviewReportModel.generated_at.desc(),
                    ReviewReportModel.id.desc(),
                )
                .limit(1)
            )
            return _to_review_report(row) if row is not None else None

    def get_poc_summary(self, *, tenant_id: str) -> PocSummary:
        tenant_uuid = _optional_uuid(tenant_id)
        if tenant_uuid is None:
            return _empty_summary()
        with self._factory() as session:
            review_time = _review_time_metric(session, tenant_uuid)
            recommendation_difference = _recommendation_difference_metric(session, tenant_uuid)
            additional_evidence = _additional_evidence_metric(session, tenant_uuid)
            action_input_missing = _action_input_missing_metric(session, tenant_uuid)
            dry_run_success = _dry_run_success_metric(session, tenant_uuid)
            analysis_failure, analysis_partial = _analysis_terminal_metrics(session, tenant_uuid)
        return PocSummary(
            generated_at=datetime.now(UTC),
            review_time=review_time,
            recommendation_difference_rate=recommendation_difference,
            additional_evidence_request_rate=additional_evidence,
            action_input_missing_rate=action_input_missing,
            dry_run_success_rate=dry_run_success,
            analysis_failure_rate=analysis_failure,
            analysis_partial_success_rate=analysis_partial,
        )


def create_review_report_for_terminal_transition(
    session: Session,
    *,
    resolution: CaseResolutionModel,
    terminal_event: CaseResolutionEventModel,
) -> ReviewReportModel | None:
    """Add one report to the caller's transaction for a new terminal version."""

    if resolution.status not in _TERMINAL_RESOLUTION_STATUSES:
        return None
    if (
        terminal_event.tenant_id != resolution.tenant_id
        or terminal_event.case_id != resolution.case_id
        or terminal_event.resolution_id != resolution.id
        or terminal_event.to_status != resolution.status
    ):
        raise RuntimeError("terminal Resolution event identity does not match its projection")

    session.flush()
    existing = session.scalar(
        select(ReviewReportModel).where(
            ReviewReportModel.tenant_id == resolution.tenant_id,
            ReviewReportModel.resolution_id == resolution.id,
            ReviewReportModel.resolution_version == resolution.version,
        )
    )
    if existing is not None:
        if existing.terminal_event_id != terminal_event.id:
            raise RuntimeError(
                "terminal Resolution version is already bound to a different report event"
            )
        _to_review_report(existing)
        return existing

    generated_at = _aware(terminal_event.created_at)

    case_row = session.scalar(
        select(CaseModel).where(
            CaseModel.tenant_id == resolution.tenant_id,
            CaseModel.id == resolution.case_id,
        )
    )
    task = session.scalar(
        select(HumanReviewTaskModel).where(
            HumanReviewTaskModel.tenant_id == resolution.tenant_id,
            HumanReviewTaskModel.id == resolution.source_review_task_id,
        )
    )
    packet = session.scalar(
        select(HumanReviewPacketModel).where(
            HumanReviewPacketModel.tenant_id == resolution.tenant_id,
            HumanReviewPacketModel.review_task_id == resolution.source_review_task_id,
        )
    )
    decision = session.scalar(
        select(HumanReviewDecisionModel).where(
            HumanReviewDecisionModel.tenant_id == resolution.tenant_id,
            HumanReviewDecisionModel.id == resolution.source_human_decision_id,
        )
    )
    if case_row is None or task is None or packet is None or decision is None:
        if resolution.failure_code is not None:
            return _create_degraded_review_report(
                session,
                resolution=resolution,
                terminal_event=terminal_event,
                generated_at=generated_at,
                source_failure="SOURCE_GRAPH_INCOMPLETE",
            )
        raise RuntimeError("terminal Resolution report source graph is incomplete")
    if (
        task.case_id != resolution.case_id
        or packet.case_id != resolution.case_id
        or decision.review_task_id != resolution.source_review_task_id
    ):
        if resolution.failure_code is not None:
            return _create_degraded_review_report(
                session,
                resolution=resolution,
                terminal_event=terminal_event,
                generated_at=generated_at,
                source_failure="SOURCE_GRAPH_INCONSISTENT",
            )
        raise RuntimeError("terminal Resolution report source graph is inconsistent")
    try:
        decision = verify_human_decision_integrity(
            session,
            tenant_id=resolution.tenant_id,
            decision_id=resolution.source_human_decision_id,
        )
    except ReviewPacketIntegrityError:
        if resolution.failure_code is None:
            raise
        return _create_degraded_review_report(
            session,
            resolution=resolution,
            terminal_event=terminal_event,
            generated_at=generated_at,
            source_failure="HUMAN_REVIEW_INTEGRITY_FAILED",
        )

    analysis = session.scalar(
        select(AnalysisRunModel).where(
            AnalysisRunModel.tenant_id == resolution.tenant_id,
            AnalysisRunModel.id == packet.analysis_run_id,
            AnalysisRunModel.case_id == resolution.case_id,
        )
    )
    policy_run = session.scalar(
        select(PolicyEvaluationRunModel).where(
            PolicyEvaluationRunModel.tenant_id == resolution.tenant_id,
            PolicyEvaluationRunModel.id == packet.policy_evaluation_run_id,
            PolicyEvaluationRunModel.case_id == resolution.case_id,
        )
    )
    rule_set = session.scalar(
        select(PolicyRuleSetModel).where(
            PolicyRuleSetModel.tenant_id == resolution.tenant_id,
            PolicyRuleSetModel.id == packet.rule_set_id,
        )
    )
    if analysis is None or policy_run is None or rule_set is None:
        if resolution.failure_code is not None:
            return _create_degraded_review_report(
                session,
                resolution=resolution,
                terminal_event=terminal_event,
                generated_at=generated_at,
                source_failure="ANALYSIS_OR_POLICY_SOURCE_MISSING",
            )
        raise RuntimeError("terminal Resolution report analysis or policy source is missing")

    basis_rows = tuple(
        session.scalars(
            select(HumanReviewDecisionBasisModel)
            .where(
                HumanReviewDecisionBasisModel.tenant_id == resolution.tenant_id,
                HumanReviewDecisionBasisModel.human_review_decision_id == decision.id,
            )
            .order_by(
                HumanReviewDecisionBasisModel.basis_type,
                HumanReviewDecisionBasisModel.reference_id,
                HumanReviewDecisionBasisModel.id,
            )
        )
    )
    intent = session.scalar(
        select(ExternalActionIntentModel).where(
            ExternalActionIntentModel.tenant_id == resolution.tenant_id,
            ExternalActionIntentModel.resolution_id == resolution.id,
        )
    )
    result = None
    if intent is not None:
        try:
            _verify_intent(intent)
        except CaseResolutionIntegrityError:
            if resolution.failure_code is None:
                raise
            return _create_degraded_review_report(
                session,
                resolution=resolution,
                terminal_event=terminal_event,
                generated_at=generated_at,
                source_failure="ACTION_INTENT_INTEGRITY_FAILED",
            )
        result = session.scalar(
            select(ExternalActionSimulationResultModel).where(
                ExternalActionSimulationResultModel.tenant_id == resolution.tenant_id,
                ExternalActionSimulationResultModel.external_action_intent_id == intent.id,
            )
        )
    if result is not None:
        try:
            _verify_result(result)
        except CaseResolutionIntegrityError:
            if resolution.failure_code is None:
                raise
            return _create_degraded_review_report(
                session,
                resolution=resolution,
                terminal_event=terminal_event,
                generated_at=generated_at,
                source_failure="SIMULATION_RESULT_INTEGRITY_FAILED",
            )

    report = ReviewReport.create(
        report_id=str(uuid4()),
        tenant_id=str(resolution.tenant_id),
        case_id=str(resolution.case_id),
        resolution_id=str(resolution.id),
        resolution_version=resolution.version,
        terminal_event_id=str(terminal_event.id),
        case_snapshot={
            "case_id": str(case_row.id),
            "status": case_row.status,
            "order_ref": case_row.order_ref,
            "product_ref": case_row.product_ref,
            "requested_action": case_row.requested_action,
            "created_at": _iso(case_row.created_at),
        },
        analysis_snapshot={
            "analysis_run_id": str(analysis.id),
            "pipeline_name": analysis.pipeline_name,
            "pipeline_version": analysis.pipeline_version,
            "status": analysis.status,
            "completed_at": _iso(analysis.completed_at),
        },
        policy_snapshot={
            "policy_evaluation_run_id": str(policy_run.id),
            "rule_set_id": str(rule_set.id),
            "rule_set_version": rule_set.rule_set_version,
            "rule_set_hash": rule_set.content_hash,
            "rule_set_source_type": rule_set.source_type,
            "as_of_date": policy_run.as_of_date.isoformat(),
            "summary_status": policy_run.summary_status,
            "policy_effects": cast(list[JsonValue], packet.policy_effects),
        },
        review_snapshot={
            "review_task_id": str(task.id),
            "task_type": task.task_type,
            "priority": task.priority,
            "task_version": task.version,
            "resolved_at": _iso(task.resolved_at),
            "packet_id": str(packet.id),
            "packet_schema_version": packet.packet_schema_version,
            "packet_hash": packet.packet_hash,
            "decision_id": str(decision.id),
            "decision_type": decision.decision_type,
            "reason_codes": cast(list[JsonValue], decision.reason_codes),
            "rationale": decision.rationale,
            "outcome_relation": decision.outcome_relation,
            "outcome_relation_rule_version": decision.outcome_relation_rule_version,
            "decided_by": str(decision.decided_by),
            "decided_at": _iso(decision.decided_at),
            "decision_schema_version": decision.decision_schema_version,
            "decision_hash": decision.content_hash,
            "basis": [
                {
                    "basis_type": row.basis_type,
                    "reference_id": row.reference_id,
                }
                for row in basis_rows
            ],
        },
        resolution_snapshot={
            "resolution_id": str(resolution.id),
            "status": resolution.status,
            "version": resolution.version,
            "mapping_name": resolution.mapping_name,
            "mapping_version": resolution.mapping_version,
            "resolution_schema_version": resolution.resolution_schema_version,
            "missing_fields": cast(list[JsonValue], resolution.missing_fields),
            "invalid_fields": cast(list[JsonValue], resolution.invalid_fields),
            "failure_code": resolution.failure_code,
            "terminal_event_id": str(terminal_event.id),
            "terminal_event_sequence": terminal_event.sequence,
            "terminal_event_type": terminal_event.event_type,
            "terminal_event_payload": cast(dict[str, JsonValue], terminal_event.payload),
            "terminal_event_at": generated_at.isoformat().replace("+00:00", "Z"),
        },
        dry_run_snapshot=_dry_run_snapshot(intent, result),
        qualification_snapshot=cast(dict[str, JsonValue], packet.qualification_snapshot),
        data_scope={
            "case_data_scope": "NOT_ATTESTED",
            "policy_source_type": rule_set.source_type,
            "qualification_source": "review_packet/1.0.0",
            "report_generation": "STRUCTURED_DATABASE_SNAPSHOT",
        },
        generated_at=generated_at,
    )
    return _add_review_report(session, report)


def _add_review_report(session: Session, report: ReviewReport) -> ReviewReportModel:
    model = ReviewReportModel(
        id=UUID(report.report_id),
        tenant_id=UUID(report.tenant_id),
        case_id=UUID(report.case_id),
        resolution_id=UUID(report.resolution_id),
        resolution_version=report.resolution_version,
        terminal_event_id=UUID(report.terminal_event_id),
        schema_version=report.schema_version,
        case_snapshot=report.case_snapshot,
        analysis_snapshot=report.analysis_snapshot,
        policy_snapshot=report.policy_snapshot,
        review_snapshot=report.review_snapshot,
        resolution_snapshot=report.resolution_snapshot,
        dry_run_snapshot=report.dry_run_snapshot,
        qualification_snapshot=report.qualification_snapshot,
        data_scope=report.data_scope,
        generated_at=report.generated_at,
        content_hash=report.content_hash,
    )
    session.add(model)
    session.flush()
    return model


def _create_degraded_review_report(
    session: Session,
    *,
    resolution: CaseResolutionModel,
    terminal_event: CaseResolutionEventModel,
    generated_at: datetime,
    source_failure: str,
) -> ReviewReportModel:
    """Persist a minimal failure snapshot without trusting corrupted source content."""

    report = ReviewReport.create(
        report_id=str(uuid4()),
        tenant_id=str(resolution.tenant_id),
        case_id=str(resolution.case_id),
        resolution_id=str(resolution.id),
        resolution_version=resolution.version,
        terminal_event_id=str(terminal_event.id),
        case_snapshot={
            "case_id": str(resolution.case_id),
            "source_integrity": "UNAVAILABLE",
        },
        analysis_snapshot={"source_integrity": "UNAVAILABLE"},
        policy_snapshot={"source_integrity": "UNAVAILABLE"},
        review_snapshot={
            "review_task_id": str(resolution.source_review_task_id),
            "decision_id": str(resolution.source_human_decision_id),
            "source_integrity": "FAILED",
            "source_failure": source_failure,
        },
        resolution_snapshot={
            "resolution_id": str(resolution.id),
            "status": resolution.status,
            "version": resolution.version,
            "mapping_name": resolution.mapping_name,
            "mapping_version": resolution.mapping_version,
            "resolution_schema_version": resolution.resolution_schema_version,
            "missing_fields": cast(list[JsonValue], resolution.missing_fields),
            "invalid_fields": cast(list[JsonValue], resolution.invalid_fields),
            "failure_code": resolution.failure_code,
            "terminal_event_id": str(terminal_event.id),
            "terminal_event_sequence": terminal_event.sequence,
            "terminal_event_type": terminal_event.event_type,
            "terminal_event_payload": cast(dict[str, JsonValue], terminal_event.payload),
            "terminal_event_at": generated_at.isoformat().replace("+00:00", "Z"),
        },
        dry_run_snapshot={"source_integrity": "UNAVAILABLE"},
        qualification_snapshot={"source_integrity": "UNAVAILABLE"},
        data_scope={
            "case_data_scope": "NOT_ATTESTED",
            "report_generation": "DEGRADED_INTEGRITY_FAILURE_SNAPSHOT",
            "source_content_included": False,
        },
        generated_at=generated_at,
    )
    return _add_review_report(session, report)


def _review_time_metric(session: Session, tenant_id: UUID) -> PocMetric:
    resolved_task_count = int(
        session.scalar(
            select(func.count(HumanReviewTaskModel.id)).where(
                HumanReviewTaskModel.tenant_id == tenant_id,
                HumanReviewTaskModel.status == "RESOLVED",
            )
        )
        or 0
    )
    seconds, interval_count = session.execute(
        select(
            func.coalesce(
                func.sum(
                    func.extract(
                        "epoch",
                        HumanReviewAssignmentModel.released_at
                        - HumanReviewAssignmentModel.assigned_at,
                    )
                ),
                0,
            ),
            func.count(HumanReviewAssignmentModel.id),
        )
        .join(
            HumanReviewTaskModel,
            and_(
                HumanReviewTaskModel.tenant_id == HumanReviewAssignmentModel.tenant_id,
                HumanReviewTaskModel.id == HumanReviewAssignmentModel.review_task_id,
            ),
        )
        .where(
            HumanReviewAssignmentModel.tenant_id == tenant_id,
            HumanReviewAssignmentModel.released_at.is_not(None),
            HumanReviewTaskModel.status == "RESOLVED",
        )
    ).one()
    return PocMetric.from_fraction(
        numerator=float(seconds or 0),
        denominator=resolved_task_count,
        sample_count=int(interval_count or 0),
        unit=MetricUnit.SECONDS,
    )


def _recommendation_difference_metric(session: Session, tenant_id: UUID) -> PocMetric:
    different, comparable = session.execute(
        select(
            func.count(HumanReviewDecisionModel.id).filter(
                HumanReviewDecisionModel.outcome_relation == "DIFFERS_FROM_RECOMMENDATION"
            ),
            func.count(HumanReviewDecisionModel.id).filter(
                HumanReviewDecisionModel.outcome_relation.in_(_COMPARABLE_RELATIONS)
            ),
        ).where(HumanReviewDecisionModel.tenant_id == tenant_id)
    ).one()
    denominator = int(comparable or 0)
    return PocMetric.from_fraction(
        numerator=float(different or 0),
        denominator=denominator,
        sample_count=denominator,
        unit=MetricUnit.RATIO,
    )


def _additional_evidence_metric(session: Session, tenant_id: UUID) -> PocMetric:
    task_count = int(
        session.scalar(
            select(func.count(HumanReviewTaskModel.id)).where(
                HumanReviewTaskModel.tenant_id == tenant_id
            )
        )
        or 0
    )
    requested_count = int(
        session.scalar(
            select(func.count(func.distinct(HumanReviewActionModel.review_task_id))).where(
                HumanReviewActionModel.tenant_id == tenant_id,
                HumanReviewActionModel.action_type == "EVIDENCE_REQUESTED",
            )
        )
        or 0
    )
    return PocMetric.from_fraction(
        numerator=float(requested_count),
        denominator=task_count,
        sample_count=task_count,
        unit=MetricUnit.RATIO,
    )


def _action_input_missing_metric(session: Session, tenant_id: UUID) -> PocMetric:
    needs_input, approvals = session.execute(
        select(
            func.count(CaseResolutionModel.id).filter(
                CaseResolutionModel.status == "ACTION_NEEDS_INPUT"
            ),
            func.count(CaseResolutionModel.id),
        )
        .join(
            HumanReviewDecisionModel,
            and_(
                HumanReviewDecisionModel.tenant_id == CaseResolutionModel.tenant_id,
                HumanReviewDecisionModel.id == CaseResolutionModel.source_human_decision_id,
            ),
        )
        .where(
            CaseResolutionModel.tenant_id == tenant_id,
            HumanReviewDecisionModel.decision_type.in_(_APPROVAL_DECISIONS),
        )
    ).one()
    denominator = int(approvals or 0)
    return PocMetric.from_fraction(
        numerator=float(needs_input or 0),
        denominator=denominator,
        sample_count=denominator,
        unit=MetricUnit.RATIO,
    )


def _dry_run_success_metric(session: Session, tenant_id: UUID) -> PocMetric:
    validated, terminal = session.execute(
        select(
            func.count(ExternalActionSimulationResultModel.id).filter(
                ExternalActionSimulationResultModel.outcome == "VALIDATED"
            ),
            func.count(ExternalActionSimulationResultModel.id).filter(
                ExternalActionSimulationResultModel.outcome.in_(("VALIDATED", "FAILED"))
            ),
        ).where(ExternalActionSimulationResultModel.tenant_id == tenant_id)
    ).one()
    denominator = int(terminal or 0)
    return PocMetric.from_fraction(
        numerator=float(validated or 0),
        denominator=denominator,
        sample_count=denominator,
        unit=MetricUnit.RATIO,
    )


def _analysis_terminal_metrics(session: Session, tenant_id: UUID) -> tuple[PocMetric, PocMetric]:
    failed, partial, terminal = session.execute(
        select(
            func.count(AnalysisRunModel.id).filter(AnalysisRunModel.status == "FAILED"),
            func.count(AnalysisRunModel.id).filter(AnalysisRunModel.status == "PARTIAL_SUCCESS"),
            func.count(AnalysisRunModel.id).filter(
                AnalysisRunModel.status.in_(_TERMINAL_ANALYSIS_STATUSES)
            ),
        ).where(AnalysisRunModel.tenant_id == tenant_id)
    ).one()
    denominator = int(terminal or 0)
    failure_metric = PocMetric.from_fraction(
        numerator=float(failed or 0),
        denominator=denominator,
        sample_count=denominator,
        unit=MetricUnit.RATIO,
    )
    partial_metric = PocMetric.from_fraction(
        numerator=float(partial or 0),
        denominator=denominator,
        sample_count=denominator,
        unit=MetricUnit.RATIO,
    )
    return failure_metric, partial_metric


def _dry_run_snapshot(
    intent: ExternalActionIntentModel | None,
    result: ExternalActionSimulationResultModel | None,
) -> dict[str, JsonValue]:
    intent_snapshot: dict[str, JsonValue] | None = None
    if intent is not None:
        intent_snapshot = {
            "intent_id": str(intent.id),
            "action_type": intent.action_type,
            "mode": intent.mode,
            "order_ref": intent.order_ref,
            "product_ref": intent.product_ref,
            "amount": _decimal(intent.amount),
            "currency": intent.currency,
            "quantity": intent.quantity,
            "shipping_address_ref": intent.shipping_address_ref,
            "mapping_name": intent.mapping_name,
            "mapping_version": intent.mapping_version,
            "intent_schema_version": intent.intent_schema_version,
            "content_hash": intent.content_hash,
        }
    result_snapshot: dict[str, JsonValue] | None = None
    if result is not None:
        result_snapshot = {
            "result_id": str(result.id),
            "simulation_attempt_id": str(result.simulation_attempt_id),
            "outcome": result.outcome,
            "mode": result.mode,
            "side_effects_performed": result.side_effects_performed,
            "failure_code": result.failure_code,
            "result_schema_version": result.result_schema_version,
            "content_hash": result.content_hash,
        }
    return {"intent": intent_snapshot, "result": result_snapshot}


def _verify_intent(row: ExternalActionIntentModel) -> None:
    try:
        intent = ExternalActionIntent.model_validate(
            {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "case_id": str(row.case_id),
                "resolution_id": str(row.resolution_id),
                "human_decision_id": str(row.human_decision_id),
                "action_type": row.action_type,
                "mode": row.mode,
                "order_ref": row.order_ref,
                "product_ref": row.product_ref,
                "amount": _decimal(row.amount),
                "currency": row.currency,
                "quantity": row.quantity,
                "shipping_address_ref": row.shipping_address_ref,
                "mapping_name": row.mapping_name,
                "mapping_version": row.mapping_version,
                "intent_schema_version": row.intent_schema_version,
                "content_hash": row.content_hash,
                "created_at": row.created_at,
            }
        )
    except ValidationError as error:
        raise CaseResolutionIntegrityError(
            "The immutable Action Intent shape failed Review Report verification."
        ) from error
    if canonical_hash(action_intent_hash_payload(intent)) != row.content_hash:
        raise CaseResolutionIntegrityError(
            "The immutable Action Intent failed Review Report verification."
        )


def _verify_result(row: ExternalActionSimulationResultModel) -> None:
    payload = {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "case_id": str(row.case_id),
        "resolution_id": str(row.resolution_id),
        "external_action_intent_id": str(row.external_action_intent_id),
        "simulation_attempt_id": str(row.simulation_attempt_id),
        "outcome": row.outcome,
        "mode": row.mode,
        "side_effects_performed": row.side_effects_performed,
        "failure_code": row.failure_code,
        "failure_message": row.failure_message,
        "simulated_request": row.simulated_request,
        "simulated_response": row.simulated_response,
        "result_schema_version": row.result_schema_version,
        "created_at": row.created_at.isoformat(),
    }
    if row.side_effects_performed or canonical_hash(payload) != row.content_hash:
        raise CaseResolutionIntegrityError(
            "The immutable simulation Result failed Review Report verification."
        )


def _to_review_report(row: ReviewReportModel) -> ReviewReport:
    return ReviewReport.model_validate(
        {
            "schema_version": row.schema_version,
            "report_id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "case_id": str(row.case_id),
            "resolution_id": str(row.resolution_id),
            "resolution_version": row.resolution_version,
            "terminal_event_id": str(row.terminal_event_id),
            "case_snapshot": row.case_snapshot,
            "analysis_snapshot": row.analysis_snapshot,
            "policy_snapshot": row.policy_snapshot,
            "review_snapshot": row.review_snapshot,
            "resolution_snapshot": row.resolution_snapshot,
            "dry_run_snapshot": row.dry_run_snapshot,
            "qualification_snapshot": row.qualification_snapshot,
            "data_scope": row.data_scope,
            "generated_at": row.generated_at,
            "content_hash": row.content_hash,
        }
    )


def _empty_summary() -> PocSummary:
    ratio = PocMetric.from_fraction(
        numerator=0,
        denominator=0,
        sample_count=0,
        unit=MetricUnit.RATIO,
    )
    review_time = PocMetric.from_fraction(
        numerator=0,
        denominator=0,
        sample_count=0,
        unit=MetricUnit.SECONDS,
    )
    return PocSummary(
        generated_at=datetime.now(UTC),
        review_time=review_time,
        recommendation_difference_rate=ratio,
        additional_evidence_request_rate=ratio,
        action_input_missing_rate=ratio,
        dry_run_success_rate=ratio,
        analysis_failure_rate=ratio,
        analysis_partial_success_rate=ratio,
    )


def _optional_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except (TypeError, ValueError):
        return None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("Review Report source timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware(value).isoformat().replace("+00:00", "Z")
    return value.isoformat()


def _decimal(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


__all__ = [
    "SQLAlchemyPocReportingRepository",
    "create_review_report_for_terminal_transition",
]
