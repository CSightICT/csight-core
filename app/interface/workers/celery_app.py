"""Celery application factory and worker process entrypoint."""

from celery import Celery

from app.bootstrap.logging import configure_logging
from app.bootstrap.settings import Settings, get_settings

ANALYSIS_REQUESTED_TASK_NAME = "analysis.requested.v1"
POLICY_RETRIEVAL_REQUESTED_TASK_NAME = "policy_retrieval.requested.v1"
GROUNDED_EXPLANATION_REQUESTED_TASK_NAME = "grounded_explanation.requested.v1"
POLICY_EVALUATION_REQUESTED_TASK_NAME = "policy_evaluation.requested.v1"
HUMAN_REVIEW_REQUESTED_TASK_NAME = "human_review.requested.v1"


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Create a RabbitMQ-backed Celery process with reference-only JSON messages."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    application = Celery(
        "csight",
        broker=resolved_settings.rabbitmq_url_value,
        include=["app.interface.workers.tasks"],
    )
    application.conf.update(
        accept_content=["json"],
        task_serializer="json",
        result_serializer="json",
        task_default_queue="default",
        task_routes={
            ANALYSIS_REQUESTED_TASK_NAME: {"queue": "analysis"},
            POLICY_RETRIEVAL_REQUESTED_TASK_NAME: {"queue": "policy-retrieval"},
            GROUNDED_EXPLANATION_REQUESTED_TASK_NAME: {"queue": "grounded-explanation"},
            POLICY_EVALUATION_REQUESTED_TASK_NAME: {"queue": "policy-evaluation"},
            HUMAN_REVIEW_REQUESTED_TASK_NAME: {"queue": "human-review"},
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
