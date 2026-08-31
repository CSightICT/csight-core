"""Dry-run, authorization, idempotency, and deletion safety lifecycle tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import cast

import pytest

from app.application.privacy_lifecycle import (
    PurgeExpiredSensitivePayloads,
    ReconcileEvidenceConsistency,
)
from app.platform.errors import ForbiddenError
from app.platform.evidence import EvidenceUploadStatus, build_evidence_object_key
from app.platform.privacy_lifecycle import (
    EvidenceLifecyclePage,
    EvidenceLifecycleRecord,
    EvidencePurgeEventType,
    LifecycleFindingKind,
    LifecycleFindingOutcome,
    LifecycleMutationResult,
    LifecycleMutationStatus,
    LifecycleRunMode,
    SensitivePayloadLifecyclePage,
    SensitivePayloadLifecycleRecord,
)
from app.platform.tenant import Principal, Role
from app.ports.privacy_lifecycle import PrivacyLifecycleUnitOfWork
from app.ports.storage import (
    EvidenceObjectInventory,
    ObjectInventoryPage,
    ObjectVersionInventoryPage,
    StoredObject,
    StoredObjectVersion,
    VersionedObjectLifecycle,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 29, 3, 0, tzinfo=UTC)
TENANT_ID = "00000000-0000-4000-8000-000000000001"
ADMIN_ID = "00000000-0000-4000-8000-000000000002"
CASE_ID = "00000000-0000-4000-8000-000000000003"
EVIDENCE_ID = "00000000-0000-4000-8000-000000000004"
ORPHAN_ID = "00000000-0000-4000-8000-000000000005"
PAYLOAD_ID = "00000000-0000-4000-8000-000000000006"


class StaticClock:
    def now(self) -> datetime:
        return NOW


class Ids:
    def __init__(self) -> None:
        self.index = 10

    def new_id(self) -> str:
        self.index += 1
        return f"00000000-0000-4000-8000-{self.index:012d}"


class Repository:
    def __init__(self) -> None:
        self.sensitive = SensitivePayloadLifecyclePage(items=(), truncated=False)
        self.evidence = EvidenceLifecyclePage(items=(), truncated=False)
        self.evidence_by_key: dict[str, EvidenceLifecycleRecord] = {}
        self.case_ids = {CASE_ID}
        self.purge_calls: list[tuple[str, str | None]] = []
        self.reconcile_calls: list[tuple[str, EvidenceUploadStatus, str]] = []
        self.events: list[tuple[EvidencePurgeEventType, str, str]] = []

    def list_expired_sensitive_payloads(
        self, *, tenant_id: str, expired_before: datetime, limit: int
    ) -> SensitivePayloadLifecyclePage:
        assert tenant_id == TENANT_ID
        assert expired_before == NOW
        assert limit > 0
        return self.sensitive

    def purge_sensitive_payload(
        self,
        *,
        candidate: SensitivePayloadLifecycleRecord,
        actor_id: str | None,
        correlation_id: str,
        occurred_at: datetime,
    ) -> LifecycleMutationResult:
        assert correlation_id
        assert occurred_at == NOW
        self.purge_calls.append((candidate.id, actor_id))
        return LifecycleMutationResult(
            status=LifecycleMutationStatus.APPLIED,
            reason="payload_purged",
        )

    def list_evidence_for_reconciliation(
        self, *, tenant_id: str, stale_pending_before: datetime, limit: int
    ) -> EvidenceLifecyclePage:
        assert tenant_id == TENANT_ID
        assert stale_pending_before == NOW - timedelta(hours=1)
        assert limit > 0
        return self.evidence

    def get_evidence_by_object_key(
        self, *, tenant_id: str, object_key: str
    ) -> EvidenceLifecycleRecord | None:
        assert tenant_id == TENANT_ID
        return self.evidence_by_key.get(object_key)

    def case_exists(self, *, tenant_id: str, case_id: str) -> bool:
        assert tenant_id == TENANT_ID
        return case_id in self.case_ids

    def reconcile_evidence_status(
        self,
        *,
        record: EvidenceLifecycleRecord,
        target_status: EvidenceUploadStatus,
        reason: str,
        actor_id: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> LifecycleMutationResult:
        assert actor_id == ADMIN_ID
        assert correlation_id
        assert occurred_at == NOW
        self.reconcile_calls.append((record.id, target_status, reason))
        return LifecycleMutationResult(
            status=LifecycleMutationStatus.APPLIED,
            reason="evidence_status_reconciled",
        )

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
    ) -> bool:
        assert tenant_id == TENANT_ID
        assert case_id == CASE_ID
        assert actor_id == ADMIN_ID
        assert correlation_id
        assert occurred_at == NOW
        assert reason and operation_key
        self.events.append((event_type, evidence_id, operation_key))
        return True


class UnitOfWork:
    def __init__(self, repository: Repository, transactions: list[str]) -> None:
        self.lifecycle = repository
        self._transactions = transactions

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
        self._transactions.append("flush")

    def commit(self) -> None:
        self._transactions.append("commit")

    def rollback(self) -> None:
        self._transactions.append("rollback")


class Factory:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.transactions: list[str] = []

    def __call__(self) -> PrivacyLifecycleUnitOfWork:
        return cast(
            PrivacyLifecycleUnitOfWork,
            UnitOfWork(self.repository, self.transactions),
        )


class Storage:
    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}
        self.deleted: list[str] = []
        self.versions: dict[str, list[StoredObjectVersion]] = {}
        self.fail_delete = False
        self.truncated = False

    def stat(self, key: str) -> StoredObject | None:
        return self.objects.get(key)

    def list_keys(self, *, prefix: str, limit: int) -> ObjectInventoryPage:
        keys = tuple(sorted(key for key in self.objects if key.startswith(prefix)))
        return ObjectInventoryPage(keys=keys[:limit], truncated=self.truncated or len(keys) > limit)

    def delete(self, key: str) -> None:
        if self.fail_delete:
            raise RuntimeError("secret storage failure")
        self.deleted.append(key)
        self.objects.pop(key, None)

    def list_versions(self, *, key: str, limit: int) -> ObjectVersionInventoryPage:
        versions = self.versions.get(key)
        if versions is None and key in self.objects:
            versions = [
                StoredObjectVersion(
                    key=key,
                    version_id="v-current",
                    is_delete_marker=False,
                )
            ]
        values = tuple(versions or ())
        return ObjectVersionInventoryPage(
            versions=values[:limit],
            truncated=len(values) > limit,
        )

    def delete_version(self, *, key: str, version_id: str | None) -> None:
        if self.fail_delete:
            raise RuntimeError("secret storage failure")
        versions = self.versions.get(key)
        if versions is not None:
            self.versions[key] = [item for item in versions if item.version_id != version_id]
            if self.versions[key]:
                return
        self.deleted.append(key)
        self.objects.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.objects

    def put(self, **values: object) -> StoredObject:
        raise AssertionError(values)

    def presign_get(self, key: str, *, expires_in: timedelta) -> str:
        raise AssertionError((key, expires_in))

    def is_ready(self) -> bool:
        return True


def _principal(role: Role = Role.ADMIN) -> Principal:
    return Principal(
        user_id=ADMIN_ID,
        tenant_id=TENANT_ID,
        email="admin@example.test",
        display_name="Admin",
        roles=frozenset({role}),
    )


def _payload() -> SensitivePayloadLifecycleRecord:
    return SensitivePayloadLifecycleRecord(
        id=PAYLOAD_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        payload_sha256="a" * 64,
        retention_policy_version="tenant-policy/1.0",
        expires_at=NOW - timedelta(minutes=1),
    )


def _record(
    *, status: EvidenceUploadStatus, evidence_id: str = EVIDENCE_ID
) -> EvidenceLifecycleRecord:
    key = build_evidence_object_key(
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        evidence_id=evidence_id,
    )
    return EvidenceLifecycleRecord(
        id=evidence_id,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        upload_status=status,
        storage_bucket="evidence",
        object_key=key,
        content_type="image/png",
        size_bytes=7,
        sha256="a" * 64,
        updated_at=NOW - timedelta(hours=2),
    )


def _stored(record: EvidenceLifecycleRecord) -> StoredObject:
    return StoredObject(
        bucket=record.storage_bucket,
        key=record.object_key,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
    )


def test_sensitive_purge_is_admin_only_and_defaults_to_read_only_plan() -> None:
    repository = Repository()
    repository.sensitive = SensitivePayloadLifecyclePage(items=(_payload(),), truncated=False)
    factory = Factory(repository)
    service = PurgeExpiredSensitivePayloads(
        uow_factory=factory,
        clock=StaticClock(),
        id_generator=Ids(),
    )

    with pytest.raises(ForbiddenError):
        service.execute(principal=_principal(Role.REVIEWER))
    report = service.execute(principal=_principal())

    assert report.mode is LifecycleRunMode.DRY_RUN
    assert report.planned_count == 1
    assert report.applied_count == 0
    assert repository.purge_calls == []
    assert factory.transactions == []


def test_sensitive_purge_executes_only_after_explicit_flag() -> None:
    repository = Repository()
    repository.sensitive = SensitivePayloadLifecyclePage(items=(_payload(),), truncated=False)
    factory = Factory(repository)

    report = PurgeExpiredSensitivePayloads(
        uow_factory=factory,
        clock=StaticClock(),
        id_generator=Ids(),
    ).execute(principal=_principal(), execute=True)

    assert report.applied_count == 1
    assert repository.purge_calls == [(PAYLOAD_ID, ADMIN_ID)]
    assert factory.transactions == ["flush", "commit"]


def test_sensitive_purge_automation_uses_no_human_actor_and_always_executes() -> None:
    repository = Repository()
    repository.sensitive = SensitivePayloadLifecyclePage(items=(_payload(),), truncated=False)
    factory = Factory(repository)

    report = PurgeExpiredSensitivePayloads(
        uow_factory=factory,
        clock=StaticClock(),
        id_generator=Ids(),
    ).execute_automated(tenant_id=TENANT_ID)

    assert report.mode is LifecycleRunMode.EXECUTE
    assert report.applied_count == 1
    assert repository.purge_calls == [(PAYLOAD_ID, None)]
    assert factory.transactions == ["flush", "commit"]


def test_reconciliation_plans_status_repair_without_mutating_by_default() -> None:
    repository = Repository()
    record = _record(status=EvidenceUploadStatus.PENDING)
    repository.evidence = EvidenceLifecyclePage(items=(record,), truncated=False)
    repository.evidence_by_key[record.object_key] = record
    storage = Storage()
    storage.objects[record.object_key] = _stored(record)

    report = ReconcileEvidenceConsistency(
        uow_factory=Factory(repository),
        inventory=cast(EvidenceObjectInventory, storage),
        versioned_storage=cast(VersionedObjectLifecycle, storage),
        clock=StaticClock(),
        id_generator=Ids(),
    ).execute(principal=_principal())

    assert report.planned_count == 1
    assert report.findings[0].kind is LifecycleFindingKind.STALE_PENDING_OBJECT_VALID
    assert repository.reconcile_calls == []
    assert storage.deleted == []


def test_reconciliation_applies_status_change_and_records_repository_event() -> None:
    repository = Repository()
    record = _record(status=EvidenceUploadStatus.AVAILABLE)
    repository.evidence = EvidenceLifecyclePage(items=(record,), truncated=False)

    report = ReconcileEvidenceConsistency(
        uow_factory=Factory(repository),
        inventory=cast(EvidenceObjectInventory, Storage()),
        versioned_storage=cast(VersionedObjectLifecycle, Storage()),
        clock=StaticClock(),
        id_generator=Ids(),
    ).execute(principal=_principal(), execute=True)

    assert report.applied_count == 1
    assert repository.reconcile_calls == [
        (EVIDENCE_ID, EvidenceUploadStatus.FAILED, "available_object_missing")
    ]


def test_orphan_delete_requires_second_explicit_flag_and_emits_two_events() -> None:
    repository = Repository()
    storage = Storage()
    key = build_evidence_object_key(
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        evidence_id=ORPHAN_ID,
    )
    storage.objects[key] = StoredObject(
        bucket="evidence",
        key=key,
        content_type="image/png",
        size_bytes=1,
        sha256="b" * 64,
    )
    service = ReconcileEvidenceConsistency(
        uow_factory=Factory(repository),
        inventory=cast(EvidenceObjectInventory, storage),
        versioned_storage=cast(VersionedObjectLifecycle, storage),
        clock=StaticClock(),
        id_generator=Ids(),
    )

    blocked = service.execute(principal=_principal(), execute=True)
    applied = service.execute(
        principal=_principal(),
        execute=True,
        delete_orphan_objects=True,
    )

    assert blocked.findings[0].outcome is LifecycleFindingOutcome.BLOCKED
    assert blocked.findings[0].reason == "explicit_object_delete_required"
    assert applied.applied_count == 1
    assert storage.deleted == [key]
    assert [event[0] for event in repository.events] == [
        EvidencePurgeEventType.REQUESTED,
        EvidencePurgeEventType.COMPLETED,
    ]


def test_orphan_delete_permanently_removes_every_version_and_delete_marker() -> None:
    repository = Repository()
    storage = Storage()
    key = build_evidence_object_key(
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        evidence_id=ORPHAN_ID,
    )
    storage.objects[key] = StoredObject(
        bucket="evidence",
        key=key,
        content_type="image/png",
        size_bytes=1,
        sha256="b" * 64,
    )
    storage.versions[key] = [
        StoredObjectVersion(key=key, version_id="v2", is_delete_marker=False),
        StoredObjectVersion(key=key, version_id="marker", is_delete_marker=True),
        StoredObjectVersion(key=key, version_id="v1", is_delete_marker=False),
    ]

    report = ReconcileEvidenceConsistency(
        uow_factory=Factory(repository),
        inventory=cast(EvidenceObjectInventory, storage),
        versioned_storage=cast(VersionedObjectLifecycle, storage),
        clock=StaticClock(),
        id_generator=Ids(),
    ).execute(
        principal=_principal(),
        execute=True,
        delete_orphan_objects=True,
    )

    assert report.applied_count == 1
    assert report.findings[0].reason == "object_versions_deleted"
    assert storage.list_versions(key=key, limit=10).versions == ()
    assert key not in storage.objects


def test_delete_failure_keeps_requested_event_and_exposes_only_safe_reason() -> None:
    repository = Repository()
    record = _record(status=EvidenceUploadStatus.FAILED)
    repository.evidence = EvidenceLifecyclePage(items=(record,), truncated=False)
    repository.evidence_by_key[record.object_key] = record
    storage = Storage()
    storage.objects[record.object_key] = _stored(record)
    storage.fail_delete = True

    report = ReconcileEvidenceConsistency(
        uow_factory=Factory(repository),
        inventory=cast(EvidenceObjectInventory, storage),
        versioned_storage=cast(VersionedObjectLifecycle, storage),
        clock=StaticClock(),
        id_generator=Ids(),
    ).execute(
        principal=_principal(),
        execute=True,
        delete_orphan_objects=True,
    )

    assert report.blocked_count == 1
    assert report.findings[0].reason == "storage_delete_failed"
    assert [event[0] for event in repository.events] == [EvidencePurgeEventType.REQUESTED]
