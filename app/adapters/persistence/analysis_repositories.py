"""Tenant-scoped SQLAlchemy repositories for Sprint 2 analysis workflows."""

from datetime import datetime
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.adapters.persistence.models import (
    AnalysisRequestIdempotencyRecordModel,
    AnalysisRunEvidenceModel,
    AnalysisRunModel,
    AnalysisStageAttemptModel,
    AnalysisStageRunModel,
    LLMExtractionResultModel,
    LLMExtractionResultV2Model,
    OutboxEventModel,
    VisionAnalysisResultModel,
    VisionDetectionModel,
    VisionImageAssessmentModel,
)
from app.platform.analysis.enums import (
    AnalysisAttemptStatus,
    AnalysisRunStatus,
    AnalysisStageStatus,
    CoordinateSystem,
    DefectType,
    OutboxStatus,
    require_run_transition,
    require_stage_transition,
)
from app.platform.analysis.llm_v2 import (
    CompletenessResult,
    LLMExtractionResultV2Record,
    LLMTextExtractionResultV2,
)
from app.platform.analysis.models import (
    AnalysisFailure,
    AnalysisRequestIdempotencyRecord,
    AnalysisRun,
    AnalysisStageAttempt,
    AnalysisStageRun,
    OutboxEvent,
    ProviderExecutionMetadata,
)
from app.platform.analysis.schemas import (
    AnalysisEvidenceSnapshot,
    BoundingBox,
    DetectionFinding,
    ImageQualityResult,
    LLMExtractionResultRecord,
    LLMTextExtractionResult,
    VisionAnalysisResult,
    VisionAnalysisResultRecord,
    VisionImageAssessment,
)
from app.platform.errors import InconsistentPersistenceStateError
from app.ports.analysis_repository import (
    AnalysisAdmissionCounts,
    AnalysisRequestIdempotencyClaim,
    AnalysisRunListCriteria,
)


def _required_uuid(value: str) -> UUID:
    return UUID(value)


def _optional_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _require_tenant_scope(*, tenant_id: str, entity_tenant_id: str) -> UUID:
    tenant_uuid = _required_uuid(tenant_id)
    if tenant_uuid != _required_uuid(entity_tenant_id):
        raise ValueError("entity tenant_id does not match the repository tenant scope")
    return tenant_uuid


def _failure_values(failure: AnalysisFailure | None) -> dict[str, object]:
    if failure is None:
        return {
            "failure_code": None,
            "failure_message": None,
            "failure_retryable": None,
        }
    return {
        "failure_code": failure.code,
        "failure_message": failure.message,
        "failure_retryable": failure.retryable,
    }


def _failure_from_columns(
    *,
    code: str | None,
    message: str | None,
    retryable: bool | None,
) -> AnalysisFailure | None:
    if code is None:
        return None
    if message is None or retryable is None:
        raise InconsistentPersistenceStateError("Persisted analysis failure fields are incomplete.")
    return AnalysisFailure(code=code, message=message, retryable=retryable)


def _provider_values(
    provider: ProviderExecutionMetadata | None,
) -> dict[str, object]:
    if provider is None:
        return {
            "execution_provider_name": None,
            "execution_model_name": None,
            "execution_model_version": None,
            "execution_model_revision": None,
            "provider_request_id": None,
            "input_token_count": None,
            "output_token_count": None,
            "latency_ms": None,
        }
    return {
        "execution_provider_name": provider.provider_name,
        "execution_model_name": provider.model_name,
        "execution_model_version": provider.model_version,
        "execution_model_revision": provider.model_revision,
        "provider_request_id": provider.provider_request_id,
        "input_token_count": provider.input_token_count,
        "output_token_count": provider.output_token_count,
        "latency_ms": provider.latency_ms,
    }


def _provider_from_model(
    model: AnalysisStageRunModel | AnalysisStageAttemptModel,
) -> ProviderExecutionMetadata | None:
    if model.execution_provider_name is None:
        return None
    if (
        model.execution_model_name is None
        or model.execution_model_version is None
        or model.latency_ms is None
    ):
        raise InconsistentPersistenceStateError(
            "Persisted provider execution fields are incomplete."
        )
    return ProviderExecutionMetadata(
        provider_name=model.execution_provider_name,
        model_name=model.execution_model_name,
        model_version=model.execution_model_version,
        model_revision=model.execution_model_revision,
        provider_request_id=model.provider_request_id,
        input_token_count=model.input_token_count,
        output_token_count=model.output_token_count,
        latency_ms=model.latency_ms,
    )


