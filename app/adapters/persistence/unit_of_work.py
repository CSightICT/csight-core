"""SQLAlchemy transaction boundary for Case and Evidence application services."""

from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.repositories import (
    SQLAlchemyCaseRepository,
    SQLAlchemyCaseStatusHistoryRepository,
    SQLAlchemyEvidenceRepository,
    SQLAlchemyIdempotencyRepository,
)
from app.adapters.persistence.session import create_session_factory
from app.ports.case_repository import (
    CaseRepository,
    CaseStatusHistoryRepository,
    EvidenceRepository,
    IdempotencyRepository,
)


class SQLAlchemyCaseUnitOfWork:
    """One explicit SQLAlchemy session shared by all Case repositories."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.cases: CaseRepository = SQLAlchemyCaseRepository(session)
        self.status_history: CaseStatusHistoryRepository = SQLAlchemyCaseStatusHistoryRepository(
            session
        )
        self.evidence: EvidenceRepository = SQLAlchemyEvidenceRepository(session)
        self.idempotency: IdempotencyRepository = SQLAlchemyIdempotencyRepository(session)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback
        try:
            self.rollback()
        finally:
            self._session.close()

    def flush(self) -> None:
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


class SQLAlchemyCaseUnitOfWorkFactory:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SQLAlchemyCaseUnitOfWork:
        return SQLAlchemyCaseUnitOfWork(self._session_factory())


def create_case_unit_of_work_factory(engine: Engine) -> SQLAlchemyCaseUnitOfWorkFactory:
    return SQLAlchemyCaseUnitOfWorkFactory(create_session_factory(engine))


__all__ = [
    "SQLAlchemyCaseUnitOfWork",
    "SQLAlchemyCaseUnitOfWorkFactory",
    "create_case_unit_of_work_factory",
]
