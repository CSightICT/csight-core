"""Sprint 4C-2 composition root."""

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.policy_query_runs import SQLAlchemyPolicyRetrievalRunRepository
from app.adapters.persistence.session import create_session_factory
from app.application.policy_query_runs import (
    ExecutePolicyRetrievalRun,
    GetPolicyRetrievalRun,
    ListPolicyRetrievalRuns,
    StartPolicyRetrievalRun,
)
from app.bootstrap.dependencies import build_llm_provider
from app.bootstrap.settings import Settings
from app.bootstrap.sprint4b import build_sprint4b_services, sprint4b_is_configured
from app.domains.product_defect_cs.prompts import POLICY_QUERY_BUILDER_PROMPT_V1_1
from app.interface.http.services import Sprint4C2ServiceContainer


def sprint4c2_is_configured(settings: Settings) -> bool:
    return sprint4b_is_configured(settings)


def build_sprint4c2_services(settings: Settings) -> Sprint4C2ServiceContainer:
    repository = SQLAlchemyPolicyRetrievalRunRepository(
        create_session_factory(get_engine(settings))
    )
    return Sprint4C2ServiceContainer(
        start_policy_retrieval_run=StartPolicyRetrievalRun(repository),
        list_policy_retrieval_runs=ListPolicyRetrievalRuns(repository),
        get_policy_retrieval_run=GetPolicyRetrievalRun(repository),
    )


def build_execute_policy_retrieval_run(settings: Settings) -> ExecutePolicyRetrievalRun:
    repository = SQLAlchemyPolicyRetrievalRunRepository(
        create_session_factory(get_engine(settings))
    )
    return ExecutePolicyRetrievalRun(
        repository=repository,
        search=build_sprint4b_services(settings).search_policy_clauses,
        llm=build_llm_provider(settings),
        prompt=POLICY_QUERY_BUILDER_PROMPT_V1_1,
    )


__all__ = [
    "build_execute_policy_retrieval_run",
    "build_sprint4c2_services",
    "sprint4c2_is_configured",
]
