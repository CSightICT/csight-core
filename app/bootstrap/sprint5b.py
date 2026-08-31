"""Sprint 5B human review composition root."""

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.human_review import SQLAlchemyHumanReviewRepository
from app.adapters.persistence.session import create_session_factory
from app.application.human_review import (
    CreateReviewTaskFromPolicy,
    GetHumanReviewTask,
    HumanReviewActions,
    ListHumanReviewTasks,
    ListReviewAssignees,
)
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint5BServiceContainer


def sprint5b_is_configured(settings: Settings) -> bool:
    return settings.database_url_value is not None


def _repository(settings: Settings) -> SQLAlchemyHumanReviewRepository:
    return SQLAlchemyHumanReviewRepository(create_session_factory(get_engine(settings)))


def build_sprint5b_services(settings: Settings) -> Sprint5BServiceContainer:
    repository = _repository(settings)
    return Sprint5BServiceContainer(
        list_tasks=ListHumanReviewTasks(repository),
        list_assignees=ListReviewAssignees(repository),
        get_task=GetHumanReviewTask(repository),
        actions=HumanReviewActions(repository),
    )


def build_create_review_task(settings: Settings) -> CreateReviewTaskFromPolicy:
    return CreateReviewTaskFromPolicy(_repository(settings))


__all__ = ["build_create_review_task", "build_sprint5b_services", "sprint5b_is_configured"]
