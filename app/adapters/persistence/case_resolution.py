"""SQLAlchemy adapter for Case Resolution and deterministic Action simulations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.async_events import (
    begin_consumer_attempt,
    mark_event_consumed,
    mark_event_failed,
    record_rejected_dispatch_recovery,
    recover_dispatch_failure,
    validate_request_event,
)
from app.adapters.persistence.human_review import verify_human_decision_integrity
from app.adapters.persistence.models import (
    CaseModel,
    CaseResolutionEventModel,
    CaseResolutionModel,
    CaseResolutionRequestEventModel,
    ExternalActionIntentModel,
    ExternalActionSimulationAttemptModel,
    ExternalActionSimulationRequestEventModel,
    ExternalActionSimulationResultModel,
    HumanReviewTaskModel,
)
from app.platform.async_reliability import (
    AsyncEventIntegrityError,
    ExecutionAttemptsExhaustedError,
    ExecutionLeaseActiveError,
)
from app.platform.case_resolution import (
    ACTION_MAPPING_NAME,
    ACTION_MAPPING_VERSION,
    SIMULATION_RESULT_SCHEMA_VERSION,
    CaseResolution,
    CaseResolutionEvent,
    CaseResolutionIntegrityError,
    ExternalActionIntent,
    ExternalActionIntentDetail,
    ExternalActionMode,
    ExternalActionSimulationAttempt,
    ExternalActionSimulationResult,
    ResolutionStatus,
    SimulationAdapterResult,
    SimulationAttemptStatus,
    SimulationClaim,
    SimulationOutcome,
    action_intent_hash_payload,
    assess_action_input,
    canonical_hash,
)
from app.platform.human_review import HumanDecisionType, ReviewPacketIntegrityError

CASE_RESOLUTION_DISPATCH_FAILURE = "CASE_RESOLUTION_OUTBOX_FAILED"
SIMULATION_DISPATCH_FAILURE = "EXTERNAL_ACTION_SIMULATION_OUTBOX_FAILED"


class SQLAlchemyCaseResolutionRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        lease_ttl: timedelta = timedelta(minutes=5),
        max_execution_attempts: int = 4,
    ) -> None:
        if lease_ttl.total_seconds() <= 0:
            raise ValueError("lease_ttl must be positive")
        if max_execution_attempts < 1:
            raise ValueError("max_execution_attempts must be positive")
        self._factory = session_factory
        self._lease_ttl = lease_ttl
        self._max_execution_attempts = max_execution_attempts

    def process_requested(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        resolution_id: str,
        correlation_id: str,
    ) -> str:
        deferred: Exception | None = None
        disposition = "NOOP"
        now = datetime.now(UTC)
        event_uuid = UUID(event_id)
        tenant_uuid = UUID(tenant_id)
        case_uuid = UUID(case_id)
        resolution_uuid = UUID(resolution_id)
        with self._factory.begin() as session:
            event = session.scalar(
                select(CaseResolutionRequestEventModel)
                .where(CaseResolutionRequestEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None:
                deferred = AsyncEventIntegrityError(
                    code="CASE_RESOLUTION_EVENT_NOT_FOUND",
                    message="The Case Resolution request event was not found.",
                )
            else:
                exact_identity = _event_identity_matches(
                    event,
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    aggregate_id=resolution_uuid,
                    aggregate_attribute="resolution_id",
                    correlation_id=correlation_id,
                )
                if (
                    exact_identity
                    and event.status == "FAILED"
                    and event.failure_code == CASE_RESOLUTION_DISPATCH_FAILURE
                ):
                    recover_dispatch_failure(
                        event,
                        now=now,
                        dispatch_failure_code=CASE_RESOLUTION_DISPATCH_FAILURE,
                    )
                error = validate_request_event(
                    event,
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    correlation_id=correlation_id,
                    run_id=resolution_uuid,
                    run_attribute="resolution_id",
                )
                if event.status == "CONSUMED" and exact_identity:
                    disposition = "NOOP"
                elif error is not None:
                    begin_consumer_attempt(event)
                    if (
                        event.status == "FAILED"
                        and event.failure_code == CASE_RESOLUTION_DISPATCH_FAILURE
                    ):
                        record_rejected_dispatch_recovery(event, message=str(error))
                    elif event.status != "FAILED":
                        mark_event_failed(
                            event,
                            now=now,
                            code=error.code,
                            message=str(error),
                        )
                    _fail_resolution_for_event(
                        session,
                        event=event,
                        now=now,
                        code=error.code,
                        message=str(error),
                    )
                    deferred = error
                else:
                    begin_consumer_attempt(event)
                    resolution = session.scalar(
                        select(CaseResolutionModel)
                        .where(
                            CaseResolutionModel.tenant_id == event.tenant_id,
                            CaseResolutionModel.case_id == event.case_id,
                            CaseResolutionModel.id == event.resolution_id,
                        )
                        .with_for_update()
                    )
                    if resolution is None:
                        error = CaseResolutionIntegrityError(
                            "The durable request references a missing Resolution."
                        )
                        mark_event_failed(
                            event,
                            now=now,
                            code=error.code,
                            message=str(error),
                        )
                        deferred = error
                    else:
                        outcome = self._apply_resolution_request(
                            session,
                            event=event,
                            resolution=resolution,
                            now=now,
                        )
                        if isinstance(outcome, Exception):
                            mark_event_failed(
                                event,
                                now=now,
                                code=str(
                                    getattr(
                                        outcome,
                                        "code",
                                        "CASE_RESOLUTION_INTEGRITY_FAILED",
                                    )
                                ),
                                message=str(outcome),
                            )
                            _transition_resolution(
                                session,
                                resolution=resolution,
                                to_status=ResolutionStatus.MANUAL_FOLLOW_UP_REQUIRED,
                                now=now,
                                human_decision_id=event.human_decision_id,
                                payload={
                                    "failure_code": getattr(outcome, "code", "INTEGRITY_FAILED")
                                },
                                failure_code=str(
                                    getattr(outcome, "code", "CASE_RESOLUTION_INTEGRITY_FAILED")
                                ),
                                failure_message=str(outcome),
                            )
                            deferred = outcome
                        else:
                            mark_event_consumed(event, now=now)
                            disposition = outcome
        if deferred is not None:
            raise deferred
        return disposition

    def _apply_resolution_request(
        self,
        session: Session,
        *,
        event: CaseResolutionRequestEventModel,
        resolution: CaseResolutionModel,
        now: datetime,
    ) -> str | Exception:
        try:
            decision = verify_human_decision_integrity(
                session,
                tenant_id=event.tenant_id,
                decision_id=event.human_decision_id,
            )
        except ReviewPacketIntegrityError as error:
            return CaseResolutionIntegrityError(str(error))
        task = session.scalar(
            select(HumanReviewTaskModel).where(
                HumanReviewTaskModel.tenant_id == event.tenant_id,
                HumanReviewTaskModel.id == decision.review_task_id,
                HumanReviewTaskModel.case_id == event.case_id,
                HumanReviewTaskModel.status == "RESOLVED",
            )
        )
        if task is None:
            return CaseResolutionIntegrityError(
                "The Human Decision is not attached to a resolved task for this Case."
            )

        if resolution.source_human_decision_id != decision.id:
            _abort_active_simulation_for_conflict(session, resolution=resolution, now=now)
            _transition_resolution(
                session,
                resolution=resolution,
                to_status=ResolutionStatus.MANUAL_FOLLOW_UP_REQUIRED,
                now=now,
                human_decision_id=decision.id,
                payload={
                    "reason": "DIFFERENT_SECOND_HUMAN_DECISION",
                    "original_human_decision_id": str(resolution.source_human_decision_id),
                    "conflicting_human_decision_id": str(decision.id),
                },
                failure_code="HUMAN_DECISION_CONFLICT",
                failure_message="A different second Human Decision requires manual follow-up.",
            )
            return "MANUAL_FOLLOW_UP_REQUIRED"

        if resolution.status != ResolutionStatus.DECISION_RECORDED.value:
            return "NOOP"

        case = session.scalar(
            select(CaseModel).where(
                CaseModel.tenant_id == event.tenant_id,
                CaseModel.id == event.case_id,
            )
        )
        if case is None:
            return CaseResolutionIntegrityError("The source Case is missing.")
        assessment = assess_action_input(
            decision=HumanDecisionType(decision.decision_type),
            order_ref=case.order_ref,
            product_ref=case.product_ref,
            attributes=case.attributes,
        )
        if assessment.terminal_status is not None:
            _transition_resolution(
                session,
                resolution=resolution,
                to_status=assessment.terminal_status,
                now=now,
                human_decision_id=decision.id,
                payload={
                    "mapping_name": ACTION_MAPPING_NAME,
                    "mapping_version": ACTION_MAPPING_VERSION,
                    "missing_fields": list(assessment.missing_fields),
                    "invalid_fields": list(assessment.invalid_fields),
                },
                missing_fields=assessment.missing_fields,
                invalid_fields=assessment.invalid_fields,
            )
            return assessment.terminal_status.value

        assert assessment.action_type is not None
        intent_id = uuid4()
        intent = ExternalActionIntent(
            id=str(intent_id),
            tenant_id=str(event.tenant_id),
            case_id=str(event.case_id),
            resolution_id=str(resolution.id),
            human_decision_id=str(decision.id),
            action_type=assessment.action_type,
            order_ref=str(assessment.values["order_ref"]),
            product_ref=_optional_string(assessment.values.get("product_ref")),
            amount=_canonical_amount(assessment.values.get("amount")),
            currency=_optional_string(assessment.values.get("currency")),
            quantity=_optional_integer(assessment.values.get("quantity")),
            shipping_address_ref=_optional_string(assessment.values.get("shipping_address_ref")),
            content_hash="0" * 64,
            created_at=now,
        )
        intent = intent.model_copy(
            update={"content_hash": canonical_hash(action_intent_hash_payload(intent))}
        )
        session.add(
            ExternalActionIntentModel(
                id=intent_id,
                tenant_id=event.tenant_id,
                case_id=event.case_id,
                resolution_id=resolution.id,
                human_decision_id=decision.id,
                action_type=intent.action_type.value,
                mode=intent.mode,
                order_ref=intent.order_ref,
                product_ref=intent.product_ref,
                amount=Decimal(intent.amount) if intent.amount is not None else None,
                currency=intent.currency,
                quantity=intent.quantity,
                shipping_address_ref=intent.shipping_address_ref,
                mapping_name=intent.mapping_name,
                mapping_version=intent.mapping_version,
                intent_schema_version=intent.intent_schema_version,
                content_hash=intent.content_hash,
                created_at=now,
            )
        )
        session.flush()
        _transition_resolution(
            session,
            resolution=resolution,
            to_status=ResolutionStatus.ACTION_READY,
            now=now,
            human_decision_id=decision.id,
            external_action_intent_id=intent_id,
            payload={
                "action_type": intent.action_type.value,
                "mode": intent.mode,
                "mapping_name": ACTION_MAPPING_NAME,
                "mapping_version": ACTION_MAPPING_VERSION,
            },
        )
        session.add(
            ExternalActionSimulationRequestEventModel(
                id=uuid4(),
                tenant_id=event.tenant_id,
                case_id=event.case_id,
                external_action_intent_id=intent_id,
                correlation_id=event.correlation_id,
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
        return "ACTION_READY"

    def record_resolution_failure(
        self,
        *,
        event_id: str,
        code: str,
        message: str,
    ) -> None:
        now = datetime.now(UTC)
        try:
            event_uuid = UUID(event_id)
        except ValueError:
            return
        with self._factory.begin() as session:
            event = session.scalar(
                select(CaseResolutionRequestEventModel)
                .where(CaseResolutionRequestEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None or event.status in {"CONSUMED", "FAILED"}:
                return
            begin_consumer_attempt(event)
            mark_event_failed(event, now=now, code=code, message=message)
            _fail_resolution_for_event(
                session,
                event=event,
                now=now,
                code=code,
                message=message,
            )

    def prepare_simulation(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        external_action_intent_id: str,
        correlation_id: str,
    ) -> SimulationClaim | None:
        now = datetime.now(UTC)
        deferred: Exception | None = None
        claim: SimulationClaim | None = None
        event_uuid = UUID(event_id)
        tenant_uuid = UUID(tenant_id)
        case_uuid = UUID(case_id)
        intent_uuid = UUID(external_action_intent_id)
        with self._factory.begin() as session:
            event = session.scalar(
                select(ExternalActionSimulationRequestEventModel)
                .where(ExternalActionSimulationRequestEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None:
                deferred = AsyncEventIntegrityError(
                    code="EXTERNAL_ACTION_SIMULATION_EVENT_NOT_FOUND",
                    message="The external Action simulation request event was not found.",
                )
            else:
                exact_identity = _event_identity_matches(
                    event,
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    aggregate_id=intent_uuid,
                    aggregate_attribute="external_action_intent_id",
                    correlation_id=correlation_id,
                )
                if (
                    exact_identity
                    and event.status == "FAILED"
                    and event.failure_code == SIMULATION_DISPATCH_FAILURE
                ):
                    recover_dispatch_failure(
                        event,
                        now=now,
                        dispatch_failure_code=SIMULATION_DISPATCH_FAILURE,
                    )
                error = validate_request_event(
                    event,
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    correlation_id=correlation_id,
                    run_id=intent_uuid,
                    run_attribute="external_action_intent_id",
                )
                if event.status == "CONSUMED" and exact_identity:
                    claim = None
                elif error is not None:
                    begin_consumer_attempt(event)
                    if (
                        event.status == "FAILED"
                        and event.failure_code == SIMULATION_DISPATCH_FAILURE
                    ):
                        record_rejected_dispatch_recovery(event, message=str(error))
                    elif event.status != "FAILED":
                        mark_event_failed(event, now=now, code=error.code, message=str(error))
                    deferred = error
                else:
                    begin_consumer_attempt(event)
                    intent_row = session.scalar(
                        select(ExternalActionIntentModel).where(
                            ExternalActionIntentModel.tenant_id == event.tenant_id,
                            ExternalActionIntentModel.case_id == event.case_id,
                            ExternalActionIntentModel.id == event.external_action_intent_id,
                        )
                    )
                    if intent_row is None:
                        error = CaseResolutionIntegrityError(
                            "The simulation event references a missing Action Intent."
                        )
                        mark_event_failed(event, now=now, code=error.code, message=str(error))
                        deferred = error
                    else:
                        resolution = session.scalar(
                            select(CaseResolutionModel)
                            .where(
                                CaseResolutionModel.tenant_id == intent_row.tenant_id,
                                CaseResolutionModel.case_id == intent_row.case_id,
                                CaseResolutionModel.id == intent_row.resolution_id,
                            )
                            .with_for_update()
                        )
                        if resolution is None:
                            error = CaseResolutionIntegrityError(
                                "The Action Intent references a missing Resolution."
                            )
                            mark_event_failed(event, now=now, code=error.code, message=str(error))
                            deferred = error
                        else:
                            claim, deferred = self._claim_simulation(
                                session,
                                event=event,
                                resolution=resolution,
                                intent_row=intent_row,
                                now=now,
                            )
        if deferred is not None:
            raise deferred
        return claim

    def _claim_simulation(
        self,
        session: Session,
        *,
        event: ExternalActionSimulationRequestEventModel,
        resolution: CaseResolutionModel,
        intent_row: ExternalActionIntentModel,
        now: datetime,
    ) -> tuple[SimulationClaim | None, Exception | None]:
        try:
            intent = _verified_intent(intent_row)
        except CaseResolutionIntegrityError as error:
            mark_event_failed(event, now=now, code=error.code, message=str(error))
            _transition_resolution(
                session,
                resolution=resolution,
                to_status=ResolutionStatus.ACTION_DRY_RUN_FAILED,
                now=now,
                human_decision_id=intent_row.human_decision_id,
                external_action_intent_id=intent_row.id,
                payload={"failure_code": error.code},
                failure_code=error.code,
                failure_message=str(error),
            )
            return None, error

        existing_result = session.scalar(
            select(ExternalActionSimulationResultModel).where(
                ExternalActionSimulationResultModel.tenant_id == event.tenant_id,
                ExternalActionSimulationResultModel.external_action_intent_id == intent_row.id,
            )
        )
        if existing_result is not None:
            _verify_result(existing_result)
            mark_event_consumed(event, now=now)
            return None, None
        if resolution.source_human_decision_id != intent_row.human_decision_id:
            error = CaseResolutionIntegrityError(
                "The Action Intent does not belong to the Resolution source decision."
            )
            mark_event_failed(event, now=now, code=error.code, message=str(error))
            return None, error
        if resolution.status not in {
            ResolutionStatus.ACTION_READY.value,
            ResolutionStatus.ACTION_DRY_RUN_PENDING.value,
        }:
            mark_event_consumed(event, now=now)
            return None, None
        if (
            resolution.status == ResolutionStatus.ACTION_DRY_RUN_PENDING.value
            and resolution.lease_expires_at is not None
            and resolution.lease_expires_at > now
        ):
            return None, ExecutionLeaseActiveError(retry_at=resolution.lease_expires_at)
        if resolution.execution_attempt_count >= self._max_execution_attempts:
            code = "EXTERNAL_ACTION_SIMULATION_EXECUTION_EXHAUSTED"
            _transition_resolution(
                session,
                resolution=resolution,
                to_status=ResolutionStatus.ACTION_DRY_RUN_FAILED,
                now=now,
                human_decision_id=intent_row.human_decision_id,
                external_action_intent_id=intent_row.id,
                payload={"failure_code": code},
                failure_code=code,
                failure_message="Simulation exhausted bounded worker-loss recovery attempts.",
            )
            mark_event_failed(
                event,
                now=now,
                code=code,
                message="Simulation exhausted bounded worker-loss recovery attempts.",
            )
            return None, ExecutionAttemptsExhaustedError(code=code)

        previous_attempt = session.scalar(
            select(ExternalActionSimulationAttemptModel)
            .where(
                ExternalActionSimulationAttemptModel.tenant_id == resolution.tenant_id,
                ExternalActionSimulationAttemptModel.external_action_intent_id == intent_row.id,
                ExternalActionSimulationAttemptModel.status == "RUNNING",
            )
            .order_by(ExternalActionSimulationAttemptModel.attempt_number.desc())
            .with_for_update()
        )
        if previous_attempt is not None:
            previous_attempt.status = "FAILED"
            previous_attempt.completed_at = now
            previous_attempt.failure_code = "SIMULATION_WORKER_LEASE_EXPIRED"
            previous_attempt.failure_message = "The previous simulation worker lease expired."
        token = uuid4()
        attempt_id = uuid4()
        attempt_number = resolution.execution_attempt_count + 1
        session.add(
            ExternalActionSimulationAttemptModel(
                id=attempt_id,
                tenant_id=resolution.tenant_id,
                case_id=resolution.case_id,
                resolution_id=resolution.id,
                external_action_intent_id=intent_row.id,
                attempt_number=attempt_number,
                execution_token=token,
                status=SimulationAttemptStatus.RUNNING.value,
                mode=ExternalActionMode.DRY_RUN.value,
                started_at=now,
                completed_at=None,
                failure_code=None,
                failure_message=None,
                created_at=now,
            )
        )
        _transition_resolution(
            session,
            resolution=resolution,
            to_status=ResolutionStatus.ACTION_DRY_RUN_PENDING,
            now=now,
            human_decision_id=intent_row.human_decision_id,
            external_action_intent_id=intent_row.id,
            payload={"attempt_number": attempt_number, "mode": "DRY_RUN"},
        )
        resolution.execution_attempt_count = attempt_number
        resolution.claim_token = token
        resolution.lease_expires_at = now + self._lease_ttl
        return (
            SimulationClaim(
                event_id=str(event.id),
                tenant_id=str(event.tenant_id),
                case_id=str(event.case_id),
                resolution_id=str(resolution.id),
                intent=intent,
                attempt_id=str(attempt_id),
                execution_token=str(token),
                correlation_id=event.correlation_id,
            ),
            None,
        )

    def complete_simulation(
        self,
        *,
        claim: SimulationClaim,
        result: SimulationAdapterResult,
    ) -> str:
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            event = session.scalar(
                select(ExternalActionSimulationRequestEventModel)
                .where(ExternalActionSimulationRequestEventModel.id == UUID(claim.event_id))
                .with_for_update()
            )
            if event is None:
                return "NOOP"
            intent_row = session.scalar(
                select(ExternalActionIntentModel).where(
                    ExternalActionIntentModel.tenant_id == UUID(claim.tenant_id),
                    ExternalActionIntentModel.id == UUID(claim.intent.id),
                )
            )
            resolution = session.scalar(
                select(CaseResolutionModel)
                .where(
                    CaseResolutionModel.tenant_id == UUID(claim.tenant_id),
                    CaseResolutionModel.case_id == UUID(claim.case_id),
                    CaseResolutionModel.id == UUID(claim.resolution_id),
                )
                .with_for_update()
            )
            if intent_row is None or resolution is None:
                return "NOOP"
            _verified_intent(intent_row)
            token = UUID(claim.execution_token)
            if (
                resolution.status != ResolutionStatus.ACTION_DRY_RUN_PENDING.value
                or resolution.claim_token != token
                or intent_row.id != event.external_action_intent_id
            ):
                return "NOOP"
            if event.status == "FAILED" and event.failure_code == SIMULATION_DISPATCH_FAILURE:
                recover_dispatch_failure(
                    event,
                    now=now,
                    dispatch_failure_code=SIMULATION_DISPATCH_FAILURE,
                )
            if event.status not in {"PROCESSING", "PUBLISHED"}:
                return "NOOP"
            existing = session.scalar(
                select(ExternalActionSimulationResultModel).where(
                    ExternalActionSimulationResultModel.tenant_id == resolution.tenant_id,
                    ExternalActionSimulationResultModel.external_action_intent_id == intent_row.id,
                )
            )
            if existing is not None:
                _verify_result(existing)
                mark_event_consumed(event, now=now)
                return "NOOP"
            attempt = session.scalar(
                select(ExternalActionSimulationAttemptModel).where(
                    ExternalActionSimulationAttemptModel.tenant_id == resolution.tenant_id,
                    ExternalActionSimulationAttemptModel.id == UUID(claim.attempt_id),
                    ExternalActionSimulationAttemptModel.execution_token == token,
                    ExternalActionSimulationAttemptModel.status == "RUNNING",
                )
            )
            if attempt is None:
                return "NOOP"
            outcome = result.outcome
            failure_code = result.failure_code
            failure_message = result.failure_message
            if result.side_effects_performed:
                outcome = SimulationOutcome.FAILED
                failure_code = "SIDE_EFFECT_CONTRACT_VIOLATED"
                failure_message = "A DRY-RUN adapter reported an external side effect."
            if outcome is SimulationOutcome.FAILED:
                failure_code = failure_code or "EXTERNAL_ACTION_SIMULATION_FAILED"
                failure_message = failure_message or "The deterministic simulation failed."
            result_id = uuid4()
            hash_payload = {
                "id": str(result_id),
                "tenant_id": claim.tenant_id,
                "case_id": claim.case_id,
                "resolution_id": claim.resolution_id,
                "external_action_intent_id": claim.intent.id,
                "simulation_attempt_id": claim.attempt_id,
                "outcome": outcome.value,
                "mode": result.mode.value,
                "side_effects_performed": False,
                "failure_code": failure_code,
                "failure_message": failure_message,
                "simulated_request": result.simulated_request,
                "simulated_response": result.simulated_response,
                "result_schema_version": SIMULATION_RESULT_SCHEMA_VERSION,
                "created_at": now.isoformat(),
            }
            session.add(
                ExternalActionSimulationResultModel(
                    id=result_id,
                    tenant_id=resolution.tenant_id,
                    case_id=resolution.case_id,
                    resolution_id=resolution.id,
                    external_action_intent_id=intent_row.id,
                    simulation_attempt_id=attempt.id,
                    outcome=outcome.value,
                    mode=result.mode.value,
                    side_effects_performed=False,
                    failure_code=failure_code,
                    failure_message=failure_message,
                    simulated_request=result.simulated_request,
                    simulated_response=result.simulated_response,
                    result_schema_version=SIMULATION_RESULT_SCHEMA_VERSION,
                    content_hash=canonical_hash(hash_payload),
                    created_at=now,
                )
            )
            attempt.status = (
                SimulationAttemptStatus.SUCCEEDED.value
                if outcome is SimulationOutcome.VALIDATED
                else SimulationAttemptStatus.FAILED.value
            )
            attempt.completed_at = now
            attempt.failure_code = failure_code
            attempt.failure_message = failure_message
            target = (
                ResolutionStatus.ACTION_DRY_RUN_VALIDATED
                if outcome is SimulationOutcome.VALIDATED
                else ResolutionStatus.ACTION_DRY_RUN_FAILED
            )
            resolution.claim_token = None
            resolution.lease_expires_at = None
            _transition_resolution(
                session,
                resolution=resolution,
                to_status=target,
                now=now,
                human_decision_id=intent_row.human_decision_id,
                external_action_intent_id=intent_row.id,
                payload={
                    "simulation_result_id": str(result_id),
                    "outcome": outcome.value,
                    "side_effects_performed": False,
                    "failure_code": failure_code,
                },
                failure_code=failure_code,
                failure_message=failure_message,
            )
            mark_event_consumed(event, now=now)
            return target.value

    def record_simulation_failure(
        self,
        *,
        event_id: str,
        code: str,
        message: str,
        expected_execution_token: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        try:
            event_uuid = UUID(event_id)
            expected_token = (
                UUID(expected_execution_token) if expected_execution_token is not None else None
            )
        except ValueError:
            return
        with self._factory.begin() as session:
            event = session.scalar(
                select(ExternalActionSimulationRequestEventModel)
                .where(ExternalActionSimulationRequestEventModel.id == event_uuid)
                .with_for_update()
            )
            if event is None or event.status in {"CONSUMED", "FAILED"}:
                return
            intent = session.scalar(
                select(ExternalActionIntentModel).where(
                    ExternalActionIntentModel.tenant_id == event.tenant_id,
                    ExternalActionIntentModel.id == event.external_action_intent_id,
                )
            )
            resolution = (
                session.scalar(
                    select(CaseResolutionModel)
                    .where(
                        CaseResolutionModel.tenant_id == intent.tenant_id,
                        CaseResolutionModel.id == intent.resolution_id,
                    )
                    .with_for_update()
                )
                if intent is not None
                else None
            )
            if (
                resolution is not None
                and resolution.status == ResolutionStatus.ACTION_DRY_RUN_PENDING.value
                and resolution.lease_expires_at is not None
                and resolution.lease_expires_at > now
                and resolution.claim_token != expected_token
            ):
                event.consumer_last_error = (
                    "Ignored stale terminal recorder while a newer simulation lease is active."
                )
                return
            begin_consumer_attempt(event)
            mark_event_failed(event, now=now, code=code, message=message)
            if resolution is None or intent is None:
                return
            if resolution.status not in {
                ResolutionStatus.ACTION_READY.value,
                ResolutionStatus.ACTION_DRY_RUN_PENDING.value,
            }:
                return
            if resolution.status == ResolutionStatus.ACTION_DRY_RUN_PENDING.value:
                attempt = session.scalar(
                    select(ExternalActionSimulationAttemptModel).where(
                        ExternalActionSimulationAttemptModel.tenant_id == resolution.tenant_id,
                        ExternalActionSimulationAttemptModel.external_action_intent_id == intent.id,
                        ExternalActionSimulationAttemptModel.status == "RUNNING",
                    )
                )
                if attempt is not None:
                    attempt.status = "FAILED"
                    attempt.completed_at = now
                    attempt.failure_code = code
                    attempt.failure_message = message[:1000]
            resolution.claim_token = None
            resolution.lease_expires_at = None
            _transition_resolution(
                session,
                resolution=resolution,
                to_status=ResolutionStatus.ACTION_DRY_RUN_FAILED,
                now=now,
                human_decision_id=intent.human_decision_id,
                external_action_intent_id=intent.id,
                payload={"failure_code": code},
                failure_code=code,
                failure_message=message,
            )

    def get_resolution(self, *, tenant_id: str, case_id: str) -> CaseResolution | None:
        with self._factory() as session:
            row = session.scalar(
                select(CaseResolutionModel).where(
                    CaseResolutionModel.tenant_id == UUID(tenant_id),
                    CaseResolutionModel.case_id == UUID(case_id),
                )
            )
            return _to_resolution(row) if row is not None else None

    def list_events(self, *, tenant_id: str, case_id: str) -> tuple[CaseResolutionEvent, ...]:
        with self._factory() as session:
            rows = session.scalars(
                select(CaseResolutionEventModel)
                .where(
                    CaseResolutionEventModel.tenant_id == UUID(tenant_id),
                    CaseResolutionEventModel.case_id == UUID(case_id),
                )
                .order_by(CaseResolutionEventModel.sequence, CaseResolutionEventModel.id)
            ).all()
            return tuple(_to_event(row) for row in rows)

    def list_intents(self, *, tenant_id: str, case_id: str) -> tuple[ExternalActionIntent, ...]:
        with self._factory() as session:
            rows = session.scalars(
                select(ExternalActionIntentModel)
                .where(
                    ExternalActionIntentModel.tenant_id == UUID(tenant_id),
                    ExternalActionIntentModel.case_id == UUID(case_id),
                )
                .order_by(ExternalActionIntentModel.created_at, ExternalActionIntentModel.id)
            ).all()
            return tuple(_verified_intent(row) for row in rows)

    def get_intent(self, *, tenant_id: str, intent_id: str) -> ExternalActionIntentDetail | None:
        tenant_uuid = UUID(tenant_id)
        intent_uuid = UUID(intent_id)
        with self._factory() as session:
            row = session.scalar(
                select(ExternalActionIntentModel).where(
                    ExternalActionIntentModel.tenant_id == tenant_uuid,
                    ExternalActionIntentModel.id == intent_uuid,
                )
            )
            if row is None:
                return None
            intent = _verified_intent(row)
            attempt_rows = session.scalars(
                select(ExternalActionSimulationAttemptModel)
                .where(
                    ExternalActionSimulationAttemptModel.tenant_id == tenant_uuid,
                    ExternalActionSimulationAttemptModel.external_action_intent_id == intent_uuid,
                )
                .order_by(ExternalActionSimulationAttemptModel.attempt_number)
            ).all()
            result_rows = session.scalars(
                select(ExternalActionSimulationResultModel)
                .where(
                    ExternalActionSimulationResultModel.tenant_id == tenant_uuid,
                    ExternalActionSimulationResultModel.external_action_intent_id == intent_uuid,
                )
                .order_by(ExternalActionSimulationResultModel.created_at)
            ).all()
            return ExternalActionIntentDetail(
                intent=intent,
                attempts=tuple(_to_attempt(item) for item in attempt_rows),
                results=tuple(_to_result(item) for item in result_rows),
            )


def _event_identity_matches(
    event: object,
    *,
    tenant_id: UUID,
    case_id: UUID,
    aggregate_id: UUID,
    aggregate_attribute: str,
    correlation_id: str,
) -> bool:
    return (
        getattr(event, "tenant_id", None) == tenant_id
        and getattr(event, "case_id", None) == case_id
        and getattr(event, aggregate_attribute, None) == aggregate_id
        and getattr(event, "correlation_id", None) == correlation_id
    )


def _fail_resolution_for_event(
    session: Session,
    *,
    event: CaseResolutionRequestEventModel,
    now: datetime,
    code: str,
    message: str,
) -> None:
    resolution = session.scalar(
        select(CaseResolutionModel)
        .where(
            CaseResolutionModel.tenant_id == event.tenant_id,
            CaseResolutionModel.case_id == event.case_id,
            CaseResolutionModel.id == event.resolution_id,
        )
        .with_for_update()
    )
    if resolution is None or resolution.status != ResolutionStatus.DECISION_RECORDED.value:
        return
    _transition_resolution(
        session,
        resolution=resolution,
        to_status=ResolutionStatus.MANUAL_FOLLOW_UP_REQUIRED,
        now=now,
        human_decision_id=event.human_decision_id,
        payload={"failure_code": code},
        failure_code=code,
        failure_message=message,
    )


def _transition_resolution(
    session: Session,
    *,
    resolution: CaseResolutionModel,
    to_status: ResolutionStatus,
    now: datetime,
    human_decision_id: UUID | None,
    payload: dict[str, object],
    external_action_intent_id: UUID | None = None,
    missing_fields: tuple[str, ...] = (),
    invalid_fields: tuple[str, ...] = (),
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> None:
    from_status = resolution.status
    if from_status == to_status.value:
        return
    next_version = resolution.version + 1
    event = CaseResolutionEventModel(
        id=uuid4(),
        tenant_id=resolution.tenant_id,
        case_id=resolution.case_id,
        resolution_id=resolution.id,
        sequence=next_version,
        event_type=to_status.value,
        from_status=from_status,
        to_status=to_status.value,
        human_decision_id=human_decision_id,
        external_action_intent_id=external_action_intent_id,
        payload=payload,
        created_at=now,
    )
    session.add(event)
    resolution.status = to_status.value
    resolution.version = next_version
    resolution.missing_fields = list(missing_fields)
    resolution.invalid_fields = list(invalid_fields)
    resolution.failure_code = failure_code
    resolution.failure_message = failure_message[:1000] if failure_message else None
    resolution.updated_at = now
    from app.adapters.persistence.poc_reporting import (
        create_review_report_for_terminal_transition,
    )

    create_review_report_for_terminal_transition(
        session,
        resolution=resolution,
        terminal_event=event,
    )


def _abort_active_simulation_for_conflict(
    session: Session, *, resolution: CaseResolutionModel, now: datetime
) -> None:
    if resolution.status != ResolutionStatus.ACTION_DRY_RUN_PENDING.value:
        return
    attempt = session.scalar(
        select(ExternalActionSimulationAttemptModel).where(
            ExternalActionSimulationAttemptModel.tenant_id == resolution.tenant_id,
            ExternalActionSimulationAttemptModel.resolution_id == resolution.id,
            ExternalActionSimulationAttemptModel.status == "RUNNING",
        )
    )
    if attempt is not None:
        attempt.status = "FAILED"
        attempt.completed_at = now
        attempt.failure_code = "HUMAN_DECISION_CONFLICT"
        attempt.failure_message = "A different second Human Decision superseded the DRY-RUN."
    resolution.claim_token = None
    resolution.lease_expires_at = None


def _canonical_amount(value: object | None) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)), ".4f")


def _optional_string(value: object | None) -> str | None:
    return value if isinstance(value, str) else None


def _optional_integer(value: object | None) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _to_resolution(row: CaseResolutionModel) -> CaseResolution:
    return CaseResolution.model_validate(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "case_id": str(row.case_id),
            "source_review_task_id": str(row.source_review_task_id),
            "source_human_decision_id": str(row.source_human_decision_id),
            "status": row.status,
            "version": row.version,
            "mapping_name": row.mapping_name,
            "mapping_version": row.mapping_version,
            "resolution_schema_version": row.resolution_schema_version,
            "missing_fields": tuple(str(item) for item in row.missing_fields),
            "invalid_fields": tuple(str(item) for item in row.invalid_fields),
            "failure_code": row.failure_code,
            "failure_message": row.failure_message,
            "correlation_id": row.correlation_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _to_event(row: CaseResolutionEventModel) -> CaseResolutionEvent:
    return CaseResolutionEvent.model_validate(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "case_id": str(row.case_id),
            "resolution_id": str(row.resolution_id),
            "sequence": row.sequence,
            "event_type": row.event_type,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "human_decision_id": str(row.human_decision_id) if row.human_decision_id else None,
            "external_action_intent_id": (
                str(row.external_action_intent_id) if row.external_action_intent_id else None
            ),
            "payload": row.payload,
            "created_at": row.created_at,
        }
    )


def _to_intent(row: ExternalActionIntentModel) -> ExternalActionIntent:
    return ExternalActionIntent.model_validate(
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
            "amount": _canonical_amount(row.amount),
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


def _verified_intent(row: ExternalActionIntentModel) -> ExternalActionIntent:
    intent = _to_intent(row)
    if canonical_hash(action_intent_hash_payload(intent)) != intent.content_hash:
        raise CaseResolutionIntegrityError("The immutable Action Intent hash does not match.")
    return intent


def _to_attempt(row: ExternalActionSimulationAttemptModel) -> ExternalActionSimulationAttempt:
    return ExternalActionSimulationAttempt.model_validate(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "case_id": str(row.case_id),
            "resolution_id": str(row.resolution_id),
            "external_action_intent_id": str(row.external_action_intent_id),
            "attempt_number": row.attempt_number,
            "execution_token": str(row.execution_token),
            "status": row.status,
            "mode": row.mode,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "failure_code": row.failure_code,
            "failure_message": row.failure_message,
        }
    )


def _result_hash_payload(row: ExternalActionSimulationResultModel) -> dict[str, object]:
    return {
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


def _verify_result(row: ExternalActionSimulationResultModel) -> None:
    if row.side_effects_performed or canonical_hash(_result_hash_payload(row)) != row.content_hash:
        raise CaseResolutionIntegrityError("The immutable simulation Result failed verification.")


def _to_result(row: ExternalActionSimulationResultModel) -> ExternalActionSimulationResult:
    _verify_result(row)
    return ExternalActionSimulationResult.model_validate(
        {
            **_result_hash_payload(row),
            "content_hash": row.content_hash,
        }
    )


__all__ = [
    "CASE_RESOLUTION_DISPATCH_FAILURE",
    "SIMULATION_DISPATCH_FAILURE",
    "SQLAlchemyCaseResolutionRepository",
]
