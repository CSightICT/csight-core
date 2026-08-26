"""Tenant-scoped persistence ports for append-only analysis workflows."""

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from app.platform.analysis.enums import (
    AnalysisAttemptStatus,
    AnalysisPipeline,
    AnalysisRunStatus,
    AnalysisStageStatus,
)
from app.platform.analysis.models import (
    AnalysisFailure,
    AnalysisRequestIdempotencyRecord,
    AnalysisRun,
    AnalysisStageAttempt,
    AnalysisStageRun,
    OutboxEvent,
    ProviderExecutionMetadata,
)
from app.platform.analysis.schemas import (
    AnalysisEvidenceSnapshot,
    LLMExtractionResultRecord,
    VisionAnalysisResultRecord,
)
from app.ports.case_repository import CaseRepository, EvidenceRepository


@dataclass(frozen=True, slots=True)
class AnalysisRunListCriteria:
    status: AnalysisRunStatus | None = None
    pipeline: AnalysisPipeline | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class AnalysisRequestIdempotencyClaim:
    claimed: bool
    record: AnalysisRequestIdempotencyRecord


@runtime_checkable
class AnalysisRunRepository(Protocol):
    def add(self, *, tenant_id: str, run: AnalysisRun) -> None: ...

    def get(
        self,
        *,
        tenant_id: str,
        case_id: str,
        analysis_run_id: str,
    ) -> AnalysisRun | None: ...

    def list(
        self,
        *,
        tenant_id: str,
        case_id: str,
        criteria: AnalysisRunListCriteria,
    ) -> tuple[AnalysisRun, ...]: ...

    def count(
        self,
        *,
        tenant_id: str,
        case_id: str,
        criteria: AnalysisRunListCriteria,
    ) -> int: ...

    def latest(self, *, tenant_id: str, case_id: str) -> AnalysisRun | None: ...

    def transition(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        expected_status: AnalysisRunStatus,
        target_status: AnalysisRunStatus,
        now: datetime,
        failure: AnalysisFailure | None = None,
    ) -> AnalysisRun | None: ...


@runtime_checkable
class AnalysisStageRunRepository(Protocol):
    def add(self, *, tenant_id: str, stage_run: AnalysisStageRun) -> None: ...

    def get(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        stage_run_id: str,
    ) -> AnalysisStageRun | None: ...

    def list(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
    ) -> tuple[AnalysisStageRun, ...]: ...

    def transition(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        stage_run_id: str,
        expected_status: AnalysisStageStatus,
        target_status: AnalysisStageStatus,
        now: datetime,
        next_attempt_at: datetime | None = None,
        failure: AnalysisFailure | None = None,
    ) -> AnalysisStageRun | None: ...

    def claim_for_execution(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        stage_run_id: str,
        claim_token: str,
        now: datetime,
        claim_expires_at: datetime,
    ) -> AnalysisStageRun | None: ...

    def transition_if_claimed(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
        stage_run_id: str,
        claim_token: str,
        target_status: AnalysisStageStatus,
        now: datetime,
        next_attempt_at: datetime | None = None,
        failure: AnalysisFailure | None = None,
        provider_execution: ProviderExecutionMetadata | None = None,
    ) -> AnalysisStageRun | None: ...


@runtime_checkable
class AnalysisStageAttemptRepository(Protocol):
    def add(self, *, tenant_id: str, attempt: AnalysisStageAttempt) -> None: ...

    def get(
        self,
        *,
        tenant_id: str,
        stage_run_id: str,
        attempt_number: int,
    ) -> AnalysisStageAttempt | None: ...

    def list(
        self,
        *,
        tenant_id: str,
        stage_run_id: str,
    ) -> tuple[AnalysisStageAttempt, ...]: ...

    def finalize_if_claimed(
        self,
        *,
        tenant_id: str,
        stage_run_id: str,
        attempt_number: int,
        claim_token: str,
        target_status: AnalysisAttemptStatus,
        completed_at: datetime,
        failure: AnalysisFailure | None = None,
        provider_execution: ProviderExecutionMetadata | None = None,
    ) -> AnalysisStageAttempt | None: ...

    def abandon_stale(
        self,
        *,
        tenant_id: str,
        stage_run_id: str,
        stale_before: datetime,
        abandoned_at: datetime,
        failure: AnalysisFailure,
    ) -> int: ...


