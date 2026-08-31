"""Sprint 4C-2 composition root."""

from datetime import timedelta

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.policy_query_runs import SQLAlchemyPolicyRetrievalRunRepository
from app.adapters.persistence.session import create_session_factory
from app.application.policy_query_runs import (
    ExecutePolicyQueryBuild,
    ExecutePolicyRetrievalRun,
    ExecutePolicySearch,
    GetPolicyRetrievalRun,
    ListPolicyRetrievalRuns,
    StartPolicyRetrievalRun,
)
from app.bootstrap.dependencies import build_llm_provider
from app.bootstrap.model_routing import (
    build_active_model_route_resolver,
    build_pinned_model_route_guard,
)
from app.bootstrap.settings import Settings
from app.bootstrap.sprint4b import build_sprint4b_services, sprint4b_is_configured
from app.domains.product_defect_cs.prompts import (
    POLICY_QUERY_BUILDER_PROMPT_LOCAL_2,
    POLICY_QUERY_BUILDER_PROMPT_V1_1,
)
from app.interface.http.services import Sprint4C2ServiceContainer
from app.platform.model_activation import ModelReleaseTask


def sprint4c2_is_configured(settings: Settings) -> bool:
    return sprint4b_is_configured(settings)


def build_sprint4c2_services(settings: Settings) -> Sprint4C2ServiceContainer:
    repository = SQLAlchemyPolicyRetrievalRunRepository(
        create_session_factory(get_engine(settings)),
        lease_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
        max_execution_attempts=settings.celery_task_max_retries + 1,
    )
    return Sprint4C2ServiceContainer(
        start_policy_retrieval_run=StartPolicyRetrievalRun(
            repository,
            model_route_resolver=build_active_model_route_resolver(settings),
        ),
        list_policy_retrieval_runs=ListPolicyRetrievalRuns(repository),
        get_policy_retrieval_run=GetPolicyRetrievalRun(repository),
    )


def build_execute_policy_retrieval_run(settings: Settings) -> ExecutePolicyRetrievalRun:
    repository = SQLAlchemyPolicyRetrievalRunRepository(
        create_session_factory(get_engine(settings)),
        lease_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
        max_execution_attempts=settings.celery_task_max_retries + 1,
    )
    prompt = (
        POLICY_QUERY_BUILDER_PROMPT_LOCAL_2
        if settings.llm_provider == "mlx"
        else POLICY_QUERY_BUILDER_PROMPT_V1_1
    )
    return ExecutePolicyRetrievalRun(
        repository=repository,
        search=build_sprint4b_services(settings).search_policy_clauses,
        llm=build_llm_provider(settings, ModelReleaseTask.POLICY_QUERY_BUILDER_V1),
        prompt=prompt,
        model_route_guard=build_pinned_model_route_guard(
            settings,
            prompt=prompt,
            task=ModelReleaseTask.POLICY_QUERY_BUILDER_V1,
        ),
    )


def build_execute_policy_query_build(
    settings: Settings,
) -> ExecutePolicyQueryBuild:
    repository = SQLAlchemyPolicyRetrievalRunRepository(
        create_session_factory(get_engine(settings)),
        lease_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
        max_execution_attempts=settings.celery_task_max_retries + 1,
    )
    prompt = (
        POLICY_QUERY_BUILDER_PROMPT_LOCAL_2
        if settings.llm_provider == "mlx"
        else POLICY_QUERY_BUILDER_PROMPT_V1_1
    )
    return ExecutePolicyQueryBuild(
        repository=repository,
        llm=build_llm_provider(settings, ModelReleaseTask.POLICY_QUERY_BUILDER_V1),
        prompt=prompt,
        model_route_guard=build_pinned_model_route_guard(
            settings,
            prompt=prompt,
            task=ModelReleaseTask.POLICY_QUERY_BUILDER_V1,
        ),
    )


def build_execute_policy_search(settings: Settings) -> ExecutePolicySearch:
    repository = SQLAlchemyPolicyRetrievalRunRepository(
        create_session_factory(get_engine(settings)),
        lease_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
        max_execution_attempts=settings.celery_task_max_retries + 1,
    )
    return ExecutePolicySearch(
        repository=repository,
        search=build_sprint4b_services(settings).search_policy_clauses,
    )


__all__ = [
    "build_execute_policy_query_build",
    "build_execute_policy_retrieval_run",
    "build_execute_policy_search",
    "build_sprint4c2_services",
    "sprint4c2_is_configured",
]
