"""Tenant-scoped SQLAlchemy repositories for Case and Evidence workflows."""

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.adapters.persistence.models import (
    CaseEvidenceModel,
    CaseModel,
    CaseStatusHistoryModel,
    IdempotencyRecordModel,
)
from app.platform.case import (
    Case,
    CaseStatusTransition,
    IdempotencyRecord,
    JsonValue,
)
from app.platform.errors import InconsistentPersistenceStateError
from app.platform.evidence import EvidenceMetadata, EvidenceUploadStatus
from app.ports.case_repository import CaseListCriteria, IdempotencyClaim


def _required_uuid(value: str) -> UUID:
    return UUID(value)


def _optional_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _require_matching_tenant_scope(*, tenant_id: str, entity_tenant_id: str) -> UUID:
    """Fail before persistence when an entity escapes the explicit tenant scope."""

    tenant_uuid = _required_uuid(tenant_id)
    if tenant_uuid != _required_uuid(entity_tenant_id):
        raise ValueError("entity tenant_id does not match the repository tenant scope")
    return tenant_uuid


def case_model_from_entity(case: Case) -> CaseModel:
    return CaseModel(
        id=_required_uuid(case.id),
        tenant_id=_required_uuid(case.tenant_id),
        domain_type=case.domain_type.value,
        status=case.status.value,
        order_ref=case.order_ref,
        product_ref=case.product_ref,
        customer_message=case.customer_message,
        requested_action=case.requested_action.value,
        attributes=cast(dict[str, object], case.attributes),
        created_by=_required_uuid(case.created_by),
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def case_entity_from_model(model: CaseModel) -> Case:
    return Case.model_validate(
        {
            "id": str(model.id),
            "tenant_id": str(model.tenant_id),
            "domain_type": model.domain_type,
            "status": model.status,
            "order_ref": model.order_ref,
            "product_ref": model.product_ref,
            "customer_message": model.customer_message,
            "requested_action": model.requested_action,
            "attributes": cast(dict[str, JsonValue], model.attributes),
            "created_by": str(model.created_by),
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


def history_model_from_entity(transition: CaseStatusTransition) -> CaseStatusHistoryModel:
    return CaseStatusHistoryModel(
        id=_required_uuid(transition.id),
        tenant_id=_required_uuid(transition.tenant_id),
        case_id=_required_uuid(transition.case_id),
        from_status=(transition.from_status.value if transition.from_status is not None else None),
        to_status=transition.to_status.value,
        actor_id=_required_uuid(transition.actor_id),
        reason=transition.reason,
        occurred_at=transition.occurred_at,
    )


def history_entity_from_model(model: CaseStatusHistoryModel) -> CaseStatusTransition:
    return CaseStatusTransition.model_validate(
        {
            "id": str(model.id),
            "tenant_id": str(model.tenant_id),
            "case_id": str(model.case_id),
            "from_status": model.from_status,
            "to_status": model.to_status,
            "actor_id": str(model.actor_id),
            "reason": model.reason,
            "occurred_at": model.occurred_at,
        }
    )


def evidence_model_from_entity(evidence: EvidenceMetadata) -> CaseEvidenceModel:
    return CaseEvidenceModel(
        id=_required_uuid(evidence.id),
        tenant_id=_required_uuid(evidence.tenant_id),
        case_id=_required_uuid(evidence.case_id),
        evidence_type=evidence.evidence_type.value,
        upload_status=evidence.upload_status.value,
        storage_bucket=evidence.storage_bucket,
        object_key=evidence.object_key,
        original_filename=evidence.original_filename,
        content_type=evidence.content_type,
        size_bytes=evidence.size_bytes,
        sha256=evidence.sha256,
        width=evidence.width,
        height=evidence.height,
        created_by=_required_uuid(evidence.created_by),
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
    )


def evidence_entity_from_model(model: CaseEvidenceModel) -> EvidenceMetadata:
    return EvidenceMetadata.model_validate(
        {
            "id": str(model.id),
            "tenant_id": str(model.tenant_id),
            "case_id": str(model.case_id),
            "evidence_type": model.evidence_type,
            "upload_status": model.upload_status,
            "storage_bucket": model.storage_bucket,
            "object_key": model.object_key,
            "original_filename": model.original_filename,
            "content_type": model.content_type,
            "size_bytes": model.size_bytes,
            "sha256": model.sha256,
            "width": model.width,
            "height": model.height,
            "created_by": str(model.created_by),
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


def idempotency_model_values(record: IdempotencyRecord) -> dict[str, object]:
    return {
        "id": _required_uuid(record.id),
        "tenant_id": _required_uuid(record.tenant_id),
        "operation": record.operation,
        "idempotency_key": record.idempotency_key,
        "request_hash": record.request_hash,
        "resource_type": record.resource_type,
        "resource_id": _required_uuid(record.resource_id),
        "response_status": record.response_status,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
    }


def idempotency_entity_from_model(model: IdempotencyRecordModel) -> IdempotencyRecord:
    return IdempotencyRecord.model_validate(
        {
            "id": str(model.id),
            "tenant_id": str(model.tenant_id),
            "operation": model.operation,
            "idempotency_key": model.idempotency_key,
            "request_hash": model.request_hash,
            "resource_type": model.resource_type,
            "resource_id": str(model.resource_id),
            "response_status": model.response_status,
            "created_at": model.created_at,
            "expires_at": model.expires_at,
        }
    )


def _case_filters(
    tenant_id: UUID,
    criteria: CaseListCriteria,
) -> list[ColumnElement[bool]]:
    filters = [CaseModel.tenant_id == tenant_id]
    if criteria.status is not None:
        filters.append(CaseModel.status == criteria.status.value)
    if criteria.order_ref is not None:
        filters.append(CaseModel.order_ref == criteria.order_ref)
    if criteria.product_ref is not None:
        filters.append(CaseModel.product_ref == criteria.product_ref)
    if criteria.created_from is not None:
        filters.append(CaseModel.created_at >= criteria.created_from)
    if criteria.created_to is not None:
        filters.append(CaseModel.created_at <= criteria.created_to)
    return filters


class SQLAlchemyCaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, case: Case) -> None:
        _require_matching_tenant_scope(tenant_id=tenant_id, entity_tenant_id=case.tenant_id)
        self._session.add(case_model_from_entity(case))

    def get(self, *, tenant_id: str, case_id: str) -> Case | None:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        if tenant_uuid is None or case_uuid is None:
            return None
        statement = select(CaseModel).where(
            CaseModel.tenant_id == tenant_uuid,
            CaseModel.id == case_uuid,
        )
        model = self._session.scalars(statement).one_or_none()
        return case_entity_from_model(model) if model is not None else None

    def list(self, *, tenant_id: str, criteria: CaseListCriteria) -> tuple[Case, ...]:
        tenant_uuid = _optional_uuid(tenant_id)
        if tenant_uuid is None:
            return ()
        if criteria.page < 1 or criteria.page_size < 1:
            raise ValueError("page and page_size must be positive")
        statement = (
            select(CaseModel)
            .where(*_case_filters(tenant_uuid, criteria))
            .order_by(CaseModel.created_at.desc(), CaseModel.id.desc())
            .offset((criteria.page - 1) * criteria.page_size)
            .limit(criteria.page_size)
        )
        return tuple(case_entity_from_model(model) for model in self._session.scalars(statement))

    def count(self, *, tenant_id: str, criteria: CaseListCriteria) -> int:
        tenant_uuid = _optional_uuid(tenant_id)
        if tenant_uuid is None:
            return 0
        statement = (
            select(func.count()).select_from(CaseModel).where(*_case_filters(tenant_uuid, criteria))
        )
        return int(self._session.scalar(statement) or 0)


class SQLAlchemyCaseStatusHistoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, transition: CaseStatusTransition) -> None:
        _require_matching_tenant_scope(
            tenant_id=tenant_id,
            entity_tenant_id=transition.tenant_id,
        )
        self._session.add(history_model_from_entity(transition))

    def list(self, *, tenant_id: str, case_id: str) -> tuple[CaseStatusTransition, ...]:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        if tenant_uuid is None or case_uuid is None:
            return ()
        statement = (
            select(CaseStatusHistoryModel)
            .where(
                CaseStatusHistoryModel.tenant_id == tenant_uuid,
                CaseStatusHistoryModel.case_id == case_uuid,
            )
            .order_by(
                CaseStatusHistoryModel.occurred_at.asc(),
                CaseStatusHistoryModel.id.asc(),
            )
        )
        return tuple(history_entity_from_model(model) for model in self._session.scalars(statement))


class SQLAlchemyEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant_id: str, evidence: EvidenceMetadata) -> None:
        _require_matching_tenant_scope(
            tenant_id=tenant_id,
            entity_tenant_id=evidence.tenant_id,
        )
        self._session.add(evidence_model_from_entity(evidence))

    def get(
        self,
        *,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceMetadata | None:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        evidence_uuid = _optional_uuid(evidence_id)
        if tenant_uuid is None or case_uuid is None or evidence_uuid is None:
            return None
        statement = select(CaseEvidenceModel).where(
            CaseEvidenceModel.tenant_id == tenant_uuid,
            CaseEvidenceModel.case_id == case_uuid,
            CaseEvidenceModel.id == evidence_uuid,
        )
        model = self._session.scalars(statement).one_or_none()
        return evidence_entity_from_model(model) if model is not None else None

    def list(self, *, tenant_id: str, case_id: str) -> tuple[EvidenceMetadata, ...]:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        if tenant_uuid is None or case_uuid is None:
            return ()
        statement = (
            select(CaseEvidenceModel)
            .where(
                CaseEvidenceModel.tenant_id == tenant_uuid,
                CaseEvidenceModel.case_id == case_uuid,
            )
            .order_by(CaseEvidenceModel.created_at.asc(), CaseEvidenceModel.id.asc())
        )
        return tuple(
            evidence_entity_from_model(model) for model in self._session.scalars(statement)
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
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        evidence_uuid = _optional_uuid(evidence_id)
        if tenant_uuid is None or case_uuid is None or evidence_uuid is None:
            return None
        statement = (
            update(CaseEvidenceModel)
            .where(
                CaseEvidenceModel.tenant_id == tenant_uuid,
                CaseEvidenceModel.case_id == case_uuid,
                CaseEvidenceModel.id == evidence_uuid,
            )
            .values(upload_status=status.value, updated_at=updated_at)
            .returning(CaseEvidenceModel)
        )
        model = self._session.scalars(statement).one_or_none()
        return evidence_entity_from_model(model) if model is not None else None


class SQLAlchemyIdempotencyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def claim(self, *, tenant_id: str, record: IdempotencyRecord) -> IdempotencyClaim:
        tenant_uuid = _require_matching_tenant_scope(
            tenant_id=tenant_id,
            entity_tenant_id=record.tenant_id,
        )
        statement = (
            postgresql_insert(IdempotencyRecordModel)
            .values(**idempotency_model_values(record))
            .on_conflict_do_nothing(constraint="uq_idempotency_records_tenant_operation_key")
            .returning(IdempotencyRecordModel)
        )
        claimed_model = self._session.scalars(statement).one_or_none()
        if claimed_model is not None:
            return IdempotencyClaim(
                claimed=True,
                record=idempotency_entity_from_model(claimed_model),
            )

        existing_statement = select(IdempotencyRecordModel).where(
            IdempotencyRecordModel.tenant_id == tenant_uuid,
            IdempotencyRecordModel.operation == record.operation,
            IdempotencyRecordModel.idempotency_key == record.idempotency_key,
        )
        existing_model = self._session.scalars(existing_statement).one_or_none()
        if existing_model is None:
            raise InconsistentPersistenceStateError(
                "The idempotency claim conflicted without a matching scoped record."
            )
        return IdempotencyClaim(
            claimed=False,
            record=idempotency_entity_from_model(existing_model),
        )


__all__ = [
    "SQLAlchemyCaseRepository",
    "SQLAlchemyCaseStatusHistoryRepository",
    "SQLAlchemyEvidenceRepository",
    "SQLAlchemyIdempotencyRepository",
    "case_entity_from_model",
    "case_model_from_entity",
    "evidence_entity_from_model",
    "evidence_model_from_entity",
    "history_entity_from_model",
    "history_model_from_entity",
    "idempotency_entity_from_model",
    "idempotency_model_values",
]