@runtime_checkable
class AnalysisRequestIdempotencyRepository(Protocol):
    def claim(
        self,
        *,
        tenant_id: str,
        record: AnalysisRequestIdempotencyRecord,
    ) -> AnalysisRequestIdempotencyClaim: ...


@runtime_checkable
class LLMExtractionResultRepository(Protocol):
    def add(self, *, tenant_id: str, result: LLMExtractionResultRecord) -> None: ...

    def get_by_run(
        self,
        *,
        tenant_id: str,
        analysis_run_id: str,
    ) -> LLMExtractionResultRecord | None: ...


@runtime_checkable
class AnalysisEvidenceSnapshotRepository(Protocol):
    def add(self, *, tenant_id: str, snapshot: AnalysisEvidenceSnapshot) -> None: ...

    def list(
        self, *, tenant_id: str, analysis_run_id: str
    ) -> tuple[AnalysisEvidenceSnapshot, ...]: ...


@runtime_checkable
class VisionAnalysisResultRepository(Protocol):
    def add(self, *, tenant_id: str, result: VisionAnalysisResultRecord) -> None: ...

    def list_by_run(
        self, *, tenant_id: str, analysis_run_id: str
    ) -> tuple[VisionAnalysisResultRecord, ...]: ...


@runtime_checkable
class OutboxEventRepository(Protocol):
    def add(self, *, tenant_id: str, event: OutboxEvent) -> None: ...

    def claim_batch(
        self,
        *,
        now: datetime,
        stale_before: datetime,
        claim_token: str,
        claimed_by: str,
        limit: int,
    ) -> tuple[OutboxEvent, ...]: ...

    def mark_published(
        self,
        *,
        tenant_id: str,
        event_id: str,
        claim_token: str,
        published_at: datetime,
    ) -> OutboxEvent | None: ...

    def release_for_retry(
        self,
        *,
        tenant_id: str,
        event_id: str,
        claim_token: str,
        available_at: datetime,
        last_error: str,
        now: datetime,
    ) -> OutboxEvent | None: ...

    def mark_failed(
        self,
        *,
        tenant_id: str,
        event_id: str,
        claim_token: str,
        last_error: str,
        now: datetime,
    ) -> OutboxEvent | None: ...

    def recover_stale(
        self,
        *,
        stale_before: datetime,
        available_at: datetime,
    ) -> int: ...


@runtime_checkable
class AnalysisUnitOfWork(Protocol):
    cases: CaseRepository
    evidence: EvidenceRepository
    analysis_runs: AnalysisRunRepository
    stage_runs: AnalysisStageRunRepository
    stage_attempts: AnalysisStageAttemptRepository
    request_idempotency: AnalysisRequestIdempotencyRepository
    extraction_results: LLMExtractionResultRepository
    evidence_snapshots: AnalysisEvidenceSnapshotRepository
    vision_results: VisionAnalysisResultRepository
    outbox: OutboxEventRepository

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
class AnalysisUnitOfWorkFactory(Protocol):
    def __call__(self) -> AnalysisUnitOfWork: ...


__all__ = [
    "AnalysisEvidenceSnapshotRepository",
    "AnalysisRequestIdempotencyClaim",
    "AnalysisRequestIdempotencyRepository",
    "AnalysisRunListCriteria",
    "AnalysisRunRepository",
    "AnalysisStageAttemptRepository",
    "AnalysisStageRunRepository",
    "AnalysisUnitOfWork",
    "AnalysisUnitOfWorkFactory",
    "LLMExtractionResultRepository",
    "OutboxEventRepository",
    "VisionAnalysisResultRepository",
]
