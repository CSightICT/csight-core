"""Composition root for Sprint 2 append-only text analysis."""

from datetime import timedelta

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.unit_of_work import create_analysis_unit_of_work_factory
from app.adapters.runtime import UtcClock, Uuid4Generator
from app.application.analysis import (
    ExecuteTextExtraction,
    GetAnalysisRun,
    GetLatestAnalysisRun,
    ListAnalysisRuns,
    StartTextAnalysis,
)
from app.application.outbox import DispatchOutbox
from app.bootstrap.dependencies import build_llm_provider
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs import PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT
from app.interface.http.services import Sprint2ServiceContainer
from app.ports.analysis_repository import AnalysisUnitOfWorkFactory
from app.ports.message_queue import MessageQueue


class Sprint2ConfigurationError(RuntimeError):
    """Raised without configuration values when Sprint 2 cannot be composed."""


def sprint2_is_configured(settings: Settings) -> bool:
    """The HTTP registration path needs PostgreSQL, but not a live LLM connection."""

    return settings.database_url_value is not None


def build_sprint2_services(settings: Settings) -> Sprint2ServiceContainer:
    """Compose the authenticated Analysis Run registration and query services."""

    uow_factory = _uow_factory(settings)
    provider = build_llm_provider(settings)
    clock = UtcClock()
    id_generator = Uuid4Generator()
    return Sprint2ServiceContainer(
        start_text_analysis=StartTextAnalysis(
            uow_factory=uow_factory,
            provider=provider,
            prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
            clock=clock,
            id_generator=id_generator,
        ),
        list_analysis_runs=ListAnalysisRuns(uow_factory=uow_factory),
        get_analysis_run=GetAnalysisRun(uow_factory=uow_factory),
        get_latest_analysis_run=GetLatestAnalysisRun(uow_factory=uow_factory),
    )


def build_execute_text_extraction(settings: Settings) -> ExecuteTextExtraction:
    """Compose one Worker-safe, fenced text-extraction use case."""

    return ExecuteTextExtraction(
        uow_factory=_uow_factory(settings),
        provider=build_llm_provider(settings),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=UtcClock(),
        id_generator=Uuid4Generator(),
        claim_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
        max_attempts=settings.celery_task_max_retries + 1,
        retry_base=timedelta(seconds=1),
        retry_max=timedelta(seconds=settings.celery_retry_backoff_max_seconds),
    )


def build_outbox_dispatcher(
    settings: Settings,
    *,
    queue: MessageQueue,
    claimed_by: str,
) -> DispatchOutbox:
    """Compose one durable outbox batch dispatcher."""

    return DispatchOutbox(
        uow_factory=_uow_factory(settings),
        queue=queue,
        clock=UtcClock(),
        id_generator=Uuid4Generator(),
        claimed_by=claimed_by,
        batch_size=settings.analysis_outbox_batch_size,
        claim_ttl=timedelta(seconds=settings.analysis_outbox_claim_seconds),
        max_attempts=settings.analysis_outbox_max_attempts,
        retry_base=timedelta(seconds=settings.analysis_outbox_retry_base_seconds),
        retry_max=timedelta(seconds=settings.analysis_outbox_retry_max_seconds),
    )


def _uow_factory(settings: Settings) -> AnalysisUnitOfWorkFactory:
    if settings.database_url_value is None:
        raise Sprint2ConfigurationError("DATABASE_URL is required for Sprint 2")
    return create_analysis_unit_of_work_factory(get_engine(settings))


__all__ = [
    "Sprint2ConfigurationError",
    "build_execute_text_extraction",
    "build_outbox_dispatcher",
    "build_sprint2_services",
    "sprint2_is_configured",
]
