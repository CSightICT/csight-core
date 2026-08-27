"""Composition root for Sprint 2 append-only text analysis."""

from datetime import timedelta

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.unit_of_work import create_analysis_unit_of_work_factory
from app.adapters.runtime import UtcClock, Uuid4Generator
from app.adapters.storage import MinioObjectStorage
from app.application.analysis import (
    ExecuteRequestedAnalysisStage,
    ExecuteTextExtraction,
    ExecuteVisionAnalysis,
    GetAnalysisRun,
    GetLatestAnalysisRun,
    ListAnalysisRuns,
    StartTextAnalysis,
)
from app.application.outbox import DispatchOutbox
from app.bootstrap.dependencies import build_llm_provider, build_vision_provider
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs import (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
)
from app.domains.product_defect_cs.prompts import (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2,
)
from app.interface.http.services import Sprint2ServiceContainer
from app.platform.analysis.prompts import PromptManifest
from app.ports.analysis_repository import AnalysisUnitOfWorkFactory
from app.ports.message_queue import MessageQueue


class Sprint2ConfigurationError(RuntimeError):
    """Raised without configuration values when Sprint 2 cannot be composed."""


def _v2_prompt(settings: Settings) -> PromptManifest:
    return (
        PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2
        if settings.llm_provider == "mlx"
        else PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
    )


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
            vision_provider=build_vision_provider(settings),
            prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
            prompt_v2=_v2_prompt(settings),
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
        prompt_v2=_v2_prompt(settings),
        clock=UtcClock(),
        id_generator=Uuid4Generator(),
        claim_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
        max_attempts=settings.celery_task_max_retries + 1,
        retry_base=timedelta(seconds=1),
        retry_max=timedelta(seconds=settings.celery_retry_backoff_max_seconds),
    )


def build_execute_analysis_stage(settings: Settings) -> ExecuteRequestedAnalysisStage:
    """Compose the shared Stage router used by the thin Celery task."""

    uow_factory = _uow_factory(settings)
    text = build_execute_text_extraction(settings)
    vision = ExecuteVisionAnalysis(
        uow_factory=uow_factory,
        provider=build_vision_provider(settings),
        storage=_object_storage(settings),
        clock=UtcClock(),
        id_generator=Uuid4Generator(),
        max_image_bytes=settings.vision_max_image_bytes,
        claim_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
        max_attempts=settings.celery_task_max_retries + 1,
        retry_base=timedelta(seconds=1),
        retry_max=timedelta(seconds=settings.celery_retry_backoff_max_seconds),
    )
    return ExecuteRequestedAnalysisStage(uow_factory=uow_factory, text=text, vision=vision)


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


def _object_storage(settings: Settings) -> MinioObjectStorage:
    required = (
        settings.minio_endpoint,
        settings.minio_presigned_endpoint_value,
        settings.minio_access_key_value,
        settings.minio_secret_key_value,
    )
    if not all(required):
        raise Sprint2ConfigurationError("MinIO configuration is required for Vision execution")
    return MinioObjectStorage(
        endpoint=str(required[0]),
        presigned_endpoint=str(required[1]),
        access_key=str(required[2]),
        secret_key=str(required[3]),
        bucket=settings.minio_bucket,
        region=settings.minio_region,
        secure=settings.minio_secure,
        presigned_secure=settings.minio_presigned_secure_value,
        timeout_seconds=settings.readiness_timeout_seconds,
    )


__all__ = [
    "Sprint2ConfigurationError",
    "build_execute_analysis_stage",
    "build_execute_text_extraction",
    "build_outbox_dispatcher",
    "build_sprint2_services",
    "sprint2_is_configured",
]
