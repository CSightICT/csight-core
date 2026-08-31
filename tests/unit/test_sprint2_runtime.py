"""Runtime composition, Celery, and durable dispatcher contracts for Sprint 2."""

import signal
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from threading import Event
from types import FrameType
from typing import Any, cast

import pytest
from pydantic import SecretStr

import app.main as main_module
from app.application.outbox import DispatchOutboxResult
from app.bootstrap.settings import Settings
from app.interface.dispatchers import outbox as dispatcher_module
from app.interface.http.services import Sprint2ServiceContainer
from app.interface.workers.celery_app import (
    ANALYSIS_REQUESTED_TASK_NAME,
    GROUNDED_EXPLANATION_REQUESTED_TASK_NAME,
    POLICY_QUERY_BUILD_REQUESTED_TASK_NAME,
    POLICY_SEARCH_REQUESTED_TASK_NAME,
    create_celery_app,
)

pytestmark = pytest.mark.unit


def test_main_auto_composes_sprint2_but_preserves_explicit_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = cast(Sprint2ServiceContainer, object())
    injected = cast(Sprint2ServiceContainer, object())
    build_calls = 0

    def build(_settings: Settings) -> Sprint2ServiceContainer:
        nonlocal build_calls
        build_calls += 1
        return built

    def is_not_configured(_settings: Settings) -> bool:
        return False

    def is_configured(_settings: Settings) -> bool:
        return True

    monkeypatch.setattr(main_module, "sprint1_is_configured", is_not_configured)
    monkeypatch.setattr(main_module, "sprint2_is_configured", is_configured)
    monkeypatch.setattr(main_module, "build_sprint2_services", build)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    auto_application = main_module.create_app(settings)
    injected_application = main_module.create_app(
        settings,
        sprint2_services=injected,
    )

    assert auto_application.state.sprint2_services is built
    assert injected_application.state.sprint2_services is injected
    assert build_calls == 1


def test_celery_configuration_uses_durable_db_retries_and_safe_worker_limits() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        rabbitmq_url=SecretStr("amqp://user:password@rabbitmq:5672//"),
        analysis_task_soft_time_limit_seconds=30,
        analysis_task_hard_time_limit_seconds=40,
        analysis_stage_lease_seconds=60,
        celery_task_max_retries=4,
    )

    application = create_celery_app(settings)

    assert application.conf.task_routes[ANALYSIS_REQUESTED_TASK_NAME] == {"queue": "analysis"}
    assert application.conf.task_routes["policy_retrieval.requested.v1"] == {
        "queue": "policy-retrieval"
    }
    assert application.conf.task_routes[POLICY_QUERY_BUILD_REQUESTED_TASK_NAME] == {
        "queue": "policy-query-build"
    }
    assert application.conf.task_routes[POLICY_SEARCH_REQUESTED_TASK_NAME] == {
        "queue": "policy-search"
    }
    assert application.conf.task_routes[GROUNDED_EXPLANATION_REQUESTED_TASK_NAME] == {
        "queue": "grounded-explanation"
    }
    assert application.conf.task_acks_late is True
    assert application.conf.task_acks_on_failure_or_timeout is False
    assert application.conf.task_reject_on_worker_lost is True
    assert application.conf.worker_prefetch_multiplier == 1
    assert application.conf.task_soft_time_limit == 30
    assert application.conf.task_time_limit == 40
    assert application.conf.task_publish_retry is True
    assert application.conf.task_publish_retry_policy["max_retries"] == 4
    assert application.conf.broker_transport_options["confirm_publish"] is True
    assert application.conf.task_default_delivery_mode == "persistent"
    assert application.conf.task_ignore_result is True


