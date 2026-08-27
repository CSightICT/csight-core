"""Sprint 5C Case Resolution composition root."""

from datetime import timedelta

from app.adapters.external_action import DeterministicDryRunExternalActionAdapter
from app.adapters.persistence.case_resolution import SQLAlchemyCaseResolutionRepository
from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.session import create_session_factory
from app.application.case_resolution import (
    ExecuteExternalActionSimulation,
    GetCaseResolution,
    GetExternalActionIntent,
    ListCaseExternalActionIntents,
    ListCaseResolutionEvents,
    ProcessCaseResolution,
)
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint5CServiceContainer


def sprint5c_is_configured(settings: Settings) -> bool:
    return settings.database_url_value is not None


def _repository(settings: Settings) -> SQLAlchemyCaseResolutionRepository:
    return SQLAlchemyCaseResolutionRepository(
        create_session_factory(get_engine(settings)),
        lease_ttl=timedelta(seconds=settings.analysis_stage_lease_seconds),
    )


def build_sprint5c_services(settings: Settings) -> Sprint5CServiceContainer:
    repository = _repository(settings)
    return Sprint5CServiceContainer(
        get_resolution=GetCaseResolution(repository),
        list_resolution_events=ListCaseResolutionEvents(repository),
        list_external_action_intents=ListCaseExternalActionIntents(repository),
        get_external_action_intent=GetExternalActionIntent(repository),
    )


def build_process_case_resolution(settings: Settings) -> ProcessCaseResolution:
    return ProcessCaseResolution(_repository(settings))


def build_execute_external_action_simulation(
    settings: Settings,
) -> ExecuteExternalActionSimulation:
    return ExecuteExternalActionSimulation(
        _repository(settings),
        DeterministicDryRunExternalActionAdapter(),
    )


__all__ = [
    "build_execute_external_action_simulation",
    "build_process_case_resolution",
    "build_sprint5c_services",
    "sprint5c_is_configured",
]