def analysis_run_model_from_entity(run: AnalysisRun) -> AnalysisRunModel:
    return AnalysisRunModel(
        id=_required_uuid(run.id),
        tenant_id=_required_uuid(run.tenant_id),
        case_id=_required_uuid(run.case_id),
        pipeline_name=run.pipeline.value,
        pipeline_version=run.pipeline_version,
        execution_mode=run.execution_mode.value,
        trigger_type=run.trigger.value,
        status=run.status.value,
        requested_by=_required_uuid(run.requested_by),
        correlation_id=run.correlation_id,
        idempotency_key=run.idempotency_key,
        request_hash=run.request_hash,
        requested_at=run.requested_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        **_failure_values(run.failure),
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def analysis_run_entity_from_model(model: AnalysisRunModel) -> AnalysisRun:
    return AnalysisRun.model_validate(
        {
            "id": str(model.id),
            "tenant_id": str(model.tenant_id),
            "case_id": str(model.case_id),
            "pipeline": model.pipeline_name,
            "pipeline_version": model.pipeline_version,
            "execution_mode": model.execution_mode,
            "trigger": model.trigger_type,
            "status": model.status,
            "requested_by": str(model.requested_by),
            "correlation_id": model.correlation_id,
            "idempotency_key": model.idempotency_key,
            "request_hash": model.request_hash,
            "requested_at": model.requested_at,
            "started_at": model.started_at,
            "completed_at": model.completed_at,
            "failure": _failure_from_columns(
                code=model.failure_code,
                message=model.failure_message,
                retryable=model.failure_retryable,
            ),
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


def stage_run_model_from_entity(stage: AnalysisStageRun) -> AnalysisStageRunModel:
    return AnalysisStageRunModel(
        id=_required_uuid(stage.id),
        tenant_id=_required_uuid(stage.tenant_id),
        analysis_run_id=_required_uuid(stage.analysis_run_id),
        model_route_plan_id=(
            _required_uuid(stage.model_route_plan_id)
            if stage.model_route_plan_id is not None
            else None
        ),
        stage_type=stage.stage_type.value,
        status=stage.status.value,
        attempt_count=stage.attempt_summary.attempt_count,
        provider_name=stage.provider_name,
        model_name=stage.model_name,
        model_version=stage.model_version,
        model_revision=stage.model_revision,
        prompt_name=stage.prompt_name,
        prompt_version=stage.prompt_version,
        prompt_content_hash=stage.prompt_content_hash,
        input_schema_version=stage.input_schema_version,
        output_schema_version=stage.output_schema_version,
        **_provider_values(stage.provider_execution),
        claim_token=_required_uuid(stage.claim_token) if stage.claim_token is not None else None,
        lease_expires_at=stage.claim_expires_at,
        next_attempt_at=stage.next_attempt_at,
        last_attempt_started_at=stage.attempt_summary.last_attempt_started_at,
        last_attempt_completed_at=stage.attempt_summary.last_attempt_completed_at,
        started_at=stage.started_at,
        completed_at=stage.completed_at,
        **_failure_values(stage.failure),
        created_at=stage.created_at,
        updated_at=stage.updated_at,
    )


def stage_run_entity_from_model(model: AnalysisStageRunModel) -> AnalysisStageRun:
    return AnalysisStageRun.model_validate(
        {
            "id": str(model.id),
            "tenant_id": str(model.tenant_id),
            "analysis_run_id": str(model.analysis_run_id),
            "model_route_plan_id": (
                str(model.model_route_plan_id) if model.model_route_plan_id is not None else None
            ),
            "stage_type": model.stage_type,
            "status": model.status,
            "attempt_summary": {
                "attempt_count": model.attempt_count,
                "last_attempt_started_at": model.last_attempt_started_at,
                "last_attempt_completed_at": model.last_attempt_completed_at,
            },
            "provider_name": model.provider_name,
            "model_name": model.model_name,
            "model_version": model.model_version,
            "model_revision": model.model_revision,
            "provider_execution": _provider_from_model(model),
            "prompt_name": model.prompt_name,
            "prompt_version": model.prompt_version,
            "prompt_content_hash": model.prompt_content_hash,
            "input_schema_version": model.input_schema_version,
            "output_schema_version": model.output_schema_version,
            "claim_token": str(model.claim_token) if model.claim_token is not None else None,
            "claim_expires_at": model.lease_expires_at,
            "next_attempt_at": model.next_attempt_at,
            "started_at": model.started_at,
            "completed_at": model.completed_at,
            "failure": _failure_from_columns(
                code=model.failure_code,
                message=model.failure_message,
                retryable=model.failure_retryable,
            ),
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


def attempt_model_from_entity(attempt: AnalysisStageAttempt) -> AnalysisStageAttemptModel:
    return AnalysisStageAttemptModel(
        id=_required_uuid(attempt.id),
        tenant_id=_required_uuid(attempt.tenant_id),
        analysis_run_id=_required_uuid(attempt.analysis_run_id),
        stage_run_id=_required_uuid(attempt.stage_run_id),
        attempt_number=attempt.attempt_number,
        execution_token=_required_uuid(attempt.claim_token),
        status=attempt.status.value,
        provider_name=attempt.provider_name,
        model_name=attempt.model_name,
        model_version=attempt.model_version,
        model_revision=attempt.model_revision,
        prompt_name=attempt.prompt_name,
        prompt_version=attempt.prompt_version,
        prompt_content_hash=attempt.prompt_content_hash,
        input_schema_version=attempt.input_schema_version,
        output_schema_version=attempt.output_schema_version,
        **_provider_values(attempt.provider_execution),
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        **_failure_values(attempt.failure),
        created_at=attempt.created_at,
    )


def attempt_entity_from_model(model: AnalysisStageAttemptModel) -> AnalysisStageAttempt:
    return AnalysisStageAttempt.model_validate(
        {
            "id": str(model.id),
            "tenant_id": str(model.tenant_id),
            "analysis_run_id": str(model.analysis_run_id),
            "stage_run_id": str(model.stage_run_id),
            "attempt_number": model.attempt_number,
            "status": model.status,
            "claim_token": str(model.execution_token),
            "provider_name": model.provider_name,
            "model_name": model.model_name,
            "model_version": model.model_version,
            "model_revision": model.model_revision,
            "prompt_name": model.prompt_name,
            "prompt_version": model.prompt_version,
            "prompt_content_hash": model.prompt_content_hash,
            "input_schema_version": model.input_schema_version,
            "output_schema_version": model.output_schema_version,
            "provider_execution": _provider_from_model(model),
            "started_at": model.started_at,
            "completed_at": model.completed_at,
            "failure": _failure_from_columns(
                code=model.failure_code,
                message=model.failure_message,
                retryable=model.failure_retryable,
            ),
            "created_at": model.created_at,
        }
    )


def result_model_from_entity(result: LLMExtractionResultRecord) -> LLMExtractionResultModel:
    value = result.result.model_dump(mode="json")
    return LLMExtractionResultModel(
        id=_required_uuid(result.id),
        tenant_id=_required_uuid(result.tenant_id),
        analysis_run_id=_required_uuid(result.analysis_run_id),
        stage_run_id=_required_uuid(result.stage_run_id),
        stage_type="TEXT_EXTRACTION",
        schema_version=cast(str, value["schema_version"]),
        language=cast(str, value["language"]),
        issue_types=cast(list[object], value["issue_types"]),
        claims=cast(list[object], value["claims"]),
        requested_action=cast(str, value["requested_action"]),
        missing_information=cast(list[object], value["missing_information"]),
        summary=cast(str, value["summary"]),
        created_at=result.created_at,
    )


def result_entity_from_model(model: LLMExtractionResultModel) -> LLMExtractionResultRecord:
    return LLMExtractionResultRecord(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        analysis_run_id=str(model.analysis_run_id),
        stage_run_id=str(model.stage_run_id),
        result=LLMTextExtractionResult.model_validate(
            {
                "schema_version": model.schema_version,
                "language": model.language,
                "issue_types": model.issue_types,
                "claims": model.claims,
                "requested_action": model.requested_action,
                "missing_information": model.missing_information,
                "summary": model.summary,
            }
        ),
        created_at=model.created_at,
    )


def evidence_snapshot_model_from_entity(
    snapshot: AnalysisEvidenceSnapshot,
) -> AnalysisRunEvidenceModel:
    return AnalysisRunEvidenceModel(
        id=_required_uuid(snapshot.id),
        tenant_id=_required_uuid(snapshot.tenant_id),
        analysis_run_id=_required_uuid(snapshot.analysis_run_id),
        evidence_id=_required_uuid(snapshot.evidence_id),
        position=snapshot.position,
        sha256=snapshot.sha256,
        created_at=snapshot.created_at,
    )


def evidence_snapshot_entity_from_model(
    model: AnalysisRunEvidenceModel,
) -> AnalysisEvidenceSnapshot:
    return AnalysisEvidenceSnapshot(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        analysis_run_id=str(model.analysis_run_id),
        evidence_id=str(model.evidence_id),
        position=model.position,
        sha256=model.sha256,
        created_at=model.created_at,
    )


def vision_result_model_from_entity(
    result: VisionAnalysisResultRecord,
) -> VisionAnalysisResultModel:
    value = result.result
    return VisionAnalysisResultModel(
        id=_required_uuid(result.id),
        tenant_id=_required_uuid(result.tenant_id),
        analysis_run_id=_required_uuid(result.analysis_run_id),
        stage_run_id=_required_uuid(result.stage_run_id),
        evidence_id=_required_uuid(result.evidence_id),
        schema_version=value.schema_version,
        provider_name=value.provider_name,
        model_name=value.model_name,
        model_version=value.model_version,
        model_revision=value.model_revision,
        dataset_version=value.dataset_version,
        taxonomy_version=value.taxonomy_version,
        threshold_version=value.threshold_version,
        preprocess_version=value.preprocess_version,
        postprocess_version=value.postprocess_version,
        framework=value.framework,
        runtime=value.runtime,
        precision=value.precision,
        image_width=value.image_width,
        image_height=value.image_height,
        image_quality=cast(dict[str, object], value.image_quality.model_dump(mode="json")),
        latency_ms=value.latency_ms,
        created_at=result.created_at,
    )


def detection_model_from_finding(
    *,
    tenant_id: str,
    vision_result_id: str,
    detection_id: str,
    index: int,
    finding: DetectionFinding,
    created_at: datetime,
) -> VisionDetectionModel:
    return VisionDetectionModel(
        id=_required_uuid(detection_id),
        tenant_id=_required_uuid(tenant_id),
        vision_result_id=_required_uuid(vision_result_id),
        detection_index=index,
        detection_id=finding.id,
        canonical_label=finding.label.value,
        model_class_id=finding.model_class_id,
        model_class_name=finding.model_class_name,
        confidence=finding.confidence,
        geometry_type=finding.geometry.type.value,
        coordinate_system=finding.geometry.coordinate_system.value,
        x1=finding.geometry.x1,
        y1=finding.geometry.y1,
        x2=finding.geometry.x2,
        y2=finding.geometry.y2,
        created_at=created_at,
    )


def image_assessment_model_from_entity(
    *,
    tenant_id: str,
    vision_result_id: str,
    assessment_id: str,
    assessment: VisionImageAssessment,
    created_at: datetime,
) -> VisionImageAssessmentModel:
    return VisionImageAssessmentModel(
        id=_required_uuid(assessment_id),
        tenant_id=_required_uuid(tenant_id),
        vision_result_id=_required_uuid(vision_result_id),
        assessment_type=assessment.assessment_type.value,
        model_output_name=assessment.model_output_name,
        score=assessment.score,
        threshold=assessment.threshold,
        threshold_operator=assessment.threshold_operator.value,
        outcome=assessment.outcome.value,
        created_at=created_at,
    )


def vision_result_entity_from_models(
    model: VisionAnalysisResultModel,
    detections: tuple[VisionDetectionModel, ...],
    image_assessment: VisionImageAssessmentModel | None = None,
) -> VisionAnalysisResultRecord:
    return VisionAnalysisResultRecord(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        analysis_run_id=str(model.analysis_run_id),
        stage_run_id=str(model.stage_run_id),
        evidence_id=str(model.evidence_id),
        result=VisionAnalysisResult(
            schema_version="1.0",
            provider_name=model.provider_name,
            model_name=model.model_name,
            model_version=model.model_version,
            model_revision=model.model_revision,
            dataset_version=model.dataset_version,
            taxonomy_version=model.taxonomy_version,
            threshold_version=model.threshold_version,
            preprocess_version=model.preprocess_version,
            postprocess_version=model.postprocess_version,
            framework=model.framework,
            runtime=model.runtime,
            precision=model.precision,
            image_width=model.image_width,
            image_height=model.image_height,
            image_quality=ImageQualityResult.model_validate(model.image_quality),
            detections=tuple(
                DetectionFinding(
                    id=detection.detection_id,
                    label=DefectType(detection.canonical_label),
                    model_class_id=detection.model_class_id,
                    model_class_name=detection.model_class_name,
                    confidence=detection.confidence,
                    geometry=BoundingBox(
                        coordinate_system=CoordinateSystem.NORMALIZED_XYXY,
                        x1=detection.x1,
                        y1=detection.y1,
                        x2=detection.x2,
                        y2=detection.y2,
                    ),
                )
                for detection in detections
            ),
            image_assessment=(
                VisionImageAssessment.model_validate(
                    {
                        "assessment_type": image_assessment.assessment_type,
                        "model_output_name": image_assessment.model_output_name,
                        "score": image_assessment.score,
                        "threshold": image_assessment.threshold,
                        "threshold_operator": image_assessment.threshold_operator,
                        "outcome": image_assessment.outcome,
                    }
                )
                if image_assessment is not None
                else None
            ),
            latency_ms=model.latency_ms,
        ),
        created_at=model.created_at,
    )


def idempotency_values(record: AnalysisRequestIdempotencyRecord) -> dict[str, object]:
    return {
        "id": _required_uuid(record.id),
        "tenant_id": _required_uuid(record.tenant_id),
        "case_id": _required_uuid(record.case_id),
        "operation": record.operation,
        "idempotency_key": record.idempotency_key,
        "request_hash": record.request_hash,
        "analysis_run_id": _required_uuid(record.analysis_run_id),
        "response_status": record.response_status,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
    }


def idempotency_entity_from_model(
    model: AnalysisRequestIdempotencyRecordModel,
) -> AnalysisRequestIdempotencyRecord:
    return AnalysisRequestIdempotencyRecord(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        case_id=str(model.case_id),
        operation=model.operation,
        idempotency_key=model.idempotency_key,
        request_hash=model.request_hash,
        analysis_run_id=str(model.analysis_run_id),
        response_status=model.response_status,
        created_at=model.created_at,
        expires_at=model.expires_at,
    )


def outbox_model_from_entity(event: OutboxEvent) -> OutboxEventModel:
    return OutboxEventModel(
        id=_required_uuid(event.id),
        tenant_id=_required_uuid(event.tenant_id),
        aggregate_type=event.aggregate_type,
        aggregate_id=_required_uuid(event.aggregate_id),
        event_type=event.event_type,
        event_version=event.event_version,
        payload=event.payload,
        status=event.status.value,
        attempt_count=event.attempt_count,
        available_at=event.available_at,
        claimed_at=event.claimed_at,
        claim_token=(_required_uuid(event.claim_token) if event.claim_token is not None else None),
        claimed_by=event.claimed_by,
        published_at=event.published_at,
        last_error=event.last_error,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def outbox_entity_from_model(model: OutboxEventModel) -> OutboxEvent:
    return OutboxEvent.model_validate(
        {
            "id": str(model.id),
            "tenant_id": str(model.tenant_id),
            "aggregate_type": model.aggregate_type,
            "aggregate_id": str(model.aggregate_id),
            "event_type": model.event_type,
            "event_version": model.event_version,
            "payload": model.payload,
            "status": model.status,
            "attempt_count": model.attempt_count,
            "available_at": model.available_at,
            "claimed_at": model.claimed_at,
            "claimed_by": model.claimed_by,
            "published_at": model.published_at,
            "claim_token": str(model.claim_token) if model.claim_token is not None else None,
            "last_error": model.last_error,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


def _run_filters(
    *,
    tenant_id: UUID,
    case_id: UUID,
    criteria: AnalysisRunListCriteria,
) -> list[ColumnElement[bool]]:
    filters = [
        AnalysisRunModel.tenant_id == tenant_id,
        AnalysisRunModel.case_id == case_id,
    ]
    if criteria.status is not None:
        filters.append(AnalysisRunModel.status == criteria.status.value)
    if criteria.pipeline is not None:
        filters.append(AnalysisRunModel.pipeline_name == criteria.pipeline.value)
    return filters


class SQLAlchemyAnalysisRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, run: AnalysisRun) -> None:
        _require_tenant_scope(tenant_id=tenant_id, entity_tenant_id=run.tenant_id)
        self._session.add(analysis_run_model_from_entity(run))

    def lock_admission_counts(self, *, tenant_id: str) -> AnalysisAdmissionCounts:
        """Serialize all new-run admissions and count current nonterminal runs."""

        tenant_uuid = _required_uuid(tenant_id)
        # The shared two-int advisory key serializes both global and per-tenant
        # checks until this Unit of Work commits or rolls back.
        self._session.execute(select(func.pg_advisory_xact_lock(1_129_538_375, 1)))
        nonterminal = (
            AnalysisRunStatus.QUEUED.value,
            AnalysisRunStatus.RUNNING.value,
            AnalysisRunStatus.RETRY_WAITING.value,
        )
        global_count, tenant_count = self._session.execute(
            select(
                func.count(AnalysisRunModel.id),
                func.count(AnalysisRunModel.id).filter(AnalysisRunModel.tenant_id == tenant_uuid),
            ).where(AnalysisRunModel.status.in_(nonterminal))
        ).one()
        return AnalysisAdmissionCounts(
            global_nonterminal=int(global_count),
            tenant_nonterminal=int(tenant_count),
        )

    def get(
        self,
        *,
        tenant_id: str,
        case_id: str,
        analysis_run_id: str,
    ) -> AnalysisRun | None:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        run_uuid = _optional_uuid(analysis_run_id)
        if tenant_uuid is None or case_uuid is None or run_uuid is None:
            return None
        model = self._session.scalars(
            select(AnalysisRunModel).where(
                AnalysisRunModel.tenant_id == tenant_uuid,
                AnalysisRunModel.case_id == case_uuid,
                AnalysisRunModel.id == run_uuid,
            )
        ).one_or_none()
        return analysis_run_entity_from_model(model) if model is not None else None

    def get_for_update(
        self,
        *,
        tenant_id: str,
        case_id: str,
        analysis_run_id: str,
    ) -> AnalysisRun | None:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        run_uuid = _optional_uuid(analysis_run_id)
        if tenant_uuid is None or case_uuid is None or run_uuid is None:
            return None
        model = self._session.scalars(
            select(AnalysisRunModel)
            .where(
                AnalysisRunModel.tenant_id == tenant_uuid,
                AnalysisRunModel.case_id == case_uuid,
                AnalysisRunModel.id == run_uuid,
            )
            .with_for_update()
        ).one_or_none()
        return analysis_run_entity_from_model(model) if model is not None else None

    def list(
        self,
        *,
        tenant_id: str,
        case_id: str,
        criteria: AnalysisRunListCriteria,
    ) -> tuple[AnalysisRun, ...]:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        if tenant_uuid is None or case_uuid is None:
            return ()
        if criteria.page < 1 or criteria.page_size < 1:
            raise ValueError("page and page_size must be positive")
        statement = (
            select(AnalysisRunModel)
            .where(*_run_filters(tenant_id=tenant_uuid, case_id=case_uuid, criteria=criteria))
            .order_by(AnalysisRunModel.created_at.desc(), AnalysisRunModel.id.desc())
            .offset((criteria.page - 1) * criteria.page_size)
            .limit(criteria.page_size)
        )
        return tuple(
            analysis_run_entity_from_model(model) for model in self._session.scalars(statement)
        )

    def count(
        self,
        *,
        tenant_id: str,
        case_id: str,
        criteria: AnalysisRunListCriteria,
    ) -> int:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        if tenant_uuid is None or case_uuid is None:
            return 0
        statement = (
            select(func.count())
            .select_from(AnalysisRunModel)
            .where(*_run_filters(tenant_id=tenant_uuid, case_id=case_uuid, criteria=criteria))
        )
        return int(self._session.scalar(statement) or 0)

    def latest(self, *, tenant_id: str, case_id: str) -> AnalysisRun | None:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        if tenant_uuid is None or case_uuid is None:
            return None
        model = self._session.scalars(
            select(AnalysisRunModel)
            .where(
                AnalysisRunModel.tenant_id == tenant_uuid,
                AnalysisRunModel.case_id == case_uuid,
            )
            .order_by(AnalysisRunModel.created_at.desc(), AnalysisRunModel.id.desc())
            .limit(1)
        ).one_or_none()
        return analysis_run_entity_from_model(model) if model is not None else None

    def transition(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        expected_status: AnalysisRunStatus,
        target_status: AnalysisRunStatus,
        now: datetime,
        failure: AnalysisFailure | None = None,
    ) -> AnalysisRun | None:
        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        if tenant_uuid is None or run_uuid is None:
            return None
        require_run_transition(expected_status, target_status)
        if target_status is AnalysisRunStatus.FAILED and failure is None:
            raise ValueError("FAILED analysis runs require a failure")
        values: dict[str, object] = {
            "status": target_status.value,
            "updated_at": now,
            **_failure_values(failure),
        }
        if target_status is AnalysisRunStatus.RUNNING:
            values["started_at"] = func.coalesce(AnalysisRunModel.started_at, now)
            values["completed_at"] = None
        elif target_status in {
            AnalysisRunStatus.PARTIAL_SUCCESS,
            AnalysisRunStatus.SUCCEEDED,
            AnalysisRunStatus.FAILED,
        }:
            values["started_at"] = func.coalesce(AnalysisRunModel.started_at, now)
            values["completed_at"] = now
        else:
            values["completed_at"] = None
        model = self._session.scalars(
            update(AnalysisRunModel)
            .where(
                AnalysisRunModel.tenant_id == tenant_uuid,
                AnalysisRunModel.id == run_uuid,
                AnalysisRunModel.status == expected_status.value,
            )
            .values(**values)
            .returning(AnalysisRunModel)
        ).one_or_none()
        return analysis_run_entity_from_model(model) if model is not None else None


class SQLAlchemyAnalysisStageRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, stage_run: AnalysisStageRun) -> None:
        _require_tenant_scope(tenant_id=tenant_id, entity_tenant_id=stage_run.tenant_id)
        self._session.add(stage_run_model_from_entity(stage_run))

    def get(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        stage_run_id: str,
    ) -> AnalysisStageRun | None:
        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        stage_uuid = _optional_uuid(stage_run_id)
        if tenant_uuid is None or run_uuid is None or stage_uuid is None:
            return None
        model = self._session.scalars(
            select(AnalysisStageRunModel).where(
                AnalysisStageRunModel.tenant_id == tenant_uuid,
                AnalysisStageRunModel.analysis_run_id == run_uuid,
                AnalysisStageRunModel.id == stage_uuid,
            )
        ).one_or_none()
        return stage_run_entity_from_model(model) if model is not None else None

    def list(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
    ) -> tuple[AnalysisStageRun, ...]:
        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        if tenant_uuid is None or run_uuid is None:
            return ()
        statement = (
            select(AnalysisStageRunModel)
            .where(
                AnalysisStageRunModel.tenant_id == tenant_uuid,
                AnalysisStageRunModel.analysis_run_id == run_uuid,
            )
            .order_by(AnalysisStageRunModel.created_at.asc(), AnalysisStageRunModel.id.asc())
        )
        return tuple(
            stage_run_entity_from_model(model) for model in self._session.scalars(statement)
        )

    def transition(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        stage_run_id: str,
        expected_status: AnalysisStageStatus,
        target_status: AnalysisStageStatus,
        now: datetime,
        next_attempt_at: datetime | None = None,
        failure: AnalysisFailure | None = None,
    ) -> AnalysisStageRun | None:
        """Conditionally fail an unclaimed stage without bypassing lease fencing.

        This path exists for failures that happen before provider execution, such
        as terminal Outbox dispatch exhaustion.  Entering RUNNING must go through
        ``claim_for_execution`` and leaving RUNNING must go through
        ``transition_if_claimed`` so a stale worker can never overwrite the
        current lease holder.
        """

        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        stage_uuid = _optional_uuid(stage_run_id)
        if tenant_uuid is None or run_uuid is None or stage_uuid is None:
            return None
        require_stage_transition(expected_status, target_status)
        if expected_status is AnalysisStageStatus.RUNNING:
            raise ValueError("RUNNING stages require a claim-token-fenced transition")
        if target_status is AnalysisStageStatus.RUNNING:
            raise ValueError("entering RUNNING requires claim_for_execution")
        if target_status is not AnalysisStageStatus.FAILED:
            raise ValueError("unclaimed stage transitions only support FAILED")
        if next_attempt_at is not None:
            raise ValueError("next_attempt_at is only valid for RETRY_WAITING")
        if failure is None:
            raise ValueError("FAILED stages require a failure")

        model = self._session.scalars(
            update(AnalysisStageRunModel)
            .where(
                AnalysisStageRunModel.tenant_id == tenant_uuid,
                AnalysisStageRunModel.analysis_run_id == run_uuid,
                AnalysisStageRunModel.id == stage_uuid,
                AnalysisStageRunModel.status == expected_status.value,
                AnalysisStageRunModel.claim_token.is_(None),
                AnalysisStageRunModel.lease_expires_at.is_(None),
            )
            .values(
                status=AnalysisStageStatus.FAILED.value,
                claim_token=None,
                lease_expires_at=None,
                next_attempt_at=None,
                started_at=func.coalesce(AnalysisStageRunModel.started_at, now),
                completed_at=now,
                updated_at=now,
                **_failure_values(failure),
            )
            .returning(AnalysisStageRunModel)
        ).one_or_none()
        return stage_run_entity_from_model(model) if model is not None else None

    def claim_for_execution(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        stage_run_id: str,
        claim_token: str,
        now: datetime,
        claim_expires_at: datetime,
    ) -> AnalysisStageRun | None:
        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        stage_uuid = _optional_uuid(stage_run_id)
        token_uuid = _optional_uuid(claim_token)
        if None in (tenant_uuid, run_uuid, stage_uuid, token_uuid):
            return None
        if claim_expires_at <= now:
            raise ValueError("claim_expires_at must be later than now")
        eligible = or_(
            AnalysisStageRunModel.status == AnalysisStageStatus.QUEUED.value,
            and_(
                AnalysisStageRunModel.status == AnalysisStageStatus.RETRY_WAITING.value,
                AnalysisStageRunModel.next_attempt_at <= now,
            ),
            and_(
                AnalysisStageRunModel.status == AnalysisStageStatus.RUNNING.value,
                AnalysisStageRunModel.lease_expires_at <= now,
            ),
        )
        values: dict[str, object] = {
            "status": AnalysisStageStatus.RUNNING.value,
            "attempt_count": AnalysisStageRunModel.attempt_count + 1,
            "claim_token": token_uuid,
            "lease_expires_at": claim_expires_at,
            "next_attempt_at": None,
            "last_attempt_started_at": now,
            "last_attempt_completed_at": None,
            "started_at": func.coalesce(AnalysisStageRunModel.started_at, now),
            "completed_at": None,
            "updated_at": now,
            **_provider_values(None),
            **_failure_values(None),
        }
        model = self._session.scalars(
            update(AnalysisStageRunModel)
            .where(
                AnalysisStageRunModel.tenant_id == tenant_uuid,
                AnalysisStageRunModel.analysis_run_id == run_uuid,
                AnalysisStageRunModel.id == stage_uuid,
                eligible,
            )
            .values(**values)
            .returning(AnalysisStageRunModel)
        ).one_or_none()
        return stage_run_entity_from_model(model) if model is not None else None

    def transition_if_claimed(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        stage_run_id: str,
        claim_token: str,
        target_status: AnalysisStageStatus,
        now: datetime,
        next_attempt_at: datetime | None = None,
        failure: AnalysisFailure | None = None,
        provider_execution: ProviderExecutionMetadata | None = None,
    ) -> AnalysisStageRun | None:
        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        stage_uuid = _optional_uuid(stage_run_id)
        token_uuid = _optional_uuid(claim_token)
        if None in (tenant_uuid, run_uuid, stage_uuid, token_uuid):
            return None
        require_stage_transition(AnalysisStageStatus.RUNNING, target_status)
        if target_status is AnalysisStageStatus.RETRY_WAITING:
            if next_attempt_at is None or next_attempt_at <= now:
                raise ValueError("RETRY_WAITING requires a future next_attempt_at")
        elif next_attempt_at is not None:
            raise ValueError("next_attempt_at is only valid for RETRY_WAITING")
        if (
            target_status in {AnalysisStageStatus.RETRY_WAITING, AnalysisStageStatus.FAILED}
            and failure is None
        ):
            raise ValueError(f"{target_status.value} requires a failure")
        values: dict[str, object] = {
            "status": target_status.value,
            "claim_token": None,
            "lease_expires_at": None,
            "next_attempt_at": next_attempt_at,
            "last_attempt_completed_at": now,
            "completed_at": (
                now
                if target_status in {AnalysisStageStatus.SUCCEEDED, AnalysisStageStatus.FAILED}
                else None
            ),
            "updated_at": now,
            **_provider_values(provider_execution),
            **_failure_values(failure),
        }
        model = self._session.scalars(
            update(AnalysisStageRunModel)
            .where(
                AnalysisStageRunModel.tenant_id == tenant_uuid,
                AnalysisStageRunModel.analysis_run_id == run_uuid,
                AnalysisStageRunModel.id == stage_uuid,
                AnalysisStageRunModel.status == AnalysisStageStatus.RUNNING.value,
                AnalysisStageRunModel.claim_token == token_uuid,
            )
            .values(**values)
            .returning(AnalysisStageRunModel)
        ).one_or_none()
        return stage_run_entity_from_model(model) if model is not None else None


class SQLAlchemyAnalysisStageAttemptRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, attempt: AnalysisStageAttempt) -> None:
        _require_tenant_scope(tenant_id=tenant_id, entity_tenant_id=attempt.tenant_id)
        self._session.add(attempt_model_from_entity(attempt))

    def get(
        self,
        *,
        tenant_id: str,
        stage_run_id: str,
        attempt_number: int,
    ) -> AnalysisStageAttempt | None:
        tenant_uuid = _optional_uuid(tenant_id)
        stage_uuid = _optional_uuid(stage_run_id)
        if tenant_uuid is None or stage_uuid is None or attempt_number < 1:
            return None
        model = self._session.scalars(
            select(AnalysisStageAttemptModel).where(
                AnalysisStageAttemptModel.tenant_id == tenant_uuid,
                AnalysisStageAttemptModel.stage_run_id == stage_uuid,
                AnalysisStageAttemptModel.attempt_number == attempt_number,
            )
        ).one_or_none()
        return attempt_entity_from_model(model) if model is not None else None

    def list(
        self,
        *,
        tenant_id: str,
        stage_run_id: str,
    ) -> tuple[AnalysisStageAttempt, ...]:
        tenant_uuid = _optional_uuid(tenant_id)
        stage_uuid = _optional_uuid(stage_run_id)
        if tenant_uuid is None or stage_uuid is None:
            return ()
        statement = (
            select(AnalysisStageAttemptModel)
            .where(
                AnalysisStageAttemptModel.tenant_id == tenant_uuid,
                AnalysisStageAttemptModel.stage_run_id == stage_uuid,
            )
            .order_by(AnalysisStageAttemptModel.attempt_number.asc())
        )
        return tuple(attempt_entity_from_model(model) for model in self._session.scalars(statement))

    def finalize_if_claimed(
        self,
        *,
        tenant_id: str,
        stage_run_id: str,
        attempt_number: int,
        claim_token: str,
        target_status: AnalysisAttemptStatus,
        completed_at: datetime,
        failure: AnalysisFailure | None = None,
        provider_execution: ProviderExecutionMetadata | None = None,
    ) -> AnalysisStageAttempt | None:
        tenant_uuid = _optional_uuid(tenant_id)
        stage_uuid = _optional_uuid(stage_run_id)
        token_uuid = _optional_uuid(claim_token)
        if tenant_uuid is None or stage_uuid is None or token_uuid is None or attempt_number < 1:
            return None
        if target_status is AnalysisAttemptStatus.RUNNING:
            raise ValueError("a finalized attempt cannot remain RUNNING")
        if (
            target_status
            in {
                AnalysisAttemptStatus.RETRY_WAITING,
                AnalysisAttemptStatus.FAILED,
                AnalysisAttemptStatus.ABANDONED,
            }
            and failure is None
        ):
            raise ValueError(f"{target_status.value} requires a failure")
        values = {
            "status": target_status.value,
            "completed_at": completed_at,
            **_provider_values(provider_execution),
            **_failure_values(failure),
        }
        model = self._session.scalars(
            update(AnalysisStageAttemptModel)
            .where(
                AnalysisStageAttemptModel.tenant_id == tenant_uuid,
                AnalysisStageAttemptModel.stage_run_id == stage_uuid,
                AnalysisStageAttemptModel.attempt_number == attempt_number,
                AnalysisStageAttemptModel.status == AnalysisAttemptStatus.RUNNING.value,
                AnalysisStageAttemptModel.execution_token == token_uuid,
            )
            .values(**values)
            .returning(AnalysisStageAttemptModel)
        ).one_or_none()
        return attempt_entity_from_model(model) if model is not None else None

    def abandon_stale(
        self,
        *,
        tenant_id: str,
        stage_run_id: str,
        stale_before: datetime,
        abandoned_at: datetime,
        failure: AnalysisFailure,
    ) -> int:
        tenant_uuid = _optional_uuid(tenant_id)
        stage_uuid = _optional_uuid(stage_run_id)
        if tenant_uuid is None or stage_uuid is None:
            return 0
        statement = (
            update(AnalysisStageAttemptModel)
            .where(
                AnalysisStageAttemptModel.tenant_id == tenant_uuid,
                AnalysisStageAttemptModel.stage_run_id == stage_uuid,
                AnalysisStageAttemptModel.status == AnalysisAttemptStatus.RUNNING.value,
                AnalysisStageAttemptModel.started_at < stale_before,
            )
            .values(
                status=AnalysisAttemptStatus.ABANDONED.value,
                completed_at=abandoned_at,
                **_failure_values(failure),
            )
            .returning(AnalysisStageAttemptModel.id)
        )
        return len(tuple(self._session.scalars(statement)))


class SQLAlchemyAnalysisRequestIdempotencyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def claim(
        self,
        *,
        tenant_id: str,
        record: AnalysisRequestIdempotencyRecord,
    ) -> AnalysisRequestIdempotencyClaim:
        tenant_uuid = _require_tenant_scope(
            tenant_id=tenant_id,
            entity_tenant_id=record.tenant_id,
        )
        statement = (
            postgresql_insert(AnalysisRequestIdempotencyRecordModel)
            .values(**idempotency_values(record))
            .on_conflict_do_nothing(
                constraint="uq_analysis_request_idempotency_tenant_operation_key"
            )
            .returning(AnalysisRequestIdempotencyRecordModel)
        )
        claimed = self._session.scalars(statement).one_or_none()
        if claimed is not None:
            return AnalysisRequestIdempotencyClaim(
                claimed=True,
                record=idempotency_entity_from_model(claimed),
            )
        existing = self._session.scalars(
            select(AnalysisRequestIdempotencyRecordModel).where(
                AnalysisRequestIdempotencyRecordModel.tenant_id == tenant_uuid,
                AnalysisRequestIdempotencyRecordModel.operation == record.operation,
                AnalysisRequestIdempotencyRecordModel.idempotency_key == record.idempotency_key,
            )
        ).one_or_none()
        if existing is None:
            raise InconsistentPersistenceStateError(
                "The analysis idempotency claim conflicted without a scoped record."
            )
        return AnalysisRequestIdempotencyClaim(
            claimed=False,
            record=idempotency_entity_from_model(existing),
        )


class SQLAlchemyLLMExtractionResultRepository:
    """Append-only result repository; intentionally exposes no update or delete."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, result: LLMExtractionResultRecord) -> None:
        _require_tenant_scope(tenant_id=tenant_id, entity_tenant_id=result.tenant_id)
        self._session.add(result_model_from_entity(result))

    def get_by_run(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
    ) -> LLMExtractionResultRecord | None:
        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        if tenant_uuid is None or run_uuid is None:
            return None
        model = self._session.scalars(
            select(LLMExtractionResultModel).where(
                LLMExtractionResultModel.tenant_id == tenant_uuid,
                LLMExtractionResultModel.analysis_run_id == run_uuid,
            )
        ).one_or_none()
        return result_entity_from_model(model) if model is not None else None


class SQLAlchemyLLMExtractionResultV2Repository:
    """Append-only v2 result repository; intentionally exposes no update or delete."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, result: LLMExtractionResultV2Record) -> None:
        _require_tenant_scope(tenant_id=tenant_id, entity_tenant_id=result.tenant_id)
        self._session.add(
            LLMExtractionResultV2Model(
                id=_required_uuid(result.id),
                tenant_id=_required_uuid(result.tenant_id),
                analysis_run_id=_required_uuid(result.analysis_run_id),
                stage_run_id=_required_uuid(result.stage_run_id),
                schema_version=result.result.schema_version,
                language=result.result.language,
                issue_types=[item.value for item in result.result.issue_types],
                claims=[item.model_dump(mode="json") for item in result.result.claims],
                requested_actions=[
                    item.model_dump(mode="json") for item in result.result.requested_actions
                ],
                text_ambiguities=[item.value for item in result.result.text_ambiguities],
                summary=result.result.summary,
                system_missing_information=[
                    item.value for item in result.completeness.system_missing_information
                ],
                action_consistency=result.completeness.action_consistency.value,
                completeness_rule_version=result.completeness.rule_version,
                created_at=result.created_at,
            )
        )

    def get_by_run(
        self, *, tenant_id: str, analysis_run_id: str
    ) -> LLMExtractionResultV2Record | None:
        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        if tenant_uuid is None or run_uuid is None:
            return None
        model = self._session.scalars(
            select(LLMExtractionResultV2Model).where(
                LLMExtractionResultV2Model.tenant_id == tenant_uuid,
                LLMExtractionResultV2Model.analysis_run_id == run_uuid,
            )
        ).one_or_none()
        if model is None:
            return None
        extraction = LLMTextExtractionResultV2.model_validate(
            {
                "schema_version": model.schema_version,
                "language": model.language,
                "issue_types": model.issue_types,
                "claims": model.claims,
                "requested_actions": model.requested_actions,
                "text_ambiguities": model.text_ambiguities,
                "summary": model.summary,
            }
        )
        completeness = CompletenessResult.model_validate(
            {
                "rule_version": model.completeness_rule_version,
                "system_missing_information": model.system_missing_information,
                "action_consistency": model.action_consistency,
            }
        )
        return LLMExtractionResultV2Record(
            id=str(model.id),
            tenant_id=str(model.tenant_id),
            analysis_run_id=str(model.analysis_run_id),
            stage_run_id=str(model.stage_run_id),
            result=extraction,
            completeness=completeness,
            created_at=model.created_at,
        )


class SQLAlchemyAnalysisEvidenceSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, snapshot: AnalysisEvidenceSnapshot) -> None:
        _require_tenant_scope(tenant_id=tenant_id, entity_tenant_id=snapshot.tenant_id)
        self._session.add(evidence_snapshot_model_from_entity(snapshot))

    def list(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
    ) -> tuple[AnalysisEvidenceSnapshot, ...]:
        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        if tenant_uuid is None or run_uuid is None:
            return ()
        statement = (
            select(AnalysisRunEvidenceModel)
            .where(
                AnalysisRunEvidenceModel.tenant_id == tenant_uuid,
                AnalysisRunEvidenceModel.analysis_run_id == run_uuid,
            )
            .order_by(AnalysisRunEvidenceModel.position.asc())
        )
        return tuple(
            evidence_snapshot_entity_from_model(model) for model in self._session.scalars(statement)
        )


class SQLAlchemyVisionAnalysisResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, result: VisionAnalysisResultRecord) -> None:
        _require_tenant_scope(tenant_id=tenant_id, entity_tenant_id=result.tenant_id)
        self._session.add(vision_result_model_from_entity(result))
        for index, finding in enumerate(result.result.detections):
            detection_uuid = str(
                uuid5(NAMESPACE_URL, f"csight:{result.id}:vision-detection:{index}")
            )
            self._session.add(
                detection_model_from_finding(
                    tenant_id=tenant_id,
                    vision_result_id=result.id,
                    detection_id=detection_uuid,
                    index=index,
                    finding=finding,
                    created_at=result.created_at,
                )
            )
        if result.result.image_assessment is not None:
            assessment_uuid = str(
                uuid5(NAMESPACE_URL, f"csight:{result.id}:vision-image-assessment")
            )
            self._session.add(
                image_assessment_model_from_entity(
                    tenant_id=tenant_id,
                    vision_result_id=result.id,
                    assessment_id=assessment_uuid,
                    assessment=result.result.image_assessment,
                    created_at=result.created_at,
                )
            )

    def list_by_run(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
    ) -> tuple[VisionAnalysisResultRecord, ...]:
        tenant_uuid = _optional_uuid(tenant_id)
        run_uuid = _optional_uuid(analysis_run_id)
        if tenant_uuid is None or run_uuid is None:
            return ()
        results = tuple(
            self._session.scalars(
                select(VisionAnalysisResultModel)
                .where(
                    VisionAnalysisResultModel.tenant_id == tenant_uuid,
                    VisionAnalysisResultModel.analysis_run_id == run_uuid,
                )
                .order_by(VisionAnalysisResultModel.created_at.asc(), VisionAnalysisResultModel.id)
            )
        )
        records: list[VisionAnalysisResultRecord] = []
        for model in results:
            detections = tuple(
                self._session.scalars(
                    select(VisionDetectionModel)
                    .where(
                        VisionDetectionModel.tenant_id == tenant_uuid,
                        VisionDetectionModel.vision_result_id == model.id,
                    )
                    .order_by(VisionDetectionModel.detection_index.asc())
                )
            )
            image_assessment = self._session.scalar(
                select(VisionImageAssessmentModel).where(
                    VisionImageAssessmentModel.tenant_id == tenant_uuid,
                    VisionImageAssessmentModel.vision_result_id == model.id,
                )
            )
            records.append(vision_result_entity_from_models(model, detections, image_assessment))
        return tuple(records)


def _sanitize_error(value: str) -> str:
    normalized = value.strip()[:500]
    return normalized or "OUTBOX_DISPATCH_FAILED"


class SQLAlchemyOutboxEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, event: OutboxEvent) -> None:
        _require_tenant_scope(tenant_id=tenant_id, entity_tenant_id=event.tenant_id)
        self._session.add(outbox_model_from_entity(event))

    def get_for_update(self, *, event_id: str) -> OutboxEvent | None:
        event_uuid = _optional_uuid(event_id)
        if event_uuid is None:
            return None
        model = self._session.scalars(
            select(OutboxEventModel).where(OutboxEventModel.id == event_uuid).with_for_update()
        ).one_or_none()
        return outbox_entity_from_model(model) if model is not None else None

    def _recover_stale(
        self,
        *,
        stale_before: datetime,
        available_at: datetime,
    ) -> int:
        statement = (
            update(OutboxEventModel)
            .where(
                OutboxEventModel.status == OutboxStatus.PROCESSING.value,
                OutboxEventModel.claimed_at < stale_before,
            )
            .values(
                status=OutboxStatus.PENDING.value,
                available_at=available_at,
                claimed_at=None,
                claim_token=None,
                claimed_by=None,
                published_at=None,
                last_error="OUTBOX_STALE_CLAIM_RECOVERED",
                updated_at=available_at,
            )
            .returning(OutboxEventModel.id)
        )
        return len(tuple(self._session.scalars(statement)))

    def claim_batch(
        self,
        *,
        now: datetime,
        stale_before: datetime,
        claim_token: str,
        claimed_by: str,
        limit: int,
    ) -> tuple[OutboxEvent, ...]:
        token_uuid = _optional_uuid(claim_token)
        if token_uuid is None:
            return ()
        if limit < 1:
            raise ValueError("outbox claim limit must be positive")
        normalized_claimed_by = claimed_by.strip()
        if not normalized_claimed_by or len(normalized_claimed_by) > 255:
            raise ValueError("claimed_by must contain 1 to 255 characters")

        self._recover_stale(stale_before=stale_before, available_at=now)
        candidate_ids = tuple(
            self._session.scalars(
                select(OutboxEventModel.id)
                .where(
                    OutboxEventModel.status == OutboxStatus.PENDING.value,
                    OutboxEventModel.available_at <= now,
                )
                .order_by(
                    OutboxEventModel.available_at.asc(),
                    OutboxEventModel.created_at.asc(),
                    OutboxEventModel.id.asc(),
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        if not candidate_ids:
            return ()
        claimed_models = tuple(
            self._session.scalars(
                update(OutboxEventModel)
                .where(
                    OutboxEventModel.id.in_(candidate_ids),
                    OutboxEventModel.status == OutboxStatus.PENDING.value,
                )
                .values(
                    status=OutboxStatus.PROCESSING.value,
                    attempt_count=OutboxEventModel.attempt_count + 1,
                    claimed_at=now,
                    claim_token=token_uuid,
                    claimed_by=normalized_claimed_by,
                    published_at=None,
                    updated_at=now,
                )
                .returning(OutboxEventModel)
            )
        )
        by_id = {model.id: model for model in claimed_models}
        return tuple(
            outbox_entity_from_model(by_id[event_id])
            for event_id in candidate_ids
            if event_id in by_id
        )

    def mark_published(
        self,
        *,
        tenant_id: str,
        event_id: str,
        claim_token: str,
        published_at: datetime,
    ) -> OutboxEvent | None:
        return self._finish_claim(
            tenant_id=tenant_id,
            event_id=event_id,
            claim_token=claim_token,
            values={
                "status": OutboxStatus.PUBLISHED.value,
                "claimed_at": None,
                "claim_token": None,
                "claimed_by": None,
                "published_at": published_at,
                "last_error": None,
                "updated_at": published_at,
            },
        )

    def release_for_retry(
        self,
        *,
        tenant_id: str,
        event_id: str,
        claim_token: str,
        available_at: datetime,
        last_error: str,
        now: datetime,
    ) -> OutboxEvent | None:
        return self._finish_claim(
            tenant_id=tenant_id,
            event_id=event_id,
            claim_token=claim_token,
            values={
                "status": OutboxStatus.PENDING.value,
                "available_at": available_at,
                "claimed_at": None,
                "claim_token": None,
                "claimed_by": None,
                "published_at": None,
                "last_error": _sanitize_error(last_error),
                "updated_at": now,
            },
        )

    def mark_failed(
        self,
        *,
        tenant_id: str,
        event_id: str,
        claim_token: str,
        last_error: str,
        now: datetime,
    ) -> OutboxEvent | None:
        return self._finish_claim(
            tenant_id=tenant_id,
            event_id=event_id,
            claim_token=claim_token,
            values={
                "status": OutboxStatus.FAILED.value,
                "claimed_at": None,
                "claim_token": None,
                "claimed_by": None,
                "published_at": None,
                "last_error": _sanitize_error(last_error),
                "updated_at": now,
            },
        )

    def record_consumer_failure(
        self,
        *,
        event_id: str,
        last_error: str,
        now: datetime,
        terminal: bool,
    ) -> OutboxEvent | None:
        event_uuid = _optional_uuid(event_id)
        if event_uuid is None:
            return None
        model = self._session.scalars(
            select(OutboxEventModel).where(OutboxEventModel.id == event_uuid).with_for_update()
        ).one_or_none()
        if model is None:
            return None
        if terminal:
            model.status = OutboxStatus.FAILED.value
            model.attempt_count = max(1, model.attempt_count)
            model.claimed_at = None
            model.claim_token = None
            model.claimed_by = None
            model.published_at = None
        model.last_error = _sanitize_error(last_error)
        model.updated_at = now
        self._session.flush()
        return outbox_entity_from_model(model)

    def _finish_claim(
        self,
        *,
        tenant_id: str,
        event_id: str,
        claim_token: str,
        values: dict[str, object],
    ) -> OutboxEvent | None:
        tenant_uuid = _optional_uuid(tenant_id)
        event_uuid = _optional_uuid(event_id)
        token_uuid = _optional_uuid(claim_token)
        if tenant_uuid is None or event_uuid is None or token_uuid is None:
            return None
        model = self._session.scalars(
            update(OutboxEventModel)
            .where(
                OutboxEventModel.tenant_id == tenant_uuid,
                OutboxEventModel.id == event_uuid,
                OutboxEventModel.status == OutboxStatus.PROCESSING.value,
                OutboxEventModel.claim_token == token_uuid,
            )
            .values(**values)
            .returning(OutboxEventModel)
        ).one_or_none()
        return outbox_entity_from_model(model) if model is not None else None

    def recover_stale(
        self,
        *,
        stale_before: datetime,
        available_at: datetime,
    ) -> int:
        return self._recover_stale(stale_before=stale_before, available_at=available_at)


__all__ = [
    "SQLAlchemyAnalysisEvidenceSnapshotRepository",
    "SQLAlchemyAnalysisRequestIdempotencyRepository",
    "SQLAlchemyAnalysisRunRepository",
    "SQLAlchemyAnalysisStageAttemptRepository",
    "SQLAlchemyAnalysisStageRunRepository",
    "SQLAlchemyLLMExtractionResultRepository",
    "SQLAlchemyOutboxEventRepository",
    "SQLAlchemyVisionAnalysisResultRepository",
    "analysis_run_entity_from_model",
    "analysis_run_model_from_entity",
    "attempt_entity_from_model",
    "attempt_model_from_entity",
    "idempotency_entity_from_model",
    "idempotency_values",
    "outbox_entity_from_model",
    "outbox_model_from_entity",
    "result_entity_from_model",
    "result_model_from_entity",
    "stage_run_entity_from_model",
    "stage_run_model_from_entity",
]
