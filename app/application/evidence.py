"""Tenant-scoped image Evidence commands and queries.

PostgreSQL and object storage cannot share one transaction. The upload service
therefore records ``PENDING`` first, promotes to ``AVAILABLE`` only after the
private object write, and uses best-effort delete/``FAILED`` compensation.
"""

from __future__ import annotations

import hashlib
import hmac
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

from pydantic import BaseModel, ConfigDict, Field

from app.platform.errors import (
    CaseNotFoundError,
    EmptyFileError,
    EvidenceNotFoundError,
    EvidenceUploadFailedError,
    FileTooLargeError,
    ImageDimensionLimitExceededError,
    InvalidFileTypeError,
    InvalidImageContentError,
    StorageUnavailableError,
)
from app.platform.evidence import (
    EvidenceMetadata,
    EvidenceType,
    EvidenceUploadStatus,
    build_evidence_object_key,
)
from app.platform.tenant import Permission, Principal
from app.ports.file_inspection import EmptyFileError as InspectionEmptyFileError
from app.ports.file_inspection import (
    FileInspector,
    ImageContentTypeMismatchError,
    ImageInspectionResult,
    ImagePixelLimitError,
    InvalidImageError,
    UnsupportedImageTypeError,
)
from app.ports.file_inspection import (
    FileTooLargeError as InspectionFileTooLargeError,
)
from app.ports.observability import CompensationFailureObserver, CompensationStep
from app.ports.runtime import Clock, IdGenerator
from app.ports.storage import ObjectStorage, ReadableObjectStorage, StoredObject
from app.ports.unit_of_work import CaseUnitOfWorkFactory


