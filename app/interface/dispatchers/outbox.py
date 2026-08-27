"""Long-running, signal-aware dispatcher for durable analysis outbox events."""

import argparse
import os
import signal
import socket
from collections.abc import Sequence
from threading import Event
from types import FrameType
from typing import Protocol

from app.adapters.messaging import (
    CeleryAnalysisMessageQueue,
    CeleryGroundedExplanationMessageQueue,
    CeleryPolicyEvaluationMessageQueue,
    CeleryPolicyRetrievalMessageQueue,
)
from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.grounding_outbox import DispatchGroundedExplanationOutbox
from app.adapters.persistence.policy_engine_outbox import DispatchPolicyEvaluationOutbox
from app.adapters.persistence.policy_query_outbox import DispatchPolicyRetrievalOutbox
from app.adapters.persistence.session import create_session_factory
from app.application.outbox import DispatchOutboxResult
from app.bootstrap.logging import configure_logging, get_logger
from app.bootstrap.settings import get_settings
from app.bootstrap.sprint2 import build_outbox_dispatcher
from app.interface.workers.celery_app import create_celery_app

logger = get_logger(__name__)


class _OutboxDispatcher(Protocol):
    def execute(self) -> DispatchOutboxResult: ...


class CompositeOutboxDispatcher:
    def __init__(self, dispatchers: tuple[_OutboxDispatcher, ...]) -> None:
        self._dispatchers = dispatchers

    def execute(self) -> DispatchOutboxResult:
        results = tuple(dispatcher.execute() for dispatcher in self._dispatchers)
        return DispatchOutboxResult(
            claimed=sum(result.claimed for result in results),
            published=sum(result.published for result in results),
            retried=sum(result.retried for result in results),
            failed=sum(result.failed for result in results),
        )


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
            logger.info(
                "outbox_dispatch_iteration_completed",
                iteration=iteration,
                claimed=result.claimed,
                published=result.published,
                retried=result.retried,
                failed=result.failed,
            )
            if once:
                return 0
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
        analysis_dispatcher = build_outbox_dispatcher(
            settings,
            queue=CeleryAnalysisMessageQueue(celery),
            claimed_by=_dispatcher_identity(),
        )
        if settings.database_url_value is None:
            dispatcher = analysis_dispatcher
        else:
            policy_dispatcher = DispatchPolicyRetrievalOutbox(
                session_factory=create_session_factory(get_engine(settings)),
                queue=CeleryPolicyRetrievalMessageQueue(celery),
            )
            grounding_dispatcher = DispatchGroundedExplanationOutbox(
                session_factory=create_session_factory(get_engine(settings)),
                queue=CeleryGroundedExplanationMessageQueue(celery),
            )
            policy_evaluation_dispatcher = DispatchPolicyEvaluationOutbox(
                session_factory=create_session_factory(get_engine(settings)),
                queue=CeleryPolicyEvaluationMessageQueue(celery),
            )
            dispatcher = CompositeOutboxDispatcher(
                (
                    analysis_dispatcher,
                    policy_dispatcher,
                    grounding_dispatcher,
                    policy_evaluation_dispatcher,
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
