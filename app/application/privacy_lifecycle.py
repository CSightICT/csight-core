"""Admin-only, dry-run-first privacy and Evidence lifecycle jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.platform.errors import ForbiddenError, StorageUnavailableError, ValidationError
from app.platform.evidence import EvidenceUploadStatus, build_evidence_object_key
from app.platform.privacy_lifecycle import (
    EvidenceLifecycleRecord,
    EvidencePurgeEventType,
    LifecycleFinding,
    LifecycleFindingKind,
    LifecycleFindingOutcome,
    LifecycleMutationStatus,
    LifecycleRunMode,
    LifecycleRunReport,
)
from app.platform.tenant import Principal, Role
from app.ports.privacy_lifecycle import PrivacyLifecycleUnitOfWorkFactory
from app.ports.runtime import Clock, IdGenerator
from app.ports.storage import (
    EvidenceObjectInventory,
    StoredObject,
    VersionedObjectLifecycle,
)

_SAFE_REASON = re.compile(r"^[a-z0-9_]{1,128}$")


class PurgeExpiredSensitivePayloads:
    """Purge expired prose and its legacy copy in one fenced DB transaction."""

    def __init__(
        self,
        *,
        uow_factory: PrivacyLifecycleUnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_generator = id_generator

    def execute(
        self,
        *,
        principal: Principal,
        execute: bool = False,
        limit: int = 100,
    ) -> LifecycleRunReport:
        _require_admin(principal)
        return self._execute(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            execute=execute,
            limit=limit,
        )

    def execute_automated(
        self,
        *,
        tenant_id: str,
        limit: int = 100,
    ) -> LifecycleRunReport:
        """Apply one bounded retention batch for an explicitly configured tenant.

        This internal maintenance capability cannot reconcile or delete Evidence objects and
        records a null human actor plus a fixed scheduler initiator in the lifecycle event.
        """

        if not tenant_id.strip():
            raise ValidationError("Lifecycle tenant ID must not be blank.")
        return self._execute(
            tenant_id=tenant_id,
            actor_id=None,
            execute=True,
            limit=limit,
        )

    def _execute(
        self,
        *,
        tenant_id: str,
        actor_id: str | None,
        execute: bool,
        limit: int,
    ) -> LifecycleRunReport:
        _validate_limit(limit)
        now = self._clock.now().astimezone(UTC)
        with self._uow_factory() as uow:
            page = uow.lifecycle.list_expired_sensitive_payloads(
                tenant_id=tenant_id,
                expired_before=now,
                limit=limit,
            )

        findings: list[LifecycleFinding] = []
        for candidate in page.items:
            if not execute:
                findings.append(
                    _finding(
                        kind=LifecycleFindingKind.SENSITIVE_PAYLOAD_EXPIRED,
                        outcome=LifecycleFindingOutcome.PLANNED,
                        candidate_case_id=candidate.case_id,
                        resource_id=candidate.id,
                        reason="retention_expired",
                    )
                )
                continue
            with self._uow_factory() as uow:
                result = uow.lifecycle.purge_sensitive_payload(
                    candidate=candidate,
                    actor_id=actor_id,
                    correlation_id=self._id_generator.new_id(),
                    occurred_at=now,
                )
                if result.status is LifecycleMutationStatus.APPLIED:
                    uow.flush()
                    uow.commit()
                else:
                    uow.rollback()
            findings.append(
                _finding(
                    kind=LifecycleFindingKind.SENSITIVE_PAYLOAD_EXPIRED,
                    outcome=_mutation_outcome(result.status),
                    candidate_case_id=candidate.case_id,
                    resource_id=candidate.id,
                    reason=result.reason,
                )
            )
        return _report(
            mode=LifecycleRunMode.EXECUTE if execute else LifecycleRunMode.DRY_RUN,
            tenant_id=tenant_id,
            now=now,
            scanned_count=len(page.items),
            findings=findings,
            truncated=page.truncated,
        )


class ReconcileEvidenceConsistency:
    """Detect and explicitly repair DB/object-storage consistency drift."""

    def __init__(
        self,
        *,
        uow_factory: PrivacyLifecycleUnitOfWorkFactory,
        inventory: EvidenceObjectInventory,
        versioned_storage: VersionedObjectLifecycle,
        clock: Clock,
        id_generator: IdGenerator,
        stale_after: timedelta = timedelta(hours=1),
    ) -> None:
        if stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive")
        self._uow_factory = uow_factory
        self._inventory = inventory
        self._versioned_storage = versioned_storage
        self._clock = clock
        self._id_generator = id_generator
        self._stale_after = stale_after

    def execute(
        self,
        *,
        principal: Principal,
        execute: bool = False,
        delete_orphan_objects: bool = False,
        limit: int = 500,
    ) -> LifecycleRunReport:
        _require_admin(principal)
        _validate_limit(limit)
        now = self._clock.now().astimezone(UTC)
        with self._uow_factory() as uow:
            evidence_page = uow.lifecycle.list_evidence_for_reconciliation(
                tenant_id=principal.tenant_id,
                stale_pending_before=now - self._stale_after,
                limit=limit,
            )
        try:
            object_page = self._inventory.list_keys(
                prefix=f"tenants/{principal.tenant_id}/",
                limit=limit,
            )
        except Exception as exc:
            raise StorageUnavailableError() from exc

        findings: list[LifecycleFinding] = []
        scanned_keys = {record.object_key for record in evidence_page.items}
        for record in evidence_page.items:
            finding = self._reconcile_record(
                principal=principal,
                record=record,
                execute=execute,
                delete_orphan_objects=delete_orphan_objects,
                now=now,
            )
            if finding is not None:
                findings.append(finding)

        for object_key in object_page.keys:
            if object_key in scanned_keys:
                continue
            with self._uow_factory() as uow:
                persisted = uow.lifecycle.get_evidence_by_object_key(
                    tenant_id=principal.tenant_id,
                    object_key=object_key,
                )
            if persisted is not None:
                continue
            parsed = _parse_canonical_evidence_key(
                tenant_id=principal.tenant_id,
                object_key=object_key,
            )
            if parsed is None:
                findings.append(
                    _finding(
                        kind=LifecycleFindingKind.UNATTRIBUTABLE_OBJECT,
                        outcome=LifecycleFindingOutcome.BLOCKED,
                        candidate_case_id=None,
                        resource_id=None,
                        reason="object_key_not_canonical",
                    )
                )
                continue
            case_id, evidence_id = parsed
            with self._uow_factory() as uow:
                case_exists = uow.lifecycle.case_exists(
                    tenant_id=principal.tenant_id,
                    case_id=case_id,
                )
            if not case_exists:
                findings.append(
                    _finding(
                        kind=LifecycleFindingKind.UNATTRIBUTABLE_OBJECT,
                        outcome=LifecycleFindingOutcome.BLOCKED,
                        candidate_case_id=case_id,
                        resource_id=evidence_id,
                        reason="orphan_parent_case_missing",
                    )
                )
                continue
            findings.append(
                self._delete_object(
                    principal=principal,
                    case_id=case_id,
                    evidence_id=evidence_id,
                    object_key=object_key,
                    kind=LifecycleFindingKind.ORPHAN_EVIDENCE_OBJECT,
                    reason="orphan_object",
                    execute=execute,
                    delete_orphan_objects=delete_orphan_objects,
                    now=now,
                )
            )

        return _report(
            mode=LifecycleRunMode.EXECUTE if execute else LifecycleRunMode.DRY_RUN,
            tenant_id=principal.tenant_id,
            now=now,
            scanned_count=len(evidence_page.items) + len(object_page.keys),
            findings=findings,
            truncated=evidence_page.truncated or object_page.truncated,
        )

    def _reconcile_record(
        self,
        *,
        principal: Principal,
        record: EvidenceLifecycleRecord,
        execute: bool,
        delete_orphan_objects: bool,
        now: datetime,
    ) -> LifecycleFinding | None:
        try:
            actual = self._inventory.stat(record.object_key)
        except Exception as exc:
            raise StorageUnavailableError() from exc
        matches = actual is not None and _object_matches(record, actual)
        if record.upload_status is EvidenceUploadStatus.PENDING:
            if matches:
                return self._status_finding(
                    principal=principal,
                    record=record,
                    target=EvidenceUploadStatus.AVAILABLE,
                    kind=LifecycleFindingKind.STALE_PENDING_OBJECT_VALID,
                    reason="stale_pending_object_valid",
                    execute=execute,
                    now=now,
                )
            kind = (
                LifecycleFindingKind.STALE_PENDING_OBJECT_MISSING
                if actual is None
                else LifecycleFindingKind.EVIDENCE_OBJECT_INTEGRITY_MISMATCH
            )
            reason = (
                "stale_pending_object_missing" if actual is None else "object_metadata_mismatch"
            )
            return self._status_finding(
                principal=principal,
                record=record,
                target=EvidenceUploadStatus.FAILED,
                kind=kind,
                reason=reason,
                execute=execute,
                now=now,
            )
        if record.upload_status is EvidenceUploadStatus.AVAILABLE and not matches:
            kind = (
                LifecycleFindingKind.EVIDENCE_OBJECT_MISSING
                if actual is None
                else LifecycleFindingKind.EVIDENCE_OBJECT_INTEGRITY_MISMATCH
            )
            reason = "available_object_missing" if actual is None else "object_metadata_mismatch"
            return self._status_finding(
                principal=principal,
                record=record,
                target=EvidenceUploadStatus.FAILED,
                kind=kind,
                reason=reason,
                execute=execute,
                now=now,
            )
        if record.upload_status is EvidenceUploadStatus.FAILED and actual is not None:
            return self._delete_object(
                principal=principal,
                case_id=record.case_id,
                evidence_id=record.id,
                object_key=record.object_key,
                kind=LifecycleFindingKind.FAILED_EVIDENCE_OBJECT_PRESENT,
                reason="failed_evidence_object",
                execute=execute,
                delete_orphan_objects=delete_orphan_objects,
                now=now,
            )
        return None

    def _status_finding(
        self,
        *,
        principal: Principal,
        record: EvidenceLifecycleRecord,
        target: EvidenceUploadStatus,
        kind: LifecycleFindingKind,
        reason: str,
        execute: bool,
        now: datetime,
    ) -> LifecycleFinding:
        if not execute:
            return _finding(
                kind=kind,
                outcome=LifecycleFindingOutcome.PLANNED,
                candidate_case_id=record.case_id,
                resource_id=record.id,
                reason=reason,
            )
        with self._uow_factory() as uow:
            result = uow.lifecycle.reconcile_evidence_status(
                record=record,
                target_status=target,
                reason=reason,
                actor_id=principal.user_id,
                correlation_id=self._id_generator.new_id(),
                occurred_at=now,
            )
            if result.status is LifecycleMutationStatus.APPLIED:
                uow.flush()
                uow.commit()
            else:
                uow.rollback()
        return _finding(
            kind=kind,
            outcome=_mutation_outcome(result.status),
            candidate_case_id=record.case_id,
            resource_id=record.id,
            reason=result.reason,
        )

    def _delete_object(
        self,
        *,
        principal: Principal,
        case_id: str,
        evidence_id: str,
        object_key: str,
        kind: LifecycleFindingKind,
        reason: str,
        execute: bool,
        delete_orphan_objects: bool,
        now: datetime,
    ) -> LifecycleFinding:
        if not execute:
            return _finding(
                kind=kind,
                outcome=LifecycleFindingOutcome.PLANNED,
                candidate_case_id=case_id,
                resource_id=evidence_id,
                reason=reason,
            )
        if not delete_orphan_objects:
            return _finding(
                kind=kind,
                outcome=LifecycleFindingOutcome.BLOCKED,
                candidate_case_id=case_id,
                resource_id=evidence_id,
                reason="explicit_object_delete_required",
            )
        operation_base = f"evidence-delete:{evidence_id}:{reason}"
        try:
            version_page = self._versioned_storage.list_versions(
                key=object_key,
                limit=10_000,
            )
        except Exception:
            return _finding(
                kind=kind,
                outcome=LifecycleFindingOutcome.BLOCKED,
                candidate_case_id=case_id,
                resource_id=evidence_id,
                reason="storage_version_inventory_failed",
            )
        if version_page.truncated:
            return _finding(
                kind=kind,
                outcome=LifecycleFindingOutcome.BLOCKED,
                candidate_case_id=case_id,
                resource_id=evidence_id,
                reason="storage_version_inventory_truncated",
            )
        with self._uow_factory() as uow:
            uow.lifecycle.record_evidence_purge_event(
                event_type=EvidencePurgeEventType.REQUESTED,
                tenant_id=principal.tenant_id,
                case_id=case_id,
                evidence_id=evidence_id,
                reason=reason,
                operation_key=f"{operation_base}:requested",
                actor_id=principal.user_id,
                correlation_id=self._id_generator.new_id(),
                occurred_at=now,
            )
            uow.flush()
            uow.commit()
        try:
            for version in version_page.versions:
                self._versioned_storage.delete_version(
                    key=version.key,
                    version_id=version.version_id,
                )
            remaining = self._versioned_storage.list_versions(
                key=object_key,
                limit=10_000,
            )
        except Exception:
            return _finding(
                kind=kind,
                outcome=LifecycleFindingOutcome.BLOCKED,
                candidate_case_id=case_id,
                resource_id=evidence_id,
                reason="storage_delete_failed",
            )
        if remaining.truncated or remaining.versions:
            return _finding(
                kind=kind,
                outcome=LifecycleFindingOutcome.BLOCKED,
                candidate_case_id=case_id,
                resource_id=evidence_id,
                reason="storage_versions_remain",
            )
        with self._uow_factory() as uow:
            uow.lifecycle.record_evidence_purge_event(
                event_type=EvidencePurgeEventType.COMPLETED,
                tenant_id=principal.tenant_id,
                case_id=case_id,
                evidence_id=evidence_id,
                reason=reason,
                operation_key=f"{operation_base}:completed",
                actor_id=principal.user_id,
                correlation_id=self._id_generator.new_id(),
                occurred_at=now,
            )
            uow.flush()
            uow.commit()
        return _finding(
            kind=kind,
            outcome=LifecycleFindingOutcome.APPLIED,
            candidate_case_id=case_id,
            resource_id=evidence_id,
            reason="object_versions_deleted",
        )


def _object_matches(record: EvidenceLifecycleRecord, actual: StoredObject) -> bool:
    return (
        actual.bucket,
        actual.key,
        actual.content_type.strip().casefold(),
        actual.size_bytes,
        actual.sha256,
    ) == (
        record.storage_bucket,
        record.object_key,
        record.content_type.strip().casefold(),
        record.size_bytes,
        record.sha256,
    )


def _parse_canonical_evidence_key(*, tenant_id: str, object_key: str) -> tuple[str, str] | None:
    parts = object_key.split("/")
    if len(parts) != 7 or parts[0] != "tenants" or parts[2] != "cases":
        return None
    if parts[4] != "evidence" or parts[6] != "original" or parts[1] != tenant_id:
        return None
    case_id, evidence_id = parts[3], parts[5]
    try:
        UUID(tenant_id)
        UUID(case_id)
        UUID(evidence_id)
    except ValueError:
        return None
    if (
        build_evidence_object_key(
            tenant_id=tenant_id,
            case_id=case_id,
            evidence_id=evidence_id,
        )
        != object_key
    ):
        return None
    return case_id, evidence_id


def _require_admin(principal: Principal) -> None:
    if Role.ADMIN not in principal.roles:
        raise ForbiddenError()


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 5000:
        raise ValidationError("Lifecycle batch limit must be between 1 and 5000.")


def _finding(
    *,
    kind: LifecycleFindingKind,
    outcome: LifecycleFindingOutcome,
    candidate_case_id: str | None,
    resource_id: str | None,
    reason: str,
) -> LifecycleFinding:
    if _SAFE_REASON.fullmatch(reason) is None:
        raise ValueError("lifecycle reason must be a safe low-cardinality value")
    return LifecycleFinding(
        kind=kind,
        outcome=outcome,
        case_id=candidate_case_id,
        resource_id=resource_id,
        reason=reason,
    )


def _mutation_outcome(status: LifecycleMutationStatus) -> LifecycleFindingOutcome:
    return {
        LifecycleMutationStatus.APPLIED: LifecycleFindingOutcome.APPLIED,
        LifecycleMutationStatus.ALREADY_APPLIED: LifecycleFindingOutcome.ALREADY_APPLIED,
        LifecycleMutationStatus.BLOCKED: LifecycleFindingOutcome.BLOCKED,
    }[status]


def _report(
    *,
    mode: LifecycleRunMode,
    tenant_id: str,
    now: datetime,
    scanned_count: int,
    findings: list[LifecycleFinding],
    truncated: bool,
) -> LifecycleRunReport:
    return LifecycleRunReport(
        mode=mode,
        tenant_id=tenant_id,
        generated_at=now,
        scanned_count=scanned_count,
        planned_count=sum(item.outcome is LifecycleFindingOutcome.PLANNED for item in findings),
        applied_count=sum(item.outcome is LifecycleFindingOutcome.APPLIED for item in findings),
        already_applied_count=sum(
            item.outcome is LifecycleFindingOutcome.ALREADY_APPLIED for item in findings
        ),
        blocked_count=sum(item.outcome is LifecycleFindingOutcome.BLOCKED for item in findings),
        truncated=truncated,
        findings=tuple(findings),
    )


@dataclass(frozen=True, slots=True)
class PrivacyLifecycleServices:
    purge_sensitive_payloads: PurgeExpiredSensitivePayloads
    reconcile_evidence: ReconcileEvidenceConsistency


__all__ = [
    "PrivacyLifecycleServices",
    "PurgeExpiredSensitivePayloads",
    "ReconcileEvidenceConsistency",
]
