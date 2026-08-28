"""Evidence application workflow, isolation, and compensation tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import TracebackType
from typing import BinaryIO, cast

import pytest

from app.application.evidence import (
    AddImageEvidence,
    CreateEvidenceAccessUrl,
    GetEvidenceMetadata,
    ListCaseEvidence,
    ReadEvidenceContent,
)
from app.platform.case import (
    Case,
    CaseStatus,
    CaseStatusTransition,
    DomainType,
    IdempotencyRecord,
    RequestedAction,
)
from app.platform.errors import (
    CaseNotFoundError,
    EmptyFileError,
    EvidenceUploadFailedError,
    ForbiddenError,
    StorageUnavailableError,
)
from app.platform.evidence import EvidenceMetadata, EvidenceUploadStatus
from app.platform.tenant import Principal, Role
from app.ports.case_repository import CaseListCriteria, IdempotencyClaim
from app.ports.file_inspection import EmptyFileError as InspectionEmptyFileError
from app.ports.file_inspection import ImageInspectionResult
from app.ports.observability import CompensationStep
from app.ports.storage import StoredObject
from app.ports.unit_of_work import CaseUnitOfWork

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 26, 2, 3, 4, tzinfo=UTC)


class StaticClock:
    def now(self) -> datetime:
        return NOW


class OneId:
    def new_id(self) -> str:
        return "00000000-0000-4000-8000-000000000099"


class Cases:
    def __init__(self, case: Case) -> None:
        self.case = case

    def add(self, *, tenant_id: str, case: Case) -> None:
        if tenant_id != case.tenant_id:
            raise ValueError("case tenant mismatch")
        self.case = case

    def get(self, *, tenant_id: str, case_id: str) -> Case | None:
        if (tenant_id, case_id) == (self.case.tenant_id, self.case.id):
            return self.case
        return None

    def list(self, *, tenant_id: str, criteria: CaseListCriteria) -> tuple[Case, ...]:
        del criteria
        return (self.case,) if tenant_id == self.case.tenant_id else ()

    def count(self, *, tenant_id: str, criteria: CaseListCriteria) -> int:
        return len(self.list(tenant_id=tenant_id, criteria=criteria))


class Evidence:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str, str], EvidenceMetadata] = {}
        self.statuses: list[EvidenceUploadStatus] = []
        self.fail_available = False
        self.fail_failed = False

    def add(self, *, tenant_id: str, evidence: EvidenceMetadata) -> None:
        if tenant_id != evidence.tenant_id:
            raise ValueError("evidence tenant mismatch")
        self.items[(evidence.tenant_id, evidence.case_id, evidence.id)] = evidence

    def get(self, *, tenant_id: str, case_id: str, evidence_id: str) -> EvidenceMetadata | None:
        return self.items.get((tenant_id, case_id, evidence_id))

    def list(self, *, tenant_id: str, case_id: str) -> tuple[EvidenceMetadata, ...]:
        return tuple(
            item
            for (scope, parent, _), item in self.items.items()
            if (scope, parent) == (tenant_id, case_id)
        )

    def set_upload_status(
        self,
        *,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
        status: EvidenceUploadStatus,
        updated_at: datetime,
    ) -> EvidenceMetadata | None:
        if status is EvidenceUploadStatus.AVAILABLE and self.fail_available:
            raise RuntimeError("database finalization failed")
        if status is EvidenceUploadStatus.FAILED and self.fail_failed:
            raise RuntimeError("database compensation failed with a secret detail")
        key = (tenant_id, case_id, evidence_id)
        current = self.items.get(key)
        if current is None:
            return None
        updated = current.model_copy(update={"upload_status": status, "updated_at": updated_at})
        self.items[key] = updated
        self.statuses.append(status)
        return updated


class History:
    def add(self, *, tenant_id: str, transition: CaseStatusTransition) -> None:
        if tenant_id != transition.tenant_id:
            raise ValueError("history tenant mismatch")

    def list(self, *, tenant_id: str, case_id: str) -> tuple[CaseStatusTransition, ...]:
        del tenant_id, case_id
        return ()


class Idempotency:
    def claim(self, *, tenant_id: str, record: IdempotencyRecord) -> IdempotencyClaim:
        raise AssertionError((tenant_id, record))


class UnitOfWork:
    def __init__(self, case: Case) -> None:
        self.cases = Cases(case)
        self.evidence = Evidence()
        self.status_history = History()
        self.idempotency = Idempotency()

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class Factory:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def __call__(self) -> CaseUnitOfWork:
        return cast(CaseUnitOfWork, self.uow)


class Inspector:
    def __init__(self) -> None:
        self.calls = 0
        self.error: Exception | None = None

    def inspect(
        self,
        *,
        content: BinaryIO,
        filename: str | None,
        declared_content_type: str | None,
    ) -> ImageInspectionResult:
        del content, filename, declared_content_type
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ImageInspectionResult(
            original_filename="photo.png",
            image_format="PNG",
            extension="png",
            content_type="image/png",
            size_bytes=7,
            sha256=hashlib.sha256(b"content").hexdigest(),
            width=8,
            height=6,
        )


class Storage:
    def __init__(self) -> None:
        self.put_keys: list[str] = []
        self.deleted: list[str] = []
        self.presigned: list[str] = []
        self.fail_put = False
        self.fail_delete = False
        self.fail_exists = False
        self.fail_get = False
        self.contents: dict[str, bytes] = {}

    def put(
        self,
        *,
        key: str,
        content: BinaryIO,
        length: int,
        content_type: str,
        sha256: str,
    ) -> StoredObject:
        value = content.read()
        self.put_keys.append(key)
        if self.fail_put:
            raise RuntimeError("minio unavailable")
        self.contents[key] = value
        return StoredObject(
            bucket="evidence",
            key=key,
            content_type=content_type,
            size_bytes=length,
            sha256=sha256,
        )

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        if self.fail_delete:
            raise RuntimeError("delete failed at http://secret-storage.test")

    def exists(self, key: str) -> bool:
        if self.fail_exists:
            raise RuntimeError("object HEAD failed")
        return key in self.put_keys and key not in self.deleted

    def presign_get(self, key: str, *, expires_in: timedelta) -> str:
        self.presigned.append(key)
        return f"http://objects.test/{key}?expires={int(expires_in.total_seconds())}"

    def get(self, key: str, *, max_bytes: int) -> bytes:
        if self.fail_get:
            raise RuntimeError("object GET failed")
        value = self.contents[key]
        if len(value) > max_bytes:
            raise RuntimeError("read bound exceeded")
        return value

    def is_ready(self) -> bool:
        return True


class RecordingCompensationObserver:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def record_failure(
        self,
        *,
        step: CompensationStep,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
        error_type: str,
    ) -> None:
        self.events.append(
            {
                "step": step,
                "tenant_id": tenant_id,
                "case_id": case_id,
                "evidence_id": evidence_id,
                "error_type": error_type,
            }
        )


def make_case() -> Case:
    return Case(
        id="00000000-0000-4000-8000-000000000001",
        tenant_id="00000000-0000-4000-8000-000000000002",
        domain_type=DomainType.PRODUCT_DEFECT_CS,
        order_ref="ORD-1",
        product_ref="SKU-1",
        customer_message="Damaged item",
        requested_action=RequestedAction.EXCHANGE,
        attributes={},
        status=CaseStatus.RECEIVED,
        created_by="00000000-0000-4000-8000-000000000003",
        created_at=NOW,
        updated_at=NOW,
    )


def principal(*, tenant_id: str | None = None, role: Role = Role.REVIEWER) -> Principal:
    case = make_case()
    return Principal(
        user_id=case.created_by,
        tenant_id=tenant_id or case.tenant_id,
        email="reviewer@example.test",
        display_name="Reviewer",
        roles=frozenset({role}),
    )


def build_service(
    uow: UnitOfWork,
    storage: Storage,
    inspector: Inspector,
    observer: RecordingCompensationObserver | None = None,
) -> AddImageEvidence:
    return AddImageEvidence(
        uow_factory=Factory(uow),
        storage=storage,
        file_inspector=inspector,
        storage_bucket="evidence",
        clock=StaticClock(),
        id_generator=OneId(),
        compensation_observer=observer or RecordingCompensationObserver(),
    )


def test_image_upload_uses_opaque_key_and_becomes_available() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()

    result = build_service(uow, storage, inspector).execute(
        principal=principal(),
        case_id=case.id,
        content=BytesIO(b"content"),
        filename="../../secret.png",
        declared_content_type="image/png",
    )

    expected_key = (
        f"tenants/{case.tenant_id}/cases/{case.id}/evidence/"
        "00000000-0000-4000-8000-000000000099/original"
    )
    assert result.upload_status is EvidenceUploadStatus.AVAILABLE
    assert result.object_key == expected_key
    assert "secret" not in result.object_key
    assert storage.put_keys == [expected_key]
    assert uow.evidence.statuses == [EvidenceUploadStatus.AVAILABLE]


def test_upload_checks_tenant_and_permission_before_inspecting_bytes() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()
    service = build_service(uow, storage, inspector)

    with pytest.raises(CaseNotFoundError):
        service.execute(
            principal=principal(tenant_id="00000000-0000-4000-8000-999999999999"),
            case_id=case.id,
            content=BytesIO(b"content"),
            filename="photo.png",
            declared_content_type="image/png",
        )
    with pytest.raises(CaseNotFoundError):
        service.execute(
            principal=principal(
                tenant_id="00000000-0000-4000-8000-999999999999",
                role=Role.QUALITY_VIEWER,
            ),
            case_id=case.id,
            content=BytesIO(b"content"),
            filename="photo.png",
            declared_content_type="image/png",
        )
    with pytest.raises(ForbiddenError):
        service.execute(
            principal=principal(role=Role.QUALITY_VIEWER),
            case_id=case.id,
            content=BytesIO(b"content"),
            filename="photo.png",
            declared_content_type="image/png",
        )
    assert inspector.calls == 0
    assert storage.put_keys == []


def test_empty_file_error_is_translated_to_public_error() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()
    inspector.error = InspectionEmptyFileError("empty")

    with pytest.raises(EmptyFileError):
        build_service(uow, storage, inspector).execute(
            principal=principal(),
            case_id=case.id,
            content=BytesIO(),
            filename="photo.png",
            declared_content_type="image/png",
        )


def test_storage_failure_marks_row_failed_and_deletes_possible_partial_object() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()
    storage.fail_put = True

    with pytest.raises(StorageUnavailableError):
        build_service(uow, storage, inspector).execute(
            principal=principal(),
            case_id=case.id,
            content=BytesIO(b"content"),
            filename="photo.png",
            declared_content_type="image/png",
        )

    evidence = next(iter(uow.evidence.items.values()))
    assert evidence.upload_status is EvidenceUploadStatus.FAILED
    assert storage.deleted == [evidence.object_key]


def test_database_finalization_failure_deletes_object_and_marks_row_failed() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()
    uow.evidence.fail_available = True

    with pytest.raises(EvidenceUploadFailedError):
        build_service(uow, storage, inspector).execute(
            principal=principal(),
            case_id=case.id,
            content=BytesIO(b"content"),
            filename="photo.png",
            declared_content_type="image/png",
        )

    evidence = next(iter(uow.evidence.items.values()))
    assert evidence.upload_status is EvidenceUploadStatus.FAILED
    assert storage.deleted == [evidence.object_key]


def test_compensation_failures_emit_only_safe_structured_identifiers() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()
    observer = RecordingCompensationObserver()
    storage.fail_put = True
    storage.fail_delete = True
    uow.evidence.fail_failed = True

    with pytest.raises(StorageUnavailableError):
        build_service(uow, storage, inspector, observer).execute(
            principal=principal(),
            case_id=case.id,
            content=BytesIO(b"content"),
            filename="photo.png",
            declared_content_type="image/png",
        )

    evidence = next(iter(uow.evidence.items.values()))
    assert observer.events == [
        {
            "step": "object_delete",
            "tenant_id": evidence.tenant_id,
            "case_id": evidence.case_id,
            "evidence_id": evidence.id,
            "error_type": "RuntimeError",
        },
        {
            "step": "evidence_mark_failed",
            "tenant_id": evidence.tenant_id,
            "case_id": evidence.case_id,
            "evidence_id": evidence.id,
            "error_type": "RuntimeError",
        },
    ]
    serialized_events = repr(observer.events)
    assert "secret-storage" not in serialized_events
    assert "database compensation failed" not in serialized_events
    assert evidence.object_key not in serialized_events


def test_queries_and_signed_url_remain_tenant_scoped() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()
    evidence = build_service(uow, storage, inspector).execute(
        principal=principal(),
        case_id=case.id,
        content=BytesIO(b"content"),
        filename="photo.png",
        declared_content_type="image/png",
    )
    factory = Factory(uow)

    listed = ListCaseEvidence(uow_factory=factory).execute(principal=principal(), case_id=case.id)
    loaded = GetEvidenceMetadata(uow_factory=factory).execute(
        principal=principal(), case_id=case.id, evidence_id=evidence.id
    )
    access = CreateEvidenceAccessUrl(
        get_evidence=GetEvidenceMetadata(uow_factory=factory),
        storage=storage,
        clock=StaticClock(),
        ttl=timedelta(minutes=15),
    ).execute(principal=principal(), case_id=case.id, evidence_id=evidence.id)

    assert listed == (evidence,)
    assert loaded == evidence
    assert access.expires_at == NOW + timedelta(minutes=15)
    assert "expires=900" in access.url
    assert access.url not in repr(access)
    with pytest.raises(CaseNotFoundError):
        GetEvidenceMetadata(uow_factory=factory).execute(
            principal=principal(tenant_id="00000000-0000-4000-8000-999999999999"),
            case_id=case.id,
            evidence_id=evidence.id,
        )


def test_signed_url_requires_the_available_object_to_exist() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()
    evidence = build_service(uow, storage, inspector).execute(
        principal=principal(),
        case_id=case.id,
        content=BytesIO(b"content"),
        filename="photo.png",
        declared_content_type="image/png",
    )
    service = CreateEvidenceAccessUrl(
        get_evidence=GetEvidenceMetadata(uow_factory=Factory(uow)),
        storage=storage,
        clock=StaticClock(),
        ttl=timedelta(minutes=15),
    )

    storage.delete(evidence.object_key)
    with pytest.raises(EvidenceUploadFailedError):
        service.execute(principal=principal(), case_id=case.id, evidence_id=evidence.id)
    assert storage.presigned == []

    storage.fail_exists = True
    with pytest.raises(StorageUnavailableError):
        service.execute(principal=principal(), case_id=case.id, evidence_id=evidence.id)
    assert storage.presigned == []


def test_authenticated_content_read_verifies_size_and_sha256() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()
    evidence = build_service(uow, storage, inspector).execute(
        principal=principal(),
        case_id=case.id,
        content=BytesIO(b"content"),
        filename="photo.png",
        declared_content_type="image/png",
    )
    service = ReadEvidenceContent(
        get_evidence=GetEvidenceMetadata(uow_factory=Factory(uow)),
        storage=storage,
        max_bytes=1024,
    )

    result = service.execute(principal=principal(), case_id=case.id, evidence_id=evidence.id)

    assert result.content == b"content"
    assert result.content_type == "image/png"
    assert result.sha256 == hashlib.sha256(b"content").hexdigest()
    with pytest.raises(CaseNotFoundError):
        service.execute(
            principal=principal(tenant_id="00000000-0000-4000-8000-999999999999"),
            case_id=case.id,
            evidence_id=evidence.id,
        )


def test_authenticated_content_read_fails_closed_on_storage_or_integrity_error() -> None:
    case = make_case()
    uow, storage, inspector = UnitOfWork(case), Storage(), Inspector()
    evidence = build_service(uow, storage, inspector).execute(
        principal=principal(),
        case_id=case.id,
        content=BytesIO(b"content"),
        filename="photo.png",
        declared_content_type="image/png",
    )
    service = ReadEvidenceContent(
        get_evidence=GetEvidenceMetadata(uow_factory=Factory(uow)),
        storage=storage,
        max_bytes=1024,
    )

    storage.fail_get = True
    with pytest.raises(StorageUnavailableError):
        service.execute(principal=principal(), case_id=case.id, evidence_id=evidence.id)
    storage.fail_get = False
    storage.contents[evidence.object_key] = b"corrupt"
    with pytest.raises(EvidenceUploadFailedError, match="integrity"):
        service.execute(principal=principal(), case_id=case.id, evidence_id=evidence.id)

    storage.fail_exists = True
    with pytest.raises(StorageUnavailableError):
        service.execute(principal=principal(), case_id=case.id, evidence_id=evidence.id)