def test_core_compose_splits_model_retrieval_and_decision_worker_lanes() -> None:
    compose = Path("infra/compose.core.yml").read_text(encoding="utf-8")
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "  worker-model:" in compose
    assert "--hostname=worker-model@%h" in compose
    assert "--queues=analysis,policy-retrieval,policy-query-build,grounded-explanation" in compose
    assert "--concurrency=1" in compose
    assert "  worker-retrieval:" in compose
    assert "--hostname=worker-retrieval@%h" in compose
    assert "--queues=policy-search" in compose
    assert "  worker-decision:" in compose
    assert "--hostname=worker-decision@%h" in compose
    assert (
        "--queues=policy-evaluation,human-review,case-resolution,external-action-simulation"
        in compose
    )
    assert compose.count("--concurrency=2") == 2
    assert "  worker:\n" not in compose
    # Core demo, strict-RLS pilot, scenario PoC, and E3 scenario profiles all
    # use the same health-gated worker-lane startup contract.
    assert makefile.count("up --build --detach --wait --remove-orphans") == 4


@dataclass(slots=True)
class _SequenceDispatcher:
    outcomes: list[DispatchOutboxResult | Exception]
    stop_event: Event | None = None
    calls: int = 0

    def execute(self) -> DispatchOutboxResult:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        if self.stop_event is not None and self.calls == len(self.outcomes):
            self.stop_event.set()
        return outcome


@dataclass(slots=True)
class _RecordingLogger:
    records: list[tuple[str, str, dict[str, object]]] = field(default_factory=list)

    def info(self, event: str, **values: object) -> None:
        self.records.append(("info", event, values))

    def warning(self, event: str, **values: object) -> None:
        self.records.append(("warning", event, values))

    def error(self, event: str, **values: object) -> None:
        self.records.append(("error", event, values))


def test_composite_dispatcher_isolates_child_failure_and_reports_each_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _SequenceDispatcher(
        outcomes=[DispatchOutboxResult(claimed=2, published=1, retried=1, failed=0)]
    )
    retrieval = _SequenceDispatcher(
        outcomes=[RuntimeError("postgresql://private-user:private-password@db/csight")]
    )
    decision = _SequenceDispatcher(
        outcomes=[DispatchOutboxResult(claimed=3, published=2, retried=0, failed=1)]
    )
    recording_logger = _RecordingLogger()
    monkeypatch.setattr(dispatcher_module, "logger", recording_logger)
    dispatcher = dispatcher_module.CompositeOutboxDispatcher(
        (
            ("analysis", analysis),
            ("policy_retrieval", retrieval),
            ("decision", decision),
        )
    )

    result = dispatcher.execute()

    assert (analysis.calls, retrieval.calls, decision.calls) == (1, 1, 1)
    assert (result.claimed, result.published, result.retried, result.failed) == (5, 3, 1, 1)
    assert result.pipeline_failures == 1
    assert tuple(outcome.pipeline for outcome in result.pipeline_outcomes) == (
        "analysis",
        "policy_retrieval",
        "decision",
    )
    assert result.pipeline_outcomes[1].result is None
    assert result.pipeline_outcomes[1].error_type == "RuntimeError"
    assert recording_logger.records == [
        (
            "info",
            "outbox_pipeline_dispatch_completed",
            {
                "pipeline": "analysis",
                "claimed": 2,
                "published": 1,
                "retried": 1,
                "failed": 0,
            },
        ),
        (
            "warning",
            "outbox_pipeline_dispatch_failed",
            {"pipeline": "policy_retrieval", "error_type": "RuntimeError"},
        ),
        (
            "info",
            "outbox_pipeline_dispatch_completed",
            {
                "pipeline": "decision",
                "claimed": 3,
                "published": 2,
                "retried": 0,
                "failed": 1,
            },
        ),
    ]
    assert "private-password" not in repr(recording_logger.records)


def test_dispatch_loop_once_executes_exactly_one_bounded_batch() -> None:
    dispatcher = _SequenceDispatcher(
        outcomes=[DispatchOutboxResult(claimed=2, published=1, retried=1, failed=0)]
    )

    exit_code = dispatcher_module.run_dispatch_loop(
        dispatcher,
        once=True,
        poll_interval_seconds=0.01,
        stop_event=Event(),
    )

    assert exit_code == 0
    assert dispatcher.calls == 1


