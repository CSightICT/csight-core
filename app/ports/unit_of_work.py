"""Explicit transaction boundary for Case and Evidence application services."""

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from app.ports.analysis_repository import AnalysisUnitOfWork, AnalysisUnitOfWorkFactory
from app.ports.case_repository import (
    CaseRepository,
    CaseStatusHistoryRepository,
    EvidenceRepository,
    IdempotencyRepository,
)


@runtime_checkable
class CaseUnitOfWork(Protocol):
    cases: CaseRepository
    status_history: CaseStatusHistoryRepository
    evidence: EvidenceRepository
    idempotency: IdempotencyRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def flush(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@runtime_checkable
class CaseUnitOfWorkFactory(Protocol):
    def __call__(self) -> CaseUnitOfWork: ...


__all__ = [
    "AnalysisUnitOfWork",
    "AnalysisUnitOfWorkFactory",
    "CaseUnitOfWork",
    "CaseUnitOfWorkFactory",
]
