"""Long-running, signal-aware dispatcher for durable analysis outbox events."""

import argparse
import os
import signal
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from threading import Event
from types import FrameType
from typing import Protocol

from app.adapters.messaging import (
    CeleryAnalysisMessageQueue,
    CeleryCaseResolutionMessageQueue,
    CeleryExternalActionSimulationMessageQueue,
    CeleryGroundedExplanationMessageQueue,
    CeleryHumanReviewMessageQueue,
    CeleryOperationalRecoveryMessageQueue,
    CeleryPolicyEvaluationMessageQueue,
    CeleryPolicyRetrievalMessageQueue,
)
from app.adapters.persistence.case_resolution_outbox import (
    DispatchCaseResolutionOutbox,
    DispatchExternalActionSimulationOutbox,
)
from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.failure_recovery_outbox import (
    DispatchOperationalFailureRecoveryOutbox,
)
from app.adapters.persistence.grounding_outbox import DispatchGroundedExplanationOutbox
from app.adapters.persistence.human_review_outbox import DispatchHumanReviewOutbox
from app.adapters.persistence.policy_engine_outbox import DispatchPolicyEvaluationOutbox
from app.adapters.persistence.policy_query_outbox import DispatchPolicyRetrievalOutbox
from app.adapters.persistence.session import create_session_factory
from app.application.outbox import DispatchOutboxResult
from app.bootstrap.logging import configure_logging, get_logger
from app.bootstrap.settings import get_settings
from app.bootstrap.sprint2 import build_outbox_dispatcher
from app.interface.workers.celery_app import create_celery_app

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PipelineDispatchOutcome:
    pipeline: str
    result: DispatchOutboxResult | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        if not self.pipeline.strip():
            raise ValueError("pipeline must not be blank")
        if (self.result is None) == (self.error_type is None):
            raise ValueError("pipeline outcome requires exactly one result or error")


@dataclass(frozen=True, slots=True)
class CompositeDispatchResult:
    pipeline_outcomes: tuple[PipelineDispatchOutcome, ...]

    @property
    def claimed(self) -> int:
        return sum(
            outcome.result.claimed
            for outcome in self.pipeline_outcomes
            if outcome.result is not None
        )

    @property
    def published(self) -> int:
        return sum(
            outcome.result.published
            for outcome in self.pipeline_outcomes
            if outcome.result is not None
        )

    @property
    def retried(self) -> int:
        return sum(
            outcome.result.retried
            for outcome in self.pipeline_outcomes
            if outcome.result is not None
        )

    @property
    def failed(self) -> int:
        return sum(
            outcome.result.failed
            for outcome in self.pipeline_outcomes
            if outcome.result is not None
        )

    @property
    def pipeline_failures(self) -> int:
        return sum(outcome.error_type is not None for outcome in self.pipeline_outcomes)


type DispatchIterationResult = DispatchOutboxResult | CompositeDispatchResult


class _OutboxDispatcher(Protocol):
    def execute(self) -> DispatchIterationResult: ...


class _ChildOutboxDispatcher(Protocol):
    def execute(self) -> DispatchOutboxResult: ...


class CompositeOutboxDispatcher:
    def __init__(self, dispatchers: tuple[tuple[str, _ChildOutboxDispatcher], ...]) -> None:
        names = tuple(name for name, _dispatcher in dispatchers)
        if any(not name.strip() for name in names) or len(set(names)) != len(names):
            raise ValueError("dispatcher pipeline names must be non-blank and unique")
        self._dispatchers = dispatchers

    def execute(self) -> CompositeDispatchResult:
        outcomes: list[PipelineDispatchOutcome] = []
        for pipeline, dispatcher in self._dispatchers:
            try:
                result = dispatcher.execute()
            except Exception as error:
                error_type = type(error).__name__
                logger.warning(
                    "outbox_pipeline_dispatch_failed",
                    pipeline=pipeline,
                    error_type=error_type,
                )
                outcomes.append(PipelineDispatchOutcome(pipeline=pipeline, error_type=error_type))
                continue
            logger.info(
                "outbox_pipeline_dispatch_completed",
                pipeline=pipeline,
                claimed=result.claimed,
                published=result.published,
                retried=result.retried,
                failed=result.failed,
            )
            outcomes.append(PipelineDispatchOutcome(pipeline=pipeline, result=result))
        return CompositeDispatchResult(pipeline_outcomes=tuple(outcomes))


def run_dispatch_loop(
    dispatcher: _OutboxDispatcher,
    *,
    once: bool,
    poll_interval_seconds: float,
    stop_event: Event,
) -> int:
    """Run bounded batches, retrying safe startup failures until termination."""

    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive")
    iteration = 0
    while not stop_event.is_set():
        iteration += 1
        try:
            result = dispatcher.execute()
        except Exception as error:
            logger.warning(
                "outbox_dispatch_iteration_failed",
                iteration=iteration,
                error_type=type(error).__name__,
            )
            if once:
                return 1
        else:
            pipeline_failures = (
                result.pipeline_failures if isinstance(result, CompositeDispatchResult) else 0
            )
            logger.info(
                "outbox_dispatch_iteration_completed",
                iteration=iteration,
                claimed=result.claimed,
                published=result.published,
                retried=result.retried,
                failed=result.failed,
                pipeline_failures=pipeline_failures,
            )
            if once:
                return 1 if pipeline_failures else 0
        stop_event.wait(poll_interval_seconds)

    logger.info("outbox_dispatcher_stopped", iterations=iteration)
    return 0


def install_signal_handlers(stop_event: Event) -> None:
    def request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info(
            "outbox_dispatcher_stop_requested",
            signal_name=signal.Signals(signum).name,
        )
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)


