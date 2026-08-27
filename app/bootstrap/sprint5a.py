"""Sprint 5A deterministic policy engine composition root."""

from datetime import timedelta

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.policy_engine import SQLAlchemyPolicyEngineRepository
from app.adapters.persistence.session import create_session_factory
from app.application.policy_engine import (
    ExecutePolicyEvaluation,
    GetPolicyEvaluation,
    ListPolicyEvaluations,
    StartPolicyEvaluation,
)
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint5AServiceContainer


def sprint5a_is_configured(settings: Settings) -> bool:
    return settings.database_url_value is not None


def _repository(settings: Settings) -> SQLAlchemyPolicyEngineRepository:
    return SQLAlchemyPolicyEngineRepository(
        create_session_factory(get_engine(settings)),
        lease_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
        max_execution_attempts=settings.celery_task_max_retries + 1,
    )


def build_sprint5a_services(settings: Settings) -> Sprint5AServiceContainer:
    repository = _repository(settings)
    return Sprint5AServiceContainer(
        start_policy_evaluation=StartPolicyEvaluation(repository),
        list_policy_evaluations=ListPolicyEvaluations(repository),
        get_policy_evaluation=GetPolicyEvaluation(repository),
    )


def build_execute_policy_evaluation(settings: Settings) -> ExecutePolicyEvaluation:
    return ExecutePolicyEvaluation(_repository(settings))


__all__ = [
    "build_execute_policy_evaluation",
    "build_sprint5a_services",
    "sprint5a_is_configured",
]
