"""PostgreSQL adapter for explicit privacy and Evidence lifecycle jobs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import TracebackType
from typing import Self, cast
from uuid import UUID, uuid5

from sqlalchemy import Engine, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.human_review import compute_human_decision_content_hash
from app.adapters.persistence.models import (
    AnalysisRunModel,
    AnalysisStageAttemptModel,
    AnalysisStageRunModel,
    CaseEvidenceModel,
    CaseModel,
    CaseResolutionModel,
    CaseSensitivePayloadModel,
    CustomerCommunicationSimulationModel,
    DataLifecycleEventModel,
    GroundedExplanationResultModel,
    GroundedExplanationRunModel,
    HumanReviewActionModel,
    HumanReviewDecisionBasisModel,
    HumanReviewDecisionModel,
    HumanReviewTaskModel,
    LLMExtractionResultModel,
    LLMExtractionResultV2Model,
    PolicyRetrievalRunModel,
    PolicyRetrievalRunQueryModel,
    ReviewReportModel,
)
from app.adapters.persistence.session import create_session_factory
from app.platform.case.models import JsonValue
from app.platform.evidence import EvidenceUploadStatus
from app.platform.poc_reporting import ReviewReport, canonical_json_hash
from app.platform.privacy_lifecycle import (
    EVIDENCE_LIFECYCLE_POLICY_VERSION,
    PURGED_CUSTOMER_MESSAGE,
    TERMINAL_CONTENT_REDACTION_POLICY_VERSION,
    EvidenceLifecyclePage,
    EvidenceLifecycleRecord,
    EvidencePurgeEventType,
    LifecycleMutationResult,
    LifecycleMutationStatus,
    SensitivePayloadLifecyclePage,
    SensitivePayloadLifecycleRecord,
)
from app.ports.privacy_lifecycle import PrivacyLifecycleRepository

_EVENT_NAMESPACE = UUID("db909b65-8cb6-4d25-8f4b-a5954e914b02")
_PURGED_GROUNDING_METRICS: dict[str, object] = {
    "statement_count": 0,
    "cited_statement_count": 0,
    "citation_reference_count": 0,
    "unique_citation_count": 0,
    "citation_coverage_rate": 0.0,
    "citation_id_valid_rate": 0.0,
    "citation_allowlist_violation_count": 0,
    "unknown_citation_count": 0,
    "duplicate_citation_count": 0,
    "forbidden_decision_count": 0,
}


def _uuid(value: str) -> UUID:
    return UUID(value)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("lifecycle timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _sensitive_record(model: CaseSensitivePayloadModel) -> SensitivePayloadLifecycleRecord:
    return SensitivePayloadLifecycleRecord(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        case_id=str(model.case_id),
        payload_sha256=model.payload_sha256,
        retention_policy_version=model.retention_policy_version,
        expires_at=model.expires_at,
    )


def _evidence_record(model: CaseEvidenceModel) -> EvidenceLifecycleRecord:
    return EvidenceLifecycleRecord(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        case_id=str(model.case_id),
        upload_status=EvidenceUploadStatus(model.upload_status),
        storage_bucket=model.storage_bucket,
        object_key=model.object_key,
        content_type=model.content_type,
        size_bytes=model.size_bytes,
        sha256=model.sha256,
        updated_at=model.updated_at,
    )


class SQLAlchemyPrivacyLifecycleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_expired_sensitive_payloads(
        self,
        *,
        tenant_id: str,
        expired_before: datetime,
        limit: int,
    ) -> SensitivePayloadLifecyclePage:
        _validate_limit(limit)
        rows = self._session.scalars(
            select(CaseSensitivePayloadModel)
            .where(
                CaseSensitivePayloadModel.tenant_id == _uuid(tenant_id),
                CaseSensitivePayloadModel.purged_at.is_(None),
                CaseSensitivePayloadModel.expires_at <= _utc(expired_before),
            )
            .order_by(
                CaseSensitivePayloadModel.expires_at,
                CaseSensitivePayloadModel.case_id,
            )
            .limit(limit + 1)
        ).all()
        return SensitivePayloadLifecyclePage(
            items=tuple(_sensitive_record(row) for row in rows[:limit]),
            truncated=len(rows) > limit,
        )

    def purge_sensitive_payload(
        self,
        *,
        candidate: SensitivePayloadLifecycleRecord,
        actor_id: str | None,
        correlation_id: str,
        occurred_at: datetime,
    ) -> LifecycleMutationResult:
        now = _utc(occurred_at)
        payload = self._session.scalar(
            select(CaseSensitivePayloadModel)
            .where(
                CaseSensitivePayloadModel.tenant_id == _uuid(candidate.tenant_id),
                CaseSensitivePayloadModel.case_id == _uuid(candidate.case_id),
                CaseSensitivePayloadModel.id == _uuid(candidate.id),
            )
            .with_for_update()
        )
        if payload is None or payload.purged_at is not None:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.ALREADY_APPLIED,
                reason="payload_already_purged",
            )
        if payload.expires_at > now or payload.expires_at != candidate.expires_at:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.BLOCKED,
                reason="payload_not_expired",
            )
        case = self._session.scalar(
            select(CaseModel)
            .where(
                CaseModel.tenant_id == payload.tenant_id,
                CaseModel.id == payload.case_id,
            )
            .with_for_update()
        )
        if case is None:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.BLOCKED,
                reason="case_missing",
            )
        message = payload.customer_message
        if message is None:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.BLOCKED,
                reason="active_payload_content_missing",
            )
        actual_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        if actual_hash != payload.payload_sha256 or actual_hash != candidate.payload_sha256:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.BLOCKED,
                reason="payload_digest_mismatch",
            )
        if case.customer_message != message:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.BLOCKED,
                reason="legacy_dual_write_mismatch",
            )

        redacted_counts = self._purge_analysis_text(
            tenant_id=payload.tenant_id,
            case_id=payload.case_id,
        )
        terminal_redaction = self._purge_terminal_content(
            tenant_id=payload.tenant_id,
            case_id=payload.case_id,
            case=case,
            purged_at=now,
        )

        operation_key = f"sensitive-purge:{payload.id}:{payload.expires_at.isoformat()}"
        inserted = self._append_event(
            event_type="SENSITIVE_PAYLOAD_PURGED",
            tenant_id=str(payload.tenant_id),
            case_id=str(payload.case_id),
            resource_type="CASE_SENSITIVE_PAYLOAD",
            resource_id=str(payload.id),
            retention_policy_version=payload.retention_policy_version,
            actor_id=actor_id,
            correlation_id=correlation_id,
            details={
                "outcome": "PURGED",
                "initiator": ("SYSTEM_RETENTION_SCHEDULER" if actor_id is None else "TENANT_ADMIN"),
                "pii_included": False,
                "legacy_copy_redacted": True,
                "analysis_text_redacted": True,
                "redacted_row_counts": redacted_counts,
                "terminal_content_redacted": True,
                "terminal_redaction_policy_version": (TERMINAL_CONTENT_REDACTION_POLICY_VERSION),
                **terminal_redaction,
            },
            operation_key=operation_key,
            occurred_at=now,
        )
        if not inserted:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.ALREADY_APPLIED,
                reason="purge_event_already_recorded",
            )
        payload.customer_message = None
        payload.purged_at = now
        payload.legacy_redacted_at = now
        payload.analysis_text_purged_at = now
        payload.terminal_content_purged_at = now
        payload.updated_at = now
        case.customer_message = PURGED_CUSTOMER_MESSAGE
        case.updated_at = now
        return LifecycleMutationResult(
            status=LifecycleMutationStatus.APPLIED,
            reason="payload_purged",
        )

    def _purge_terminal_content(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        case: CaseModel,
        purged_at: datetime,
    ) -> dict[str, object]:
        """Redact terminal free text and customer display snapshots, retaining lineage."""

        task_ids = select(HumanReviewTaskModel.id).where(
            HumanReviewTaskModel.tenant_id == tenant_id,
            HumanReviewTaskModel.case_id == case_id,
        )
        actions = tuple(
            self._session.scalars(
                select(HumanReviewActionModel).where(
                    HumanReviewActionModel.tenant_id == tenant_id,
                    HumanReviewActionModel.review_task_id.in_(task_ids),
                )
            )
        )
        decisions = tuple(
            self._session.scalars(
                select(HumanReviewDecisionModel).where(
                    HumanReviewDecisionModel.tenant_id == tenant_id,
                    HumanReviewDecisionModel.review_task_id.in_(task_ids),
                )
            )
        )
        hash_transitions: list[dict[str, str]] = []
        decision_hashes: dict[str, str] = {}

        for action in actions:
            if action.rationale is not None:
                action.rationale = PURGED_CUSTOMER_MESSAGE
            action.action_payload = {}

        for decision in decisions:
            basis_rows = tuple(
                self._session.scalars(
                    select(HumanReviewDecisionBasisModel).where(
                        HumanReviewDecisionBasisModel.tenant_id == tenant_id,
                        HumanReviewDecisionBasisModel.human_review_decision_id == decision.id,
                    )
                )
            )
            before_hash = decision.content_hash
            decision.rationale = PURGED_CUSTOMER_MESSAGE
            decision.content_hash = compute_human_decision_content_hash(decision, basis_rows)
            decision_hashes[str(decision.id)] = decision.content_hash
            hash_transitions.append(
                {
                    "resource_type": "HUMAN_REVIEW_DECISION",
                    "resource_id": str(decision.id),
                    "before_hash": before_hash,
                    "after_hash": decision.content_hash,
                }
            )

        reports = tuple(
            self._session.scalars(
                select(ReviewReportModel).where(
                    ReviewReportModel.tenant_id == tenant_id,
                    ReviewReportModel.case_id == case_id,
                )
            )
        )
        for report in reports:
            before_hash = report.content_hash
            redacted = _redacted_review_report(
                report,
                purged_at=purged_at,
                decision_hashes=decision_hashes,
            )
            report.case_snapshot = cast(dict[str, object], redacted.case_snapshot)
            report.analysis_snapshot = cast(dict[str, object], redacted.analysis_snapshot)
            report.policy_snapshot = cast(dict[str, object], redacted.policy_snapshot)
            report.review_snapshot = cast(dict[str, object], redacted.review_snapshot)
            report.resolution_snapshot = cast(dict[str, object], redacted.resolution_snapshot)
            report.dry_run_snapshot = cast(dict[str, object], redacted.dry_run_snapshot)
            report.qualification_snapshot = cast(dict[str, object], redacted.qualification_snapshot)
            report.data_scope = cast(dict[str, object], redacted.data_scope)
            report.content_hash = redacted.content_hash
            hash_transitions.append(
                {
                    "resource_type": "REVIEW_REPORT",
                    "resource_id": str(report.id),
                    "before_hash": before_hash,
                    "after_hash": report.content_hash,
                }
            )

        communications = tuple(
            self._session.scalars(
                select(CustomerCommunicationSimulationModel).where(
                    CustomerCommunicationSimulationModel.tenant_id == tenant_id,
                    CustomerCommunicationSimulationModel.case_id == case_id,
                )
            )
        )
        for communication in communications:
            before_hash = communication.content_hash
            communication.recipient_label = PURGED_CUSTOMER_MESSAGE
            communication.subject = PURGED_CUSTOMER_MESSAGE
            communication.body = PURGED_CUSTOMER_MESSAGE
            communication.content_hash = _communication_content_hash(communication)
            hash_transitions.append(
                {
                    "resource_type": "CUSTOMER_COMMUNICATION_SIMULATION",
                    "resource_id": str(communication.id),
                    "before_hash": before_hash,
                    "after_hash": communication.content_hash,
                }
            )

        resolution_result = self._session.execute(
            update(CaseResolutionModel)
            .where(
                CaseResolutionModel.tenant_id == tenant_id,
                CaseResolutionModel.case_id == case_id,
                CaseResolutionModel.failure_message.is_not(None),
            )
            .values(failure_message=PURGED_CUSTOMER_MESSAGE),
            execution_options={"synchronize_session": False},
        )
        resolution_count = getattr(resolution_result, "rowcount", 0)

        case.attributes = {}
        ordered_transitions = sorted(
            hash_transitions,
            key=lambda item: (item["resource_type"], item["resource_id"]),
        )
        receipt = json.dumps(
            ordered_transitions,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "terminal_redacted_row_counts": {
                "case_attributes": 1,
                "human_review_actions": len(actions),
                "human_review_decisions": len(decisions),
                "review_reports": len(reports),
                "customer_communications": len(communications),
                "case_resolution_failures": max(0, int(resolution_count or 0)),
            },
            "content_hash_transitions": ordered_transitions,
            "terminal_redaction_receipt_sha256": hashlib.sha256(
                receipt.encode("utf-8")
            ).hexdigest(),
        }

    def _purge_analysis_text(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
    ) -> dict[str, int]:
        """Redact customer-derived model prose while retaining run/version lineage."""

        analysis_ids = select(AnalysisRunModel.id).where(
            AnalysisRunModel.tenant_id == tenant_id,
            AnalysisRunModel.case_id == case_id,
        )
        retrieval_ids = select(PolicyRetrievalRunModel.id).where(
            PolicyRetrievalRunModel.tenant_id == tenant_id,
            PolicyRetrievalRunModel.case_id == case_id,
        )
        grounding_ids = select(GroundedExplanationRunModel.id).where(
            GroundedExplanationRunModel.tenant_id == tenant_id,
            GroundedExplanationRunModel.case_id == case_id,
        )

        statements = {
            "llm_v1": update(LLMExtractionResultModel)
            .where(
                LLMExtractionResultModel.tenant_id == tenant_id,
                LLMExtractionResultModel.analysis_run_id.in_(analysis_ids),
            )
            .values(
                claims=[],
                missing_information=[],
                summary=PURGED_CUSTOMER_MESSAGE,
            ),
            "llm_v2": update(LLMExtractionResultV2Model)
            .where(
                LLMExtractionResultV2Model.tenant_id == tenant_id,
                LLMExtractionResultV2Model.analysis_run_id.in_(analysis_ids),
            )
            .values(
                claims=[],
                requested_actions=[],
                text_ambiguities=[],
                summary=PURGED_CUSTOMER_MESSAGE,
                system_missing_information=[],
            ),
            "generated_queries": update(PolicyRetrievalRunQueryModel)
            .where(
                PolicyRetrievalRunQueryModel.tenant_id == tenant_id,
                PolicyRetrievalRunQueryModel.retrieval_run_id.in_(retrieval_ids),
                PolicyRetrievalRunQueryModel.query_source == "GENERATED",
            )
            .values(query_text=PURGED_CUSTOMER_MESSAGE),
            "grounded_results": update(GroundedExplanationResultModel)
            .where(
                GroundedExplanationResultModel.tenant_id == tenant_id,
                GroundedExplanationResultModel.grounded_explanation_run_id.in_(grounding_ids),
            )
            .values(
                policy_statements=[],
                unresolved_conditions=[],
                validation_metrics=_PURGED_GROUNDING_METRICS,
            ),
            "analysis_runs": update(AnalysisRunModel)
            .where(
                AnalysisRunModel.tenant_id == tenant_id,
                AnalysisRunModel.case_id == case_id,
                AnalysisRunModel.failure_message.is_not(None),
            )
            .values(failure_message=PURGED_CUSTOMER_MESSAGE),
            "analysis_stages": update(AnalysisStageRunModel)
            .where(
                AnalysisStageRunModel.tenant_id == tenant_id,
                AnalysisStageRunModel.analysis_run_id.in_(analysis_ids),
                AnalysisStageRunModel.failure_message.is_not(None),
            )
            .values(failure_message=PURGED_CUSTOMER_MESSAGE),
            "analysis_attempts": update(AnalysisStageAttemptModel)
            .where(
                AnalysisStageAttemptModel.tenant_id == tenant_id,
                AnalysisStageAttemptModel.analysis_run_id.in_(analysis_ids),
                AnalysisStageAttemptModel.failure_message.is_not(None),
            )
            .values(failure_message=PURGED_CUSTOMER_MESSAGE),
            "retrieval_runs": update(PolicyRetrievalRunModel)
            .where(
                PolicyRetrievalRunModel.tenant_id == tenant_id,
                PolicyRetrievalRunModel.case_id == case_id,
                PolicyRetrievalRunModel.failure_message.is_not(None),
            )
            .values(failure_message=PURGED_CUSTOMER_MESSAGE),
            "grounding_runs": update(GroundedExplanationRunModel)
            .where(
                GroundedExplanationRunModel.tenant_id == tenant_id,
                GroundedExplanationRunModel.case_id == case_id,
                GroundedExplanationRunModel.failure_message.is_not(None),
            )
            .values(failure_message=PURGED_CUSTOMER_MESSAGE),
        }
        counts: dict[str, int] = {}
        for name, statement in statements.items():
            result = self._session.execute(
                statement,
                execution_options={"synchronize_session": False},
            )
            row_count = getattr(result, "rowcount", 0)
            counts[name] = max(0, int(row_count or 0))
        return counts

    def list_evidence_for_reconciliation(
        self,
        *,
        tenant_id: str,
        stale_pending_before: datetime,
        limit: int,
    ) -> EvidenceLifecyclePage:
        _validate_limit(limit)
        rows = self._session.scalars(
            select(CaseEvidenceModel)
            .where(
                CaseEvidenceModel.tenant_id == _uuid(tenant_id),
                or_(
                    CaseEvidenceModel.upload_status != EvidenceUploadStatus.PENDING.value,
                    CaseEvidenceModel.updated_at <= _utc(stale_pending_before),
                ),
            )
            .order_by(CaseEvidenceModel.updated_at, CaseEvidenceModel.id)
            .limit(limit + 1)
        ).all()
        return EvidenceLifecyclePage(
            items=tuple(_evidence_record(row) for row in rows[:limit]),
            truncated=len(rows) > limit,
        )

    def get_evidence_by_object_key(
        self,
        *,
        tenant_id: str,
        object_key: str,
    ) -> EvidenceLifecycleRecord | None:
        model = self._session.scalar(
            select(CaseEvidenceModel).where(
                CaseEvidenceModel.tenant_id == _uuid(tenant_id),
                CaseEvidenceModel.object_key == object_key,
            )
        )
        return _evidence_record(model) if model is not None else None

    def case_exists(self, *, tenant_id: str, case_id: str) -> bool:
        return (
            self._session.scalar(
                select(CaseModel.id).where(
                    CaseModel.tenant_id == _uuid(tenant_id),
                    CaseModel.id == _uuid(case_id),
                )
            )
            is not None
        )

    def reconcile_evidence_status(
        self,
        *,
        record: EvidenceLifecycleRecord,
        target_status: EvidenceUploadStatus,
        reason: str,
        actor_id: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> LifecycleMutationResult:
        row = self._session.scalar(
            select(CaseEvidenceModel)
            .where(
                CaseEvidenceModel.tenant_id == _uuid(record.tenant_id),
                CaseEvidenceModel.case_id == _uuid(record.case_id),
                CaseEvidenceModel.id == _uuid(record.id),
            )
            .with_for_update()
        )
        if row is None:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.BLOCKED,
                reason="evidence_missing",
            )
        if row.upload_status == target_status.value:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.ALREADY_APPLIED,
                reason="evidence_status_already_reconciled",
            )
        if row.upload_status != record.upload_status.value or row.updated_at != record.updated_at:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.BLOCKED,
                reason="evidence_changed_during_scan",
            )
        allowed = {
            (EvidenceUploadStatus.PENDING, EvidenceUploadStatus.AVAILABLE),
            (EvidenceUploadStatus.PENDING, EvidenceUploadStatus.FAILED),
            (EvidenceUploadStatus.AVAILABLE, EvidenceUploadStatus.FAILED),
        }
        if (record.upload_status, target_status) not in allowed:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.BLOCKED,
                reason="evidence_transition_not_allowed",
            )
        now = _utc(occurred_at)
        operation_key = (
            f"evidence-reconcile:{record.id}:{record.updated_at.isoformat()}:"
            f"{record.upload_status.value}:{target_status.value}"
        )
        inserted = self._append_event(
            event_type="EVIDENCE_RECONCILED",
            tenant_id=record.tenant_id,
            case_id=record.case_id,
            resource_type="EVIDENCE",
            resource_id=record.id,
            retention_policy_version=EVIDENCE_LIFECYCLE_POLICY_VERSION,
            actor_id=actor_id,
            correlation_id=correlation_id,
            details={
                "reason": reason,
                "from_status": record.upload_status.value,
                "to_status": target_status.value,
                "pii_included": False,
            },
            operation_key=operation_key,
            occurred_at=now,
        )
        if not inserted:
            return LifecycleMutationResult(
                status=LifecycleMutationStatus.ALREADY_APPLIED,
                reason="reconciliation_event_already_recorded",
            )
        row.upload_status = target_status.value
        row.updated_at = now
        return LifecycleMutationResult(
            status=LifecycleMutationStatus.APPLIED,
            reason="evidence_status_reconciled",
        )

    def record_evidence_purge_event(
        self,
        *,
        event_type: EvidencePurgeEventType,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
        reason: str,
        operation_key: str,
        actor_id: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> bool:
        return self._append_event(
            event_type=event_type.value,
            tenant_id=tenant_id,
            case_id=case_id,
            resource_type="EVIDENCE",
            resource_id=evidence_id,
            retention_policy_version=EVIDENCE_LIFECYCLE_POLICY_VERSION,
            actor_id=actor_id,
            correlation_id=correlation_id,
            details={
                "reason": reason,
                "outcome": (
                    "DELETE_REQUESTED"
                    if event_type is EvidencePurgeEventType.REQUESTED
                    else "DELETED"
                ),
                "pii_included": False,
            },
            operation_key=operation_key,
            occurred_at=_utc(occurred_at),
        )

    def _append_event(
        self,
        *,
        event_type: str,
        tenant_id: str,
        case_id: str,
        resource_type: str,
        resource_id: str,
        retention_policy_version: str,
        actor_id: str | None,
        correlation_id: str,
        details: dict[str, object],
        operation_key: str,
        occurred_at: datetime,
    ) -> bool:
        if len(operation_key) > 255:
            operation_key = hashlib.sha256(operation_key.encode("utf-8")).hexdigest()
        canonical = {
            "event_type": event_type,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "retention_policy_version": retention_policy_version,
            "details": details,
            "operation_key": operation_key,
            "occurred_at": occurred_at.isoformat(),
        }
        content_hash = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        event_id = uuid5(_EVENT_NAMESPACE, f"{tenant_id}:{operation_key}")
        statement = (
            postgresql_insert(DataLifecycleEventModel)
            .values(
                id=event_id,
                tenant_id=_uuid(tenant_id),
                case_id=_uuid(case_id),
                schema_version="data_lifecycle_event/1.0.0",
                event_type=event_type,
                resource_type=resource_type,
                resource_id=_uuid(resource_id),
                retention_policy_version=retention_policy_version,
                actor_id=_uuid(actor_id) if actor_id is not None else None,
                correlation_id=_uuid(correlation_id),
                details=details,
                occurred_at=occurred_at,
                content_hash=content_hash,
                operation_key=operation_key,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    DataLifecycleEventModel.tenant_id,
                    DataLifecycleEventModel.operation_key,
                ],
                index_where=DataLifecycleEventModel.operation_key.is_not(None),
            )
            .returning(DataLifecycleEventModel.id)
        )
        return self._session.scalar(statement) is not None


def _redacted_review_report(
    row: ReviewReportModel,
    *,
    purged_at: datetime,
    decision_hashes: dict[str, str],
) -> ReviewReport:
    case_snapshot = _allowlisted_record(
        row.case_snapshot,
        ("case_id", "status", "product_ref", "requested_action", "created_at", "source_integrity"),
    )
    case_snapshot["privacy_redacted_at"] = _iso(purged_at)

    review_snapshot = dict(row.review_snapshot)
    if "rationale" in review_snapshot:
        review_snapshot["rationale"] = PURGED_CUSTOMER_MESSAGE
    decision_id = review_snapshot.get("decision_id")
    if isinstance(decision_id, str) and decision_id in decision_hashes:
        review_snapshot["decision_hash"] = decision_hashes[decision_id]
    review_snapshot["privacy_redacted_at"] = _iso(purged_at)

    resolution_snapshot = dict(row.resolution_snapshot)
    if "terminal_event_payload" in resolution_snapshot:
        resolution_snapshot["terminal_event_payload"] = {"privacy_redacted": True}
    resolution_snapshot["privacy_redacted_at"] = _iso(purged_at)

    data_scope = dict(row.data_scope)
    data_scope.update(
        {
            "commerce_context_included": False,
            "direct_contact_values_included": False,
            "privacy_redacted": True,
            "privacy_redaction_policy_version": TERMINAL_CONTENT_REDACTION_POLICY_VERSION,
            "retained_transaction_fields": ["product_ref"],
        }
    )
    return ReviewReport.create(
        report_id=str(row.id),
        tenant_id=str(row.tenant_id),
        case_id=str(row.case_id),
        resolution_id=str(row.resolution_id),
        resolution_version=row.resolution_version,
        terminal_event_id=str(row.terminal_event_id),
        case_snapshot=cast(dict[str, JsonValue], case_snapshot),
        analysis_snapshot=cast(dict[str, JsonValue], row.analysis_snapshot),
        policy_snapshot=cast(dict[str, JsonValue], row.policy_snapshot),
        review_snapshot=cast(dict[str, JsonValue], review_snapshot),
        resolution_snapshot=cast(dict[str, JsonValue], resolution_snapshot),
        dry_run_snapshot=cast(
            dict[str, JsonValue],
            _redacted_dry_run_snapshot(row.dry_run_snapshot, purged_at=purged_at),
        ),
        qualification_snapshot=cast(dict[str, JsonValue], row.qualification_snapshot),
        data_scope=cast(dict[str, JsonValue], data_scope),
        generated_at=row.generated_at,
    )


def _redacted_dry_run_snapshot(
    value: dict[str, object],
    *,
    purged_at: datetime,
) -> dict[str, object]:
    intent = value.get("intent")
    result = value.get("result")
    redacted: dict[str, object] = {
        "privacy_redacted": True,
        "privacy_redacted_at": _iso(purged_at),
    }
    if isinstance(intent, dict):
        redacted["intent"] = _allowlisted_record(
            intent,
            (
                "action_type",
                "amount",
                "currency",
                "intent_id",
                "intent_schema_version",
                "mapping_name",
                "mapping_version",
                "mode",
                "product_ref",
                "quantity",
            ),
        )
    else:
        redacted["intent"] = None
    if isinstance(result, dict):
        redacted["result"] = _allowlisted_record(
            result,
            (
                "failure_code",
                "mode",
                "outcome",
                "result_id",
                "result_schema_version",
                "side_effects_performed",
                "simulation_attempt_id",
            ),
        )
    else:
        redacted["result"] = None
    return redacted


def _allowlisted_record(value: dict[str, object], keys: tuple[str, ...]) -> dict[str, object]:
    return {key: value[key] for key in keys if key in value}


def _communication_content_hash(row: CustomerCommunicationSimulationModel) -> str:
    return canonical_json_hash(
        {
            "schema_version": row.schema_version,
            "communication_id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "case_id": str(row.case_id),
            "review_report_id": str(row.review_report_id),
            "channel": row.channel,
            "template_name": row.template_name,
            "template_version": row.template_version,
            "recipient_label": row.recipient_label,
            "subject": row.subject,
            "body": row.body,
            "delivery_status": row.delivery_status,
            "side_effects_performed": row.side_effects_performed,
            "created_by": str(row.created_by),
            "created_at": _iso(row.created_at),
        }
    )


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


class SQLAlchemyPrivacyLifecycleUnitOfWork:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.lifecycle: PrivacyLifecycleRepository = SQLAlchemyPrivacyLifecycleRepository(session)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback
        try:
            self.rollback()
        finally:
            self._session.close()

    def flush(self) -> None:
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


class SQLAlchemyPrivacyLifecycleUnitOfWorkFactory:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SQLAlchemyPrivacyLifecycleUnitOfWork:
        return SQLAlchemyPrivacyLifecycleUnitOfWork(self._session_factory())


def create_privacy_lifecycle_unit_of_work_factory(
    engine: Engine,
) -> SQLAlchemyPrivacyLifecycleUnitOfWorkFactory:
    return SQLAlchemyPrivacyLifecycleUnitOfWorkFactory(create_session_factory(engine))


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 5000:
        raise ValueError("lifecycle batch limit must be between 1 and 5000")


__all__ = [
    "SQLAlchemyPrivacyLifecycleRepository",
    "SQLAlchemyPrivacyLifecycleUnitOfWork",
    "SQLAlchemyPrivacyLifecycleUnitOfWorkFactory",
    "create_privacy_lifecycle_unit_of_work_factory",
]