def test_dispatch_loop_retries_startup_failure_without_logging_database_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = Event()
    dispatcher = _SequenceDispatcher(
        outcomes=[
            RuntimeError("postgresql://private-user:private-password@database/csight"),
            DispatchOutboxResult(claimed=0, published=0, retried=0, failed=0),
        ],
        stop_event=stop_event,
    )
    recording_logger = _RecordingLogger()
    monkeypatch.setattr(dispatcher_module, "logger", recording_logger)

    exit_code = dispatcher_module.run_dispatch_loop(
        dispatcher,
        once=False,
        poll_interval_seconds=0.001,
        stop_event=stop_event,
    )

    assert exit_code == 0
    assert dispatcher.calls == 2
    assert recording_logger.records[0] == (
        "warning",
        "outbox_dispatch_iteration_failed",
        {"iteration": 1, "error_type": "RuntimeError"},
    )
    assert "private-password" not in repr(recording_logger.records)


def test_dispatcher_cli_builds_celery_queue_and_dispatcher_for_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    celery_marker = object()
    queue_marker = object()
    dispatcher = _SequenceDispatcher(
        outcomes=[DispatchOutboxResult(claimed=0, published=0, retried=0, failed=0)]
    )
    captured: dict[str, object] = {}

    def ignore_log_level(_level: str) -> None:
        return None

    def ignore_signal_handlers(_event: Event) -> None:
        return None

    def create_application(_settings: Settings) -> object:
        return celery_marker

    monkeypatch.setattr(dispatcher_module, "get_settings", lambda: settings)
    monkeypatch.setattr(dispatcher_module, "configure_logging", ignore_log_level)
    monkeypatch.setattr(dispatcher_module, "install_signal_handlers", ignore_signal_handlers)
    monkeypatch.setattr(dispatcher_module, "_dispatcher_identity", lambda: "dispatcher:test:1")
    monkeypatch.setattr(dispatcher_module, "create_celery_app", create_application)

    def build_queue(application: object) -> object:
        captured["celery"] = application
        return queue_marker

    def build_dispatcher(
        configured_settings: Settings,
        *,
        queue: object,
        claimed_by: str,
    ) -> _SequenceDispatcher:
        captured.update(
            settings=configured_settings,
            queue=queue,
            claimed_by=claimed_by,
        )
        return dispatcher

    monkeypatch.setattr(dispatcher_module, "CeleryAnalysisMessageQueue", build_queue)
    monkeypatch.setattr(dispatcher_module, "build_outbox_dispatcher", build_dispatcher)

    assert dispatcher_module.main(["--once"]) == 0
    assert captured == {
        "celery": celery_marker,
        "settings": settings,
        "queue": queue_marker,
        "claimed_by": "dispatcher:test:1",
    }
    assert dispatcher.calls == 1


