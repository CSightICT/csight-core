"""Celery application factory and worker process entrypoint."""

from celery import Celery

from app.bootstrap.logging import configure_logging
from app.bootstrap.model_activation import validate_model_release_worker_startup
from app.bootstrap.model_routing import validate_model_route_worker_startup
from app.bootstrap.settings import Settings, get_settings

ANALYSIS_REQUESTED_TASK_NAME = "analysis.requested.v1"
POLICY_RETRIEVAL_REQUESTED_TASK_NAME = "policy_retrieval.requested.v1"
POLICY_QUERY_BUILD_REQUESTED_TASK_NAME = "policy_query_build.requested.v2"
POLICY_SEARCH_REQUESTED_TASK_NAME = "policy_search.requested.v2"
GROUNDED_EXPLANATION_REQUESTED_TASK_NAME = "grounded_explanation.requested.v1"
POLICY_EVALUATION_REQUESTED_TASK_NAME = "policy_evaluation.requested.v1"
HUMAN_REVIEW_REQUESTED_TASK_NAME = "human_review.requested.v1"
CASE_RESOLUTION_REQUESTED_TASK_NAME = "case_resolution.requested.v1"
EXTERNAL_ACTION_SIMULATION_REQUESTED_TASK_NAME = "external_action.simulation_requested.v1"


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Create a RabbitMQ-backed Celery process with reference-only JSON messages."""

    resolved_settings = settings or get_settings()
    validate_model_release_worker_startup(resolved_settings)
    validate_model_route_worker_startup(resolved_settings)
    configure_logging(resolved_settings.log_level)
    application = Celery(
        "csight",
        broker=resolved_settings.rabbitmq_url_value,
        include=["app.interface.workers.tasks"],
        task_cls="app.interface.workers.telemetry:TelemetryTask",
    )
    application.conf.update(
        accept_content=["json"],
        task_serializer="json",
        result_serializer="json",
        task_default_queue="default",
        task_routes={
            ANALYSIS_REQUESTED_TASK_NAME: {"queue": "analysis"},
            POLICY_RETRIEVAL_REQUESTED_TASK_NAME: {"queue": "policy-retrieval"},
            POLICY_QUERY_BUILD_REQUESTED_TASK_NAME: {"queue": "policy-query-build"},
            POLICY_SEARCH_REQUESTED_TASK_NAME: {"queue": "policy-search"},
            GROUNDED_EXPLANATION_REQUESTED_TASK_NAME: {"queue": "grounded-explanation"},
            POLICY_EVALUATION_REQUESTED_TASK_NAME: {"queue": "policy-evaluation"},
            HUMAN_REVIEW_REQUESTED_TASK_NAME: {"queue": "human-review"},
            CASE_RESOLUTION_REQUESTED_TASK_NAME: {"queue": "case-resolution"},
            EXTERNAL_ACTION_SIMULATION_REQUESTED_TASK_NAME: {"queue": "external-action-simulation"},
        },
        task_track_started=True,
        task_acks_late=True,
        task_acks_on_failure_or_timeout=False,
        task_reject_on_worker_lost=True,
        task_soft_time_limit=resolved_settings.analysis_task_soft_time_limit_seconds,
        task_time_limit=resolved_settings.analysis_task_hard_time_limit_seconds,
        worker_prefetch_multiplier=1,
        broker_connection_retry=True,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"confirm_publish": True},
        task_publish_retry=True,
        task_publish_retry_policy={
            "max_retries": resolved_settings.celery_task_max_retries,
            "interval_start": 0,
            "interval_step": 0.2,
            "interval_max": 1,
        },
        task_default_delivery_mode="persistent",
        task_store_errors_even_if_ignored=False,
        task_ignore_result=True,
    )
    return application


celery_app = create_celery_app()
