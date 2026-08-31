"""Ports for tenant-scoped privacy and Evidence consistency operations."""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from app.platform.evidence import EvidenceUploadStatus
from app.platform.privacy_lifecycle import (
    EvidenceLifecyclePage,
    EvidenceLifecycleRecord,
    EvidencePurgeEventType,
    LifecycleMutationResult,
    SensitivePayloadLifecyclePage,
    SensitivePayloadLifecycleRecord,
)


@runtime_checkable
class PrivacyLifecycleRepository(Protocol):
    def list_expired_sensitive_payloads(
        self,
        *,
        tenant_id: str,
        expired_before: datetime,
        limit: int,
    ) -> SensitivePayloadLifecyclePage: ...

    def purge_sensitive_payload(
        self,
        *,
        candidate: SensitivePayloadLifecycleRecord,
        actor_id: str | None,
        correlation_id: str,
        occurred_at: datetime,
    ) -> LifecycleMutationResult: ...

    def list_evidence_for_reconciliation(
        self,
        *,
        tenant_id: str,
        stale_pending_before: datetime,
        limit: int,
    ) -> EvidenceLifecyclePage: ...

    def get_evidence_by_object_key(
        self,
        *,
        tenant_id: str,
        object_key: str,
    ) -> EvidenceLifecycleRecord | None: ...

    def case_exists(self, *, tenant_id: str, case_id: str) -> bool: ...

    def reconcile_evidence_status(
        self,
        *,
        record: EvidenceLifecycleRecord,
        target_status: EvidenceUploadStatus,
        reason: str,
        actor_id: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> LifecycleMutationResult: ...

    def record_evidence_purge_event(
        self,
        *,
        event_type: EvidencePurgeEventType,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
        reason: str,
        operation_key: str,
        actor_id: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> bool: ...


@runtime_checkable
class PrivacyLifecycleUnitOfWork(Protocol):
    lifecycle: PrivacyLifecycleRepository

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
class PrivacyLifecycleUnitOfWorkFactory(Protocol):
    def __call__(self) -> PrivacyLifecycleUnitOfWork: ...


__all__ = [
    "PrivacyLifecycleRepository",
    "PrivacyLifecycleUnitOfWork",
    "PrivacyLifecycleUnitOfWorkFactory",
]
