"""Celery application factory and worker process entrypoint."""

from celery import Celery

from app.bootstrap.logging import configure_logging
from app.bootstrap.settings import Settings, get_settings

ANALYZE_CASE_TASK_NAME = "csight.analysis.analyze_case"


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
        task_routes={ANALYZE_CASE_TASK_NAME: {"queue": "analysis"}},
        task_track_started=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        task_store_errors_even_if_ignored=False,
        task_ignore_result=True,
    )
    return application


celery_app = create_celery_app()
