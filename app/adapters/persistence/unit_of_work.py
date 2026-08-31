"""SQLAlchemy transaction boundary for Case and Evidence application services."""

from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.analysis_repositories import (
    SQLAlchemyAnalysisEvidenceSnapshotRepository,
    SQLAlchemyAnalysisRequestIdempotencyRepository,
    SQLAlchemyAnalysisRunRepository,
    SQLAlchemyAnalysisStageAttemptRepository,
    SQLAlchemyAnalysisStageRunRepository,
    SQLAlchemyLLMExtractionResultRepository,
    SQLAlchemyLLMExtractionResultV2Repository,
    SQLAlchemyOutboxEventRepository,
    SQLAlchemyVisionAnalysisResultRepository,
)
from app.adapters.persistence.repositories import (
    SQLAlchemyCaseRepository,
    SQLAlchemyCaseStatusHistoryRepository,
    SQLAlchemyEvidenceRepository,
    SQLAlchemyIdempotencyRepository,
)
from app.adapters.persistence.session import create_session_factory
from app.ports.analysis_repository import (
    AnalysisEvidenceSnapshotRepository,
    AnalysisRequestIdempotencyRepository,
    AnalysisRunRepository,
    AnalysisStageAttemptRepository,
    AnalysisStageRunRepository,
    AnalysisUnitOfWork,
    LLMExtractionResultRepository,
    LLMExtractionResultV2Repository,
    OutboxEventRepository,
    VisionAnalysisResultRepository,
)
from app.ports.case_repository import (
    CaseRepository,
    CaseStatusHistoryRepository,
    EvidenceRepository,
    IdempotencyRepository,
)


class SQLAlchemyCaseUnitOfWork:
    """One explicit SQLAlchemy session shared by all Case repositories."""

    def __init__(
        self,
        session: Session,
        *,
        sensitive_payload_retention_policy_version: str = "development/30d",
        sensitive_payload_retention_days: int = 30,
    ) -> None:
        self._session = session
        self.cases: CaseRepository = SQLAlchemyCaseRepository(
            session,
            sensitive_payload_retention_policy_version=(sensitive_payload_retention_policy_version),
            sensitive_payload_retention_days=sensitive_payload_retention_days,
        )
        self.evidence: EvidenceRepository = SQLAlchemyEvidenceRepository(session)
        self.status_history: CaseStatusHistoryRepository = SQLAlchemyCaseStatusHistoryRepository(
            session
        )
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
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        sensitive_payload_retention_policy_version: str = "development/30d",
        sensitive_payload_retention_days: int = 30,
    ) -> None:
        self._session_factory = session_factory
        self._sensitive_payload_retention_policy_version = (
            sensitive_payload_retention_policy_version
        )
        self._sensitive_payload_retention_days = sensitive_payload_retention_days

    def __call__(self) -> SQLAlchemyCaseUnitOfWork:
        return SQLAlchemyCaseUnitOfWork(
            self._session_factory(),
            sensitive_payload_retention_policy_version=(
                self._sensitive_payload_retention_policy_version
            ),
            sensitive_payload_retention_days=self._sensitive_payload_retention_days,
        )


class SQLAlchemyAnalysisUnitOfWork(AnalysisUnitOfWork):
    """One explicit session for Analysis Run, result, and Outbox transactions."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.cases: CaseRepository = SQLAlchemyCaseRepository(session)
        self.evidence: EvidenceRepository = SQLAlchemyEvidenceRepository(session)
        self.analysis_runs: AnalysisRunRepository = SQLAlchemyAnalysisRunRepository(session)
        self.stage_runs: AnalysisStageRunRepository = SQLAlchemyAnalysisStageRunRepository(session)
        self.stage_attempts: AnalysisStageAttemptRepository = (
            SQLAlchemyAnalysisStageAttemptRepository(session)
        )
        self.request_idempotency: AnalysisRequestIdempotencyRepository = (
            SQLAlchemyAnalysisRequestIdempotencyRepository(session)
        )
        self.extraction_results: LLMExtractionResultRepository = (
            SQLAlchemyLLMExtractionResultRepository(session)
        )
        self.extraction_results_v2: LLMExtractionResultV2Repository = (
            SQLAlchemyLLMExtractionResultV2Repository(session)
        )
        self.evidence_snapshots: AnalysisEvidenceSnapshotRepository = (
            SQLAlchemyAnalysisEvidenceSnapshotRepository(session)
        )
        self.vision_results: VisionAnalysisResultRepository = (
            SQLAlchemyVisionAnalysisResultRepository(session)
        )
        self.outbox: OutboxEventRepository = SQLAlchemyOutboxEventRepository(session)

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


class SQLAlchemyAnalysisUnitOfWorkFactory:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SQLAlchemyAnalysisUnitOfWork:
        return SQLAlchemyAnalysisUnitOfWork(self._session_factory())


def create_case_unit_of_work_factory(
    engine: Engine,
    *,
    sensitive_payload_retention_policy_version: str = "development/30d",
    sensitive_payload_retention_days: int = 30,
) -> SQLAlchemyCaseUnitOfWorkFactory:
    return SQLAlchemyCaseUnitOfWorkFactory(
        create_session_factory(engine),
        sensitive_payload_retention_policy_version=sensitive_payload_retention_policy_version,
        sensitive_payload_retention_days=sensitive_payload_retention_days,
    )


def create_analysis_unit_of_work_factory(engine: Engine) -> SQLAlchemyAnalysisUnitOfWorkFactory:
    return SQLAlchemyAnalysisUnitOfWorkFactory(create_session_factory(engine))


__all__ = [
    "SQLAlchemyAnalysisUnitOfWork",
    "SQLAlchemyAnalysisUnitOfWorkFactory",
    "SQLAlchemyCaseUnitOfWork",
    "SQLAlchemyCaseUnitOfWorkFactory",
    "create_analysis_unit_of_work_factory",
    "create_case_unit_of_work_factory",
]