def test_all_sql_outboxes_share_resolved_dispatch_settings_and_process_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr("postgresql+psycopg://user:password@db/csight"),
        analysis_outbox_batch_size=7,
        analysis_outbox_claim_seconds=11,
        analysis_outbox_max_attempts=13,
        analysis_outbox_retry_base_seconds=2.5,
        analysis_outbox_retry_max_seconds=45,
    )
    celery_marker = object()
    engine_marker = object()
    session_factory_marker = object()
    captured: dict[str, dict[str, object]] = {}
    identity_calls = 0

    def identity() -> str:
        nonlocal identity_calls
        identity_calls += 1
        return "dispatcher:test:shared"

    def build_analysis(
        configured_settings: Settings,
        *,
        queue: object,
        claimed_by: str,
    ) -> _SequenceDispatcher:
        captured["analysis"] = {
            "settings": configured_settings,
            "queue": queue,
            "claimed_by": claimed_by,
        }
        return _SequenceDispatcher(
            outcomes=[DispatchOutboxResult(claimed=0, published=0, retried=0, failed=0)]
        )

    def reliable_factory(name: str) -> Callable[..., _SequenceDispatcher]:
        def build(**values: object) -> _SequenceDispatcher:
            captured[name] = values
            return _SequenceDispatcher(
                outcomes=[DispatchOutboxResult(claimed=0, published=0, retried=0, failed=0)]
            )

        return build

    def ignore_log_level(_level: str) -> None:
        return None

    def ignore_signal_handlers(_event: Event) -> None:
        return None

    def create_application(_settings: Settings) -> object:
        return celery_marker

    def resolve_engine(_settings: Settings) -> object:
        return engine_marker

    def resolve_session_factory(engine: object) -> object | None:
        return session_factory_marker if engine is engine_marker else None

    def queue_factory(name: str) -> Callable[[object], str]:
        def build(_application: object) -> str:
            return name

        return build

    monkeypatch.setattr(dispatcher_module, "get_settings", lambda: settings)
    monkeypatch.setattr(dispatcher_module, "configure_logging", ignore_log_level)
    monkeypatch.setattr(dispatcher_module, "install_signal_handlers", ignore_signal_handlers)
    monkeypatch.setattr(dispatcher_module, "_dispatcher_identity", identity)
    monkeypatch.setattr(dispatcher_module, "create_celery_app", create_application)
    monkeypatch.setattr(dispatcher_module, "get_engine", resolve_engine)
    monkeypatch.setattr(dispatcher_module, "create_session_factory", resolve_session_factory)
    monkeypatch.setattr(dispatcher_module, "build_outbox_dispatcher", build_analysis)
    monkeypatch.setattr(dispatcher_module, "CeleryAnalysisMessageQueue", queue_factory("analysis"))
    monkeypatch.setattr(
        dispatcher_module, "CeleryPolicyRetrievalMessageQueue", queue_factory("retrieval")
    )
    monkeypatch.setattr(
        dispatcher_module, "CeleryGroundedExplanationMessageQueue", queue_factory("grounding")
    )
    monkeypatch.setattr(
        dispatcher_module, "CeleryPolicyEvaluationMessageQueue", queue_factory("evaluation")
    )
    monkeypatch.setattr(dispatcher_module, "CeleryHumanReviewMessageQueue", queue_factory("review"))
    monkeypatch.setattr(
        dispatcher_module,
        "CeleryCaseResolutionMessageQueue",
        queue_factory("case-resolution"),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "CeleryExternalActionSimulationMessageQueue",
        queue_factory("action-simulation"),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "CeleryOperationalRecoveryMessageQueue",
        queue_factory("failure-recovery"),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "DispatchPolicyRetrievalOutbox",
        reliable_factory("retrieval"),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "DispatchGroundedExplanationOutbox",
        reliable_factory("grounding"),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "DispatchPolicyEvaluationOutbox",
        reliable_factory("evaluation"),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "DispatchHumanReviewOutbox",
        reliable_factory("review"),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "DispatchCaseResolutionOutbox",
        reliable_factory("case-resolution"),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "DispatchExternalActionSimulationOutbox",
        reliable_factory("action-simulation"),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "DispatchOperationalFailureRecoveryOutbox",
        reliable_factory("failure-recovery"),
    )

    assert dispatcher_module.main(["--once"]) == 0
    assert identity_calls == 1
    assert captured["analysis"]["claimed_by"] == "dispatcher:test:shared"
    expected = {
        "claimed_by": "dispatcher:test:shared",
        "batch_size": 7,
        "claim_ttl": timedelta(seconds=11),
        "max_attempts": 13,
        "retry_base": timedelta(seconds=2.5),
        "retry_max": timedelta(seconds=45),
    }
    for name, queue in (
        ("retrieval", "retrieval"),
        ("grounding", "grounding"),
        ("evaluation", "evaluation"),
        ("review", "review"),
        ("case-resolution", "case-resolution"),
        ("action-simulation", "action-simulation"),
        ("failure-recovery", "failure-recovery"),
    ):
        values = captured[name]
        assert values["session_factory"] is session_factory_marker
        assert values["queue"] == queue
        assert {key: values[key] for key in expected} == expected


def test_dispatcher_registers_sigterm_and_sigint_as_graceful_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handlers: dict[signal.Signals, Callable[[int, FrameType | None], Any]] = {}

    def register(
        signal_number: signal.Signals,
        handler: Callable[[int, FrameType | None], Any],
    ) -> None:
        handlers[signal_number] = handler

    monkeypatch.setattr(dispatcher_module.signal, "signal", register)
    stop_event = Event()

    dispatcher_module.install_signal_handlers(stop_event)

    assert handlers.keys() == {signal.SIGTERM, signal.SIGINT}
    handlers[signal.SIGTERM](signal.SIGTERM, None)
    assert stop_event.is_set()
