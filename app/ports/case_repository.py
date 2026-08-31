"""Tenant-scoped persistence ports for Case and Evidence workflows."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.platform.case import Case, CaseStatus, CaseStatusTransition, IdempotencyRecord
from app.platform.evidence import EvidenceMetadata, EvidenceUploadStatus


@dataclass(frozen=True, slots=True)
class CaseListCriteria:
    status: CaseStatus | None = None
    order_ref: str | None = None
    product_ref: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    page: int = 1
    page_size: int = 20
    access_actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    claimed: bool
    record: IdempotencyRecord


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    claimed: bool
    evidence: EvidenceMetadata


@runtime_checkable
class CaseRepository(Protocol):
    def add(self, *, tenant_id: str, case: Case) -> None: ...

    def get(self, *, tenant_id: str, case_id: str) -> Case | None: ...

    def list(self, *, tenant_id: str, criteria: CaseListCriteria) -> tuple[Case, ...]: ...

    def count(self, *, tenant_id: str, criteria: CaseListCriteria) -> int: ...


@runtime_checkable
class CaseStatusHistoryRepository(Protocol):
    def add(self, *, tenant_id: str, transition: CaseStatusTransition) -> None: ...

    def list(self, *, tenant_id: str, case_id: str) -> tuple[CaseStatusTransition, ...]: ...


@runtime_checkable
class EvidenceRepository(Protocol):
    def add(self, *, tenant_id: str, evidence: EvidenceMetadata) -> None: ...

    def claim(self, *, tenant_id: str, evidence: EvidenceMetadata) -> EvidenceClaim: ...

    def get(self, *, tenant_id: str, case_id: str, evidence_id: str) -> EvidenceMetadata | None: ...

    def list(self, *, tenant_id: str, case_id: str) -> tuple[EvidenceMetadata, ...]: ...

    def set_upload_status(
        self,
        *,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
        status: EvidenceUploadStatus,
        updated_at: datetime,
    ) -> EvidenceMetadata | None: ...


@runtime_checkable
class IdempotencyRepository(Protocol):
    def claim(self, *, tenant_id: str, record: IdempotencyRecord) -> IdempotencyClaim: ...
