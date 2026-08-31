"""Tenant-scoped PostgreSQL dead-letter reads and operator recovery writes."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    AnalysisRunModel,
    AnalysisStageRunModel,
    CaseResolutionRequestEventModel,
    ExternalActionSimulationRequestEventModel,
    GroundedExplanationOutboxEventModel,
    GroundedExplanationRunModel,
    HumanReviewRequestEventModel,
    OperationalFailureModel,
    OperationalFailureRecoveryEventModel,
    OperationalFailureRecoveryRunModel,
    OperationalFailureResolutionModel,
    OutboxEventModel,
    PolicyEvaluationOutboxEventModel,
    PolicyEvaluationRunModel,
    PolicyRetrievalOutboxEventModel,
    PolicyRetrievalRunModel,
)
from app.platform.errors import (
    IdempotencyKeyReusedError,
    OperationalFailureAlreadyResolvedError,
    OperationalFailureNotFoundError,
    OperationalFailureNotReplayableError,
    ValidationError,
)
from app.platform.operations import (
    OperationalFailureAction,
    OperationalFailureKind,
    OperationalFailurePage,
    OperationalFailurePipeline,
    OperationalFailureRecord,
    OperationalFailureResolutionResult,
    OperationalFailureStatus,
)

_MAX_CURSOR_BYTES = 384
_ANALYSIS_DISPATCH_ERROR = "Message publication failed permanently."
_CANCEL_FAILURE_CODE = "OPERATIONAL_FAILURE_CANCELLED"
_CANCEL_FAILURE_MESSAGE = "An authenticated operator cancelled the failed delivery."


class _SourceSpec:
    def __init__(
        self,
        *,
        model: type[Any],
        topic: str,
        run_attribute: str,
        queue_key: str,
        dispatch_code: str,
    ) -> None:
        self.model = model
        self.topic = topic
        self.run_attribute = run_attribute
        self.queue_key = queue_key
        self.dispatch_code = dispatch_code


_SOURCE_SPECS: dict[str, _SourceSpec] = {
    "policy_retrieval_outbox_events": _SourceSpec(
        model=PolicyRetrievalOutboxEventModel,
        topic="policy_retrieval.requested.v1",
        run_attribute="retrieval_run_id",
        queue_key="retrieval_run_id",
        dispatch_code="POLICY_RETRIEVAL_OUTBOX_FAILED",
    ),
    "grounded_explanation_outbox_events": _SourceSpec(
        model=GroundedExplanationOutboxEventModel,
        topic="grounded_explanation.requested.v1",
        run_attribute="grounded_explanation_run_id",
        queue_key="grounded_explanation_run_id",
        dispatch_code="GROUNDED_EXPLANATION_OUTBOX_FAILED",
    ),
    "policy_evaluation_outbox_events": _SourceSpec(
        model=PolicyEvaluationOutboxEventModel,
        topic="policy_evaluation.requested.v1",
        run_attribute="policy_evaluation_run_id",
        queue_key="policy_evaluation_run_id",
        dispatch_code="POLICY_EVALUATION_OUTBOX_FAILED",
    ),
    "human_review_request_events": _SourceSpec(
        model=HumanReviewRequestEventModel,
        topic="human_review.requested.v1",
        run_attribute="policy_evaluation_run_id",
        queue_key="policy_evaluation_run_id",
        dispatch_code="HUMAN_REVIEW_OUTBOX_FAILED",
    ),
    "case_resolution_request_events": _SourceSpec(
        model=CaseResolutionRequestEventModel,
        topic="case_resolution.requested.v1",
        run_attribute="resolution_id",
        queue_key="resolution_id",
        dispatch_code="CASE_RESOLUTION_OUTBOX_FAILED",
    ),
    "external_action_simulation_request_events": _SourceSpec(
        model=ExternalActionSimulationRequestEventModel,
        topic="external_action.simulation_requested.v1",
        run_attribute="external_action_intent_id",
        queue_key="external_action_intent_id",
        dispatch_code="EXTERNAL_ACTION_SIMULATION_OUTBOX_FAILED",
    ),
}


class SQLAlchemyOperationalFailureRepository:
    """Keep failure history immutable while fencing one terminal operator action."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._factory = session_factory
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    def list_failures(
        self,
        *,
        tenant_id: str,
        since: datetime,
        limit: int,
        cursor: str | None,
    ) -> OperationalFailurePage:
        tenant_uuid = _uuid_or_validation(tenant_id, "tenant identifier")
        if not 1 <= limit <= 100:
            raise ValidationError("Operations failure page size must be between 1 and 100.")
        if since.tzinfo is None or since.utcoffset() is None:
            raise ValidationError("Failure lookback timestamp must include a timezone.")
        cursor_value = _decode_cursor(cursor) if cursor is not None else None

        statement = (
            select(
                OperationalFailureModel,
                OperationalFailureResolutionModel,
                OperationalFailureRecoveryEventModel,
            )
            .outerjoin(
                OperationalFailureResolutionModel,
                and_(
                    OperationalFailureResolutionModel.tenant_id
                    == OperationalFailureModel.tenant_id,
                    OperationalFailureResolutionModel.failure_id == OperationalFailureModel.id,
                ),
            )
            .outerjoin(
                OperationalFailureRecoveryEventModel,
                and_(
                    OperationalFailureRecoveryEventModel.tenant_id
                    == OperationalFailureResolutionModel.tenant_id,
                    OperationalFailureRecoveryEventModel.recovery_run_id
                    == OperationalFailureResolutionModel.recovery_run_id,
                ),
            )
            .where(
                OperationalFailureModel.tenant_id == tenant_uuid,
                OperationalFailureModel.occurred_at >= since.astimezone(UTC),
            )
        )
        if cursor_value is not None:
            cursor_time, cursor_id = cursor_value
            statement = statement.where(
                or_(
                    OperationalFailureModel.occurred_at < cursor_time,
                    and_(
                        OperationalFailureModel.occurred_at == cursor_time,
                        OperationalFailureModel.id < cursor_id,
                    ),
                )
            )
        statement = statement.order_by(
            OperationalFailureModel.occurred_at.desc(),
            OperationalFailureModel.id.desc(),
        ).limit(limit + 1)

        with self._factory() as session:
            rows = session.execute(statement).all()
        has_more = len(rows) > limit
        selected = rows[:limit]
        items = tuple(
            _to_failure_record(failure, resolution, recovery_event)
            for failure, resolution, recovery_event in selected
        )
        next_cursor = None
        if has_more and selected:
            last_failure = selected[-1][0]
            next_cursor = _encode_cursor(last_failure.occurred_at, last_failure.id)
        return OperationalFailurePage(items=items, next_cursor=next_cursor)

    def replay_failure(
        self,
        *,
        tenant_id: str,
        failure_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> OperationalFailureResolutionResult:
        return self._resolve_failure(
            tenant_id=tenant_id,
            failure_id=failure_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            action=OperationalFailureAction.REPLAYED,
        )

    def cancel_failure(
        self,
        *,
        tenant_id: str,
        failure_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> OperationalFailureResolutionResult:
        return self._resolve_failure(
            tenant_id=tenant_id,
            failure_id=failure_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            action=OperationalFailureAction.CANCELLED,
        )

    def _resolve_failure(
        self,
        *,
        tenant_id: str,
        failure_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
        action: OperationalFailureAction,
    ) -> OperationalFailureResolutionResult:
        tenant_uuid = _uuid_or_validation(tenant_id, "tenant identifier")
        failure_uuid = _uuid_or_not_found(failure_id)
        actor_uuid = _uuid_or_validation(actor_id, "operator identifier")
        now = self._now()
        request_hash = _request_hash(failure_uuid=failure_uuid, action=action)

        with self._factory.begin() as session:
            failure = session.scalar(
                select(OperationalFailureModel)
                .where(
                    OperationalFailureModel.tenant_id == tenant_uuid,
                    OperationalFailureModel.id == failure_uuid,
                )
                .with_for_update()
            )
            if failure is None:
                raise OperationalFailureNotFoundError()
            existing = session.scalar(
                select(OperationalFailureResolutionModel).where(
                    OperationalFailureResolutionModel.tenant_id == tenant_uuid,
                    OperationalFailureResolutionModel.failure_id == failure_uuid,
                )
            )
            if existing is not None:
                return self._existing_resolution(
                    session=session,
                    existing=existing,
                    requested_action=action,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                )

            recovery_run: OperationalFailureRecoveryRunModel | None = None
            recovery_event: OperationalFailureRecoveryEventModel | None = None
            if action is OperationalFailureAction.REPLAYED:
                if not failure.replayable or failure.failure_kind != "DISPATCH":
                    raise OperationalFailureNotReplayableError()
                topic, payload = _recovery_envelope(session=session, failure=failure)
                source_correlation_id = str(payload["correlation_id"])
                recovery_run = OperationalFailureRecoveryRunModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    failure_id=failure_uuid,
                    requested_by=actor_uuid,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    correlation_id=correlation_id,
                    created_at=now,
                )
                recovery_event = OperationalFailureRecoveryEventModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    failure_id=failure_uuid,
                    recovery_run_id=recovery_run.id,
                    topic=topic,
                    payload=payload,
                    correlation_id=source_correlation_id,
                    status="PENDING",
                    attempt_count=0,
                    available_at=now,
                    claimed_at=None,
                    claim_token=None,
                    claimed_by=None,
                    published_at=None,
                    last_error=None,
                    failure_code=None,
                    failed_at=None,
                    created_at=now,
                )
                # The ORM models deliberately expose no mutable relationships.
                # Flush the immutable parent first so PostgreSQL can enforce the
                # recovery-event FK without relying on implicit unit-of-work order.
                session.add(recovery_run)
                session.flush()
                session.add(recovery_event)
            else:
                _cancel_awaiting_source(session=session, failure=failure, now=now)

            resolution_id = uuid4()
            reason_code = (
                "OPERATOR_REPLAY"
                if action is OperationalFailureAction.REPLAYED
                else "OPERATOR_CANCELLED"
            )
            content_hash = _resolution_hash(
                resolution_id=resolution_id,
                tenant_id=tenant_uuid,
                failure_id=failure_uuid,
                action=action,
                actor_id=actor_uuid,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                reason_code=reason_code,
                recovery_run_id=recovery_run.id if recovery_run is not None else None,
                correlation_id=correlation_id,
                created_at=now,
            )
            resolution = OperationalFailureResolutionModel(
                id=resolution_id,
                tenant_id=tenant_uuid,
                failure_id=failure_uuid,
                action=action.value,
                actor_id=actor_uuid,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                reason_code=reason_code,
                recovery_run_id=recovery_run.id if recovery_run is not None else None,
                correlation_id=correlation_id,
                content_hash=content_hash,
                created_at=now,
            )
            session.add(resolution)
            session.flush()
            return OperationalFailureResolutionResult(
                failure_id=str(failure_uuid),
                action=action,
                recovery_run_id=(str(recovery_run.id) if recovery_run is not None else None),
                recovery_event_id=(str(recovery_event.id) if recovery_event is not None else None),
                created_at=now,
                idempotent_replay=False,
            )

    def _existing_resolution(
        self,
        *,
        session: Session,
        existing: OperationalFailureResolutionModel,
        requested_action: OperationalFailureAction,
        idempotency_key: str,
        request_hash: str,
    ) -> OperationalFailureResolutionResult:
        if existing.idempotency_key == idempotency_key and existing.request_hash != request_hash:
            raise IdempotencyKeyReusedError()
        if (
            existing.idempotency_key != idempotency_key
            or existing.action != requested_action.value
            or existing.request_hash != request_hash
        ):
            raise OperationalFailureAlreadyResolvedError()
        recovery_event_id: str | None = None
        if existing.recovery_run_id is not None:
            recovery_event = session.scalar(
                select(OperationalFailureRecoveryEventModel).where(
                    OperationalFailureRecoveryEventModel.tenant_id == existing.tenant_id,
                    OperationalFailureRecoveryEventModel.recovery_run_id
                    == existing.recovery_run_id,
                )
            )
            if recovery_event is not None:
                recovery_event_id = str(recovery_event.id)
        return OperationalFailureResolutionResult(
            failure_id=str(existing.failure_id),
            action=OperationalFailureAction(existing.action),
            recovery_run_id=(
                str(existing.recovery_run_id) if existing.recovery_run_id is not None else None
            ),
            recovery_event_id=recovery_event_id,
            created_at=existing.created_at,
            idempotent_replay=True,
        )

    def _now(self) -> datetime:
        value = self._now_factory()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("failure recovery clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


def _recovery_envelope(
    *,
    session: Session,
    failure: OperationalFailureModel,
) -> tuple[str, dict[str, object]]:
    if failure.source_table == "outbox_events":
        source = session.scalar(
            select(OutboxEventModel)
            .where(
                OutboxEventModel.tenant_id == failure.tenant_id,
                OutboxEventModel.id == failure.source_event_id,
            )
            .with_for_update()
        )
        if (
            source is None
            or source.status != "FAILED"
            or source.last_error != _ANALYSIS_DISPATCH_ERROR
        ):
            raise OperationalFailureNotReplayableError()
        raw = source.payload
        payload: dict[str, object] = {
            "event_id": _required_uuid_text(raw, "event_id"),
            "tenant_id": _required_uuid_text(raw, "tenant_id"),
            "case_id": _required_uuid_text(raw, "case_id"),
            "analysis_run_id": _required_uuid_text(raw, "analysis_run_id"),
            "stage_run_id": _required_uuid_text(raw, "stage_run_id"),
            "correlation_id": _required_text(raw, "correlation_id"),
        }
        if payload["event_id"] != str(source.id) or payload["tenant_id"] != str(source.tenant_id):
            raise OperationalFailureNotReplayableError()
        return "analysis.requested.v1", payload

    spec = _SOURCE_SPECS.get(failure.source_table)
    if spec is None:
        raise OperationalFailureNotReplayableError()
    source = session.scalar(
        select(spec.model)
        .where(
            spec.model.tenant_id == failure.tenant_id,
            spec.model.id == failure.source_event_id,
        )
        .with_for_update()
    )
    if source is None or source.status != "FAILED" or source.failure_code != spec.dispatch_code:
        raise OperationalFailureNotReplayableError()
    run_id = getattr(source, spec.run_attribute)
    payload: dict[str, object] = {
        "event_id": str(source.id),
        "tenant_id": str(source.tenant_id),
        "case_id": str(source.case_id),
        spec.queue_key: str(run_id),
        "correlation_id": source.correlation_id,
    }
    _validate_identifier_payload(payload)
    return spec.topic, payload


def _cancel_awaiting_source(
    *,
    session: Session,
    failure: OperationalFailureModel,
    now: datetime,
) -> None:
    """Terminalize only an execution that never crossed the failed dispatch boundary."""

    if failure.failure_kind != "DISPATCH":
        return
    if failure.pipeline == "analysis":
        if failure.source_stage_id is None or failure.source_run_id is None:
            return
        stage = session.scalar(
            select(AnalysisStageRunModel)
            .where(
                AnalysisStageRunModel.tenant_id == failure.tenant_id,
                AnalysisStageRunModel.analysis_run_id == failure.source_run_id,
                AnalysisStageRunModel.id == failure.source_stage_id,
            )
            .with_for_update()
        )
        if stage is None or stage.status not in {"QUEUED", "RETRY_WAITING"}:
            return
        stage.status = "FAILED"
        stage.started_at = stage.started_at or now
        stage.completed_at = now
        stage.next_attempt_at = None
        stage.claim_token = None
        stage.lease_expires_at = None
        stage.failure_code = _CANCEL_FAILURE_CODE
        stage.failure_message = _CANCEL_FAILURE_MESSAGE
        stage.failure_retryable = False
        session.flush()
        _reconcile_analysis_run(session=session, failure=failure, now=now)
        return

    run_model: type[Any] | None = {
        "policy_retrieval": PolicyRetrievalRunModel,
        "grounded_explanation": GroundedExplanationRunModel,
        "policy_evaluation": PolicyEvaluationRunModel,
    }.get(failure.pipeline)
    if run_model is None or failure.source_run_id is None:
        return
    run = session.scalar(
        select(run_model)
        .where(
            run_model.tenant_id == failure.tenant_id,
            run_model.id == failure.source_run_id,
        )
        .with_for_update()
    )
    if run is None or run.status != "QUEUED":
        return
    run.status = "FAILED"
    run.started_at = run.started_at or now
    run.completed_at = now
    run.failure_code = _CANCEL_FAILURE_CODE
    run.failure_message = _CANCEL_FAILURE_MESSAGE
    run.claim_token = None
    run.lease_expires_at = None


def _reconcile_analysis_run(
    *,
    session: Session,
    failure: OperationalFailureModel,
    now: datetime,
) -> None:
    assert failure.source_run_id is not None
    run = session.scalar(
        select(AnalysisRunModel)
        .where(
            AnalysisRunModel.tenant_id == failure.tenant_id,
            AnalysisRunModel.id == failure.source_run_id,
        )
        .with_for_update()
    )
    if run is None or run.status in {"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"}:
        return
    statuses = tuple(
        session.scalars(
            select(AnalysisStageRunModel.status).where(
                AnalysisStageRunModel.tenant_id == failure.tenant_id,
                AnalysisStageRunModel.analysis_run_id == failure.source_run_id,
            )
        ).all()
    )
    if not statuses:
        return
    if any(status in {"QUEUED", "RUNNING"} for status in statuses):
        target = "RUNNING"
    elif "RETRY_WAITING" in statuses:
        target = "RETRY_WAITING"
    elif all(status == "FAILED" for status in statuses):
        target = "FAILED"
    elif all(status == "SUCCEEDED" for status in statuses):
        target = "SUCCEEDED"
    else:
        target = "PARTIAL_SUCCESS"
    run.status = target
    run.started_at = run.started_at or now
    if target in {"FAILED", "SUCCEEDED", "PARTIAL_SUCCESS"}:
        run.completed_at = now
    if target == "FAILED":
        run.failure_code = _CANCEL_FAILURE_CODE
        run.failure_message = _CANCEL_FAILURE_MESSAGE
        run.failure_retryable = False


def _to_failure_record(
    failure: OperationalFailureModel,
    resolution: OperationalFailureResolutionModel | None,
    recovery_event: OperationalFailureRecoveryEventModel | None,
) -> OperationalFailureRecord:
    if resolution is None:
        status = OperationalFailureStatus.OPEN
    else:
        status = OperationalFailureStatus(resolution.action)
    return OperationalFailureRecord(
        failure_id=str(failure.id),
        pipeline=OperationalFailurePipeline(failure.pipeline),
        failure_kind=OperationalFailureKind(failure.failure_kind),
        failure_code=failure.failure_code,
        source_event_id=str(failure.source_event_id),
        source_run_id=str(failure.source_run_id) if failure.source_run_id is not None else None,
        source_stage_id=(
            str(failure.source_stage_id) if failure.source_stage_id is not None else None
        ),
        correlation_id=failure.correlation_id,
        replayable=failure.replayable,
        status=status,
        occurred_at=failure.occurred_at,
        resolved_at=resolution.created_at if resolution is not None else None,
        recovery_run_id=(
            str(resolution.recovery_run_id)
            if resolution is not None and resolution.recovery_run_id is not None
            else None
        ),
        recovery_event_id=str(recovery_event.id) if recovery_event is not None else None,
    )


def _request_hash(*, failure_uuid: UUID, action: OperationalFailureAction) -> str:
    return _stable_hash(
        {
            "schema_version": "operational_failure_resolution/1.0.0",
            "failure_id": str(failure_uuid),
            "action": action.value,
        }
    )


def _resolution_hash(**values: object) -> str:
    canonical = {
        key: value.isoformat()
        if isinstance(value, datetime)
        else str(value)
        if isinstance(value, UUID)
        else value
        for key, value in values.items()
    }
    canonical["schema_version"] = "operational_failure_resolution/1.0.0"
    return _stable_hash(canonical)


def _stable_hash(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise OperationalFailureNotReplayableError()
    return value


def _required_uuid_text(payload: Mapping[str, object], key: str) -> str:
    value = _required_text(payload, key)
    try:
        return str(UUID(value))
    except ValueError as error:
        raise OperationalFailureNotReplayableError() from error


def _validate_identifier_payload(payload: Mapping[str, object]) -> None:
    for key, value in payload.items():
        if key == "correlation_id":
            if not isinstance(value, str) or not 1 <= len(value) <= 128:
                raise OperationalFailureNotReplayableError()
            continue
        if not isinstance(value, str):
            raise OperationalFailureNotReplayableError()
        try:
            UUID(value)
        except ValueError as error:
            raise OperationalFailureNotReplayableError() from error


def _encode_cursor(occurred_at: datetime, failure_id: UUID) -> str:
    payload = json.dumps(
        [occurred_at.astimezone(UTC).isoformat(), str(failure_id)],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, UUID]:
    if not value or len(value) > _MAX_CURSOR_BYTES:
        raise ValidationError("Operations failure cursor is invalid.")
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode())
        raw = json.loads(decoded)
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError
        occurred_at = datetime.fromisoformat(str(raw[0]))
        failure_id = UUID(str(raw[1]))
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValidationError("Operations failure cursor is invalid.") from error
    return occurred_at.astimezone(UTC), failure_id


def _uuid_or_validation(value: str, label: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise ValidationError(f"The {label} is invalid.") from error


def _uuid_or_not_found(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise OperationalFailureNotFoundError() from error


__all__ = ["SQLAlchemyOperationalFailureRepository"]
