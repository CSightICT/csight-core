"""Composition root for server-side operator read projections."""

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.operator_read import SQLAlchemyOperatorReadRepository
from app.adapters.persistence.session import create_session_factory
from app.application.operator_read import (
    GetWorkflowSnapshot,
    ListOperatorCases,
    ListOperatorReviews,
)
from app.bootstrap.settings import Settings
from app.interface.http.operator_read_services import OperatorReadServiceContainer


def operator_read_is_configured(settings: Settings) -> bool:
    return settings.database_url_value is not None


def build_operator_read_services(settings: Settings) -> OperatorReadServiceContainer:
    repository = SQLAlchemyOperatorReadRepository(create_session_factory(get_engine(settings)))
    return OperatorReadServiceContainer(
        list_cases=ListOperatorCases(repository),
        list_reviews=ListOperatorReviews(repository),
        get_workflow_snapshot=GetWorkflowSnapshot(repository),
    )


__all__ = ["build_operator_read_services", "operator_read_is_configured"]
