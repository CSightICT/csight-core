"""Sprint 4C-3A citation-grounding composition root."""

from datetime import timedelta

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.grounding import SQLAlchemyGroundedExplanationRunRepository
from app.adapters.persistence.session import create_session_factory
from app.application.grounding import (
    ExecuteGroundedExplanation,
    GetGroundedExplanationRun,
    ListGroundedExplanationRuns,
    StartGroundedExplanation,
)
from app.bootstrap.dependencies import build_llm_provider
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs.prompts import (
    GROUNDED_POLICY_EXPLANATION_PROMPT_LOCAL_2,
    GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1,
)
from app.interface.http.services import Sprint4C3AServiceContainer
from app.platform.analysis.prompts import PromptManifest


def _grounding_prompt(settings: Settings) -> PromptManifest:
    return (
        GROUNDED_POLICY_EXPLANATION_PROMPT_LOCAL_2
        if settings.llm_provider == "mlx"
        else GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1
    )


def sprint4c3a_is_configured(settings: Settings) -> bool:
    # Grounding consumes an already successful retrieval run and does not call
    # the embedding service, so its API composition only requires persistence.
    return settings.database_url_value is not None


def build_sprint4c3a_services(settings: Settings) -> Sprint4C3AServiceContainer:
    repository = SQLAlchemyGroundedExplanationRunRepository(
        create_session_factory(get_engine(settings))
    )
    llm = build_llm_provider(settings)
    return Sprint4C3AServiceContainer(
        start_grounded_explanation=StartGroundedExplanation(
            repository,
            llm,
            _grounding_prompt(settings),
        ),
        list_grounded_explanations=ListGroundedExplanationRuns(repository),
        get_grounded_explanation=GetGroundedExplanationRun(repository),
    )


def build_execute_grounded_explanation(settings: Settings) -> ExecuteGroundedExplanation:
    return ExecuteGroundedExplanation(
        repository=SQLAlchemyGroundedExplanationRunRepository(
            create_session_factory(get_engine(settings)),
            lease_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
            max_execution_attempts=settings.celery_task_max_retries + 1,
        ),
        llm=build_llm_provider(settings),
        prompt=_grounding_prompt(settings),
    )


__all__ = [
    "build_execute_grounded_explanation",
    "build_sprint4c3a_services",
    "sprint4c3a_is_configured",
]