def _dispatcher_identity() -> str:
    hostname = socket.gethostname().strip() or "unknown-host"
    return f"dispatcher:{hostname}:{os.getpid()}"


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dispatch durable CSight analysis outbox events")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Claim and dispatch at most one configured batch, then exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    stop_event = Event()
    install_signal_handlers(stop_event)

    try:
        celery = create_celery_app(settings)
        dispatcher_identity = _dispatcher_identity()
        analysis_dispatcher = build_outbox_dispatcher(
            settings,
            queue=CeleryAnalysisMessageQueue(celery),
            claimed_by=dispatcher_identity,
        )
        if settings.database_url_value is None:
            dispatcher = analysis_dispatcher
        else:
            session_factory = create_session_factory(get_engine(settings))
            claim_ttl = timedelta(seconds=settings.analysis_outbox_claim_seconds)
            retry_base = timedelta(seconds=settings.analysis_outbox_retry_base_seconds)
            retry_max = timedelta(seconds=settings.analysis_outbox_retry_max_seconds)
            terminalize_run_on_failure = not (
                settings.database_rls_required and settings.database_runtime_role == "dispatcher"
            )
            policy_dispatcher = DispatchPolicyRetrievalOutbox(
                session_factory=session_factory,
                queue=CeleryPolicyRetrievalMessageQueue(celery),
                claimed_by=dispatcher_identity,
                batch_size=settings.analysis_outbox_batch_size,
                claim_ttl=claim_ttl,
                max_attempts=settings.analysis_outbox_max_attempts,
                retry_base=retry_base,
                retry_max=retry_max,
                terminalize_run_on_failure=terminalize_run_on_failure,
            )
            grounding_dispatcher = DispatchGroundedExplanationOutbox(
                session_factory=session_factory,
                queue=CeleryGroundedExplanationMessageQueue(celery),
                claimed_by=dispatcher_identity,
                batch_size=settings.analysis_outbox_batch_size,
                claim_ttl=claim_ttl,
                max_attempts=settings.analysis_outbox_max_attempts,
                retry_base=retry_base,
                retry_max=retry_max,
                terminalize_run_on_failure=terminalize_run_on_failure,
            )
            policy_evaluation_dispatcher = DispatchPolicyEvaluationOutbox(
                session_factory=session_factory,
                queue=CeleryPolicyEvaluationMessageQueue(celery),
                claimed_by=dispatcher_identity,
                batch_size=settings.analysis_outbox_batch_size,
                claim_ttl=claim_ttl,
                max_attempts=settings.analysis_outbox_max_attempts,
                retry_base=retry_base,
                retry_max=retry_max,
                terminalize_run_on_failure=terminalize_run_on_failure,
            )
            human_review_dispatcher = DispatchHumanReviewOutbox(
                session_factory=session_factory,
                queue=CeleryHumanReviewMessageQueue(celery),
                claimed_by=dispatcher_identity,
                batch_size=settings.analysis_outbox_batch_size,
                claim_ttl=claim_ttl,
                max_attempts=settings.analysis_outbox_max_attempts,
                retry_base=retry_base,
                retry_max=retry_max,
            )
            case_resolution_dispatcher = DispatchCaseResolutionOutbox(
                session_factory=session_factory,
                queue=CeleryCaseResolutionMessageQueue(celery),
                claimed_by=dispatcher_identity,
                batch_size=settings.analysis_outbox_batch_size,
                claim_ttl=claim_ttl,
                max_attempts=settings.analysis_outbox_max_attempts,
                retry_base=retry_base,
                retry_max=retry_max,
            )
            action_simulation_dispatcher = DispatchExternalActionSimulationOutbox(
                session_factory=session_factory,
                queue=CeleryExternalActionSimulationMessageQueue(celery),
                claimed_by=dispatcher_identity,
                batch_size=settings.analysis_outbox_batch_size,
                claim_ttl=claim_ttl,
                max_attempts=settings.analysis_outbox_max_attempts,
                retry_base=retry_base,
                retry_max=retry_max,
            )
            failure_recovery_dispatcher = DispatchOperationalFailureRecoveryOutbox(
                session_factory=session_factory,
                queue=CeleryOperationalRecoveryMessageQueue(celery),
                claimed_by=dispatcher_identity,
                batch_size=settings.analysis_outbox_batch_size,
                claim_ttl=claim_ttl,
                max_attempts=settings.analysis_outbox_max_attempts,
                retry_base=retry_base,
                retry_max=retry_max,
            )
            dispatcher = CompositeOutboxDispatcher(
                (
                    ("analysis", analysis_dispatcher),
                    ("policy_retrieval", policy_dispatcher),
                    ("grounded_explanation", grounding_dispatcher),
                    ("policy_evaluation", policy_evaluation_dispatcher),
                    ("human_review", human_review_dispatcher),
                    ("case_resolution", case_resolution_dispatcher),
                    ("external_action_simulation", action_simulation_dispatcher),
                    ("failure_recovery", failure_recovery_dispatcher),
                )
            )
    except Exception as error:
        logger.error(
            "outbox_dispatcher_configuration_failed",
            error_type=type(error).__name__,
        )
        return 1

    logger.info(
        "outbox_dispatcher_started",
        once=arguments.once,
        poll_interval_seconds=settings.analysis_outbox_poll_interval_seconds,
    )
    return run_dispatch_loop(
        dispatcher,
        once=arguments.once,
        poll_interval_seconds=settings.analysis_outbox_poll_interval_seconds,
        stop_event=stop_event,
    )


if __name__ == "__main__":
    raise SystemExit(main())