class EvidenceAccessUrl(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    url: str = Field(min_length=1, repr=False)
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceContent:
    evidence_id: str
    content: bytes
    content_type: str
    sha256: str


class AddImageEvidence:
    """Validate an image, persist lifecycle metadata, and store its private bytes."""

    def __init__(
        self,
        *,
        uow_factory: CaseUnitOfWorkFactory,
        storage: ObjectStorage,
        file_inspector: FileInspector,
        storage_bucket: str,
        clock: Clock,
        id_generator: IdGenerator,
        compensation_observer: CompensationFailureObserver,
    ) -> None:
        if not storage_bucket.strip():
            raise ValueError("storage_bucket must not be empty")
        self._uow_factory = uow_factory
        self._storage = storage
        self._file_inspector = file_inspector
        self._storage_bucket = storage_bucket
        self._clock = clock
        self._id_generator = id_generator
        self._compensation_observer = compensation_observer

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        content: BinaryIO,
        filename: str | None,
        declared_content_type: str | None,
        evidence_type: EvidenceType = EvidenceType.IMAGE,
    ) -> EvidenceMetadata:
        if evidence_type is not EvidenceType.IMAGE:
            raise InvalidFileTypeError("Only IMAGE evidence is supported in this sprint.")
        self._require_case(principal=principal, case_id=case_id)
        # A resource outside the principal's tenant is always hidden as 404,
        # independently of role. QUALITY_VIEWER can already read in-tenant Cases,
        # so resolving the scoped parent before the write permission check does not
        # reveal any resource it could not otherwise query.
        principal.require(Permission.EVIDENCE_UPLOAD)
        inspected = self._inspect(
            content=content,
            filename=filename,
            declared_content_type=declared_content_type,
        )

        evidence_id = self._id_generator.new_id()
        now = self._clock.now().astimezone(UTC)
        object_key = build_evidence_object_key(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            evidence_id=evidence_id,
        )
        pending = EvidenceMetadata(
            id=evidence_id,
            tenant_id=principal.tenant_id,
            case_id=case_id,
            evidence_type=EvidenceType.IMAGE,
            upload_status=EvidenceUploadStatus.PENDING,
            storage_bucket=self._storage_bucket,
            object_key=object_key,
            original_filename=inspected.original_filename,
            content_type=inspected.content_type,
            size_bytes=inspected.size_bytes,
            sha256=inspected.sha256,
            width=inspected.width,
            height=inspected.height,
            created_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._uow_factory() as uow:
                uow.evidence.add(
                    tenant_id=principal.tenant_id,
                    evidence=pending,
                )
                uow.flush()
                uow.commit()
        except Exception as exc:
            raise EvidenceUploadFailedError() from exc

        try:
            stored = self._storage.put(
                key=object_key,
                content=content,
                length=inspected.size_bytes,
                content_type=inspected.content_type,
                sha256=inspected.sha256,
            )
        except Exception as exc:
            self._compensate_failed_upload(pending)
            raise StorageUnavailableError() from exc

        if not self._object_matches(expected=pending, actual=stored):
            self._compensate_failed_upload(pending, additional_key=stored.key)
            raise EvidenceUploadFailedError("Stored object metadata did not match the upload.")

        try:
            return self._set_upload_status(
                evidence=pending,
                status=EvidenceUploadStatus.AVAILABLE,
            )
        except Exception as exc:
            self._compensate_failed_upload(pending)
            raise EvidenceUploadFailedError() from exc

    def _require_case(self, *, principal: Principal, case_id: str) -> None:
        with self._uow_factory() as uow:
            case = uow.cases.get(tenant_id=principal.tenant_id, case_id=case_id)
        if case is None:
            raise CaseNotFoundError()

    def _inspect(
        self,
        *,
        content: BinaryIO,
        filename: str | None,
        declared_content_type: str | None,
    ) -> ImageInspectionResult:
        try:
            return self._file_inspector.inspect(
                content=content,
                filename=filename,
                declared_content_type=declared_content_type,
            )
        except InspectionFileTooLargeError as exc:
            raise FileTooLargeError() from exc
        except InspectionEmptyFileError as exc:
            raise EmptyFileError() from exc
        except ImagePixelLimitError as exc:
            raise ImageDimensionLimitExceededError() from exc
        except (UnsupportedImageTypeError, ImageContentTypeMismatchError) as exc:
            raise InvalidFileTypeError() from exc
        except InvalidImageError as exc:
            raise InvalidImageContentError() from exc

    @staticmethod
    def _object_matches(*, expected: EvidenceMetadata, actual: StoredObject) -> bool:
        return (
            actual.bucket,
            actual.key,
            actual.content_type,
            actual.size_bytes,
            actual.sha256,
        ) == (
            expected.storage_bucket,
            expected.object_key,
            expected.content_type,
            expected.size_bytes,
            expected.sha256,
        )

    def _set_upload_status(
        self,
        *,
        evidence: EvidenceMetadata,
        status: EvidenceUploadStatus,
    ) -> EvidenceMetadata:
        updated_at = self._clock.now().astimezone(UTC)
        with self._uow_factory() as uow:
            updated = uow.evidence.set_upload_status(
                tenant_id=evidence.tenant_id,
                case_id=evidence.case_id,
                evidence_id=evidence.id,
                status=status,
                updated_at=updated_at,
            )
            if updated is None:
                raise EvidenceNotFoundError()
            uow.flush()
            uow.commit()
        return updated

    def _compensate_failed_upload(
        self,
        evidence: EvidenceMetadata,
        *,
        additional_key: str | None = None,
    ) -> None:
        keys = (evidence.object_key,)
        if additional_key is not None and additional_key != evidence.object_key:
            keys += (additional_key,)
        for key in keys:
            try:
                self._storage.delete(key)
            except Exception as exc:
                self._report_compensation_failure(
                    evidence=evidence,
                    step="object_delete",
                    error=exc,
                )
        try:
            self._set_upload_status(evidence=evidence, status=EvidenceUploadStatus.FAILED)
        except Exception as exc:
            self._report_compensation_failure(
                evidence=evidence,
                step="evidence_mark_failed",
                error=exc,
            )

    def _report_compensation_failure(
        self,
        *,
        evidence: EvidenceMetadata,
        step: CompensationStep,
        error: Exception,
    ) -> None:
        # Observability must not replace the original upload failure if the log
        # sink itself is unavailable.
        with suppress(Exception):
            self._compensation_observer.record_failure(
                step=step,
                tenant_id=evidence.tenant_id,
                case_id=evidence.case_id,
                evidence_id=evidence.id,
                error_type=type(error).__name__,
            )


class ListCaseEvidence:
    def __init__(self, *, uow_factory: CaseUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, *, principal: Principal, case_id: str) -> tuple[EvidenceMetadata, ...]:
        principal.require(Permission.CASE_READ)
        with self._uow_factory() as uow:
            case = uow.cases.get(tenant_id=principal.tenant_id, case_id=case_id)
            if case is None:
                raise CaseNotFoundError()
            return uow.evidence.list(tenant_id=principal.tenant_id, case_id=case_id)


class GetEvidenceMetadata:
    def __init__(self, *, uow_factory: CaseUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceMetadata:
        principal.require(Permission.CASE_READ)
        with self._uow_factory() as uow:
            case = uow.cases.get(tenant_id=principal.tenant_id, case_id=case_id)
            if case is None:
                raise CaseNotFoundError()
            evidence = uow.evidence.get(
                tenant_id=principal.tenant_id,
                case_id=case_id,
                evidence_id=evidence_id,
            )
        if evidence is None:
            raise EvidenceNotFoundError()
        return evidence


class CreateEvidenceAccessUrl:
    def __init__(
        self,
        *,
        get_evidence: GetEvidenceMetadata,
        storage: ObjectStorage,
        clock: Clock,
        ttl: timedelta,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        self._get_evidence = get_evidence
        self._storage = storage
        self._clock = clock
        self._ttl = ttl

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceAccessUrl:
        evidence = self._get_evidence.execute(
            principal=principal,
            case_id=case_id,
            evidence_id=evidence_id,
        )
        if evidence.upload_status is not EvidenceUploadStatus.AVAILABLE:
            raise EvidenceUploadFailedError("The evidence is not available for access.")
        try:
            object_exists = self._storage.exists(evidence.object_key)
        except Exception as exc:
            raise StorageUnavailableError() from exc
        if not object_exists:
            raise EvidenceUploadFailedError("The evidence object is not available for access.")
        try:
            url = self._storage.presign_get(evidence.object_key, expires_in=self._ttl)
        except Exception as exc:
            raise StorageUnavailableError() from exc
        return EvidenceAccessUrl(
            evidence_id=evidence.id,
            url=url,
            expires_at=self._clock.now().astimezone(UTC) + self._ttl,
        )


class ReadEvidenceContent:
    """Read one tenant-scoped private image through the authenticated API boundary."""

    def __init__(
        self,
        *,
        get_evidence: GetEvidenceMetadata,
        storage: ReadableObjectStorage,
        max_bytes: int,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._get_evidence = get_evidence
        self._storage = storage
        self._max_bytes = max_bytes

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceContent:
        evidence = self._get_evidence.execute(
            principal=principal,
            case_id=case_id,
            evidence_id=evidence_id,
        )
        if evidence.upload_status is not EvidenceUploadStatus.AVAILABLE:
            raise EvidenceUploadFailedError("The evidence is not available for access.")
        if evidence.size_bytes > self._max_bytes:
            raise EvidenceUploadFailedError("The evidence exceeds the configured read limit.")
        try:
            if not self._storage.exists(evidence.object_key):
                raise EvidenceUploadFailedError("The evidence object is not available for access.")
            content = self._storage.get(evidence.object_key, max_bytes=self._max_bytes)
        except EvidenceUploadFailedError:
            raise
        except Exception as exc:
            raise StorageUnavailableError() from exc
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if len(content) != evidence.size_bytes or not hmac.compare_digest(
            actual_sha256, evidence.sha256
        ):
            raise EvidenceUploadFailedError("The evidence object failed integrity verification.")
        return EvidenceContent(
            evidence_id=evidence.id,
            content=content,
            content_type=evidence.content_type,
            sha256=evidence.sha256,
        )
