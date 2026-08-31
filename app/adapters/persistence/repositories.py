"""Tenant-scoped SQLAlchemy repositories for Case and Evidence workflows."""

import hashlib
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.adapters.persistence.models import (
    CaseEvidenceModel,
    CaseModel,
    CaseSensitivePayloadModel,
    CaseStatusHistoryModel,
    DataLifecycleEventModel,
    HumanReviewDecisionModel,
    HumanReviewTaskModel,
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
from app.platform.privacy_lifecycle import PURGED_CUSTOMER_MESSAGE
from app.ports.case_repository import CaseListCriteria, EvidenceClaim, IdempotencyClaim


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
        source_scope=case.source_scope.value,
        source_provenance=case.source_provenance,
        created_by=_required_uuid(case.created_by),
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def case_entity_from_model(
    model: CaseModel,
    *,
    sensitive_payload_id: UUID | None = None,
    sensitive_customer_message: str | None = None,
    sensitive_purged_at: datetime | None = None,
) -> Case:
    if sensitive_payload_id is None:
        raise InconsistentPersistenceStateError(
            "The Case is missing its required sensitive-payload lifecycle record."
        )
    if sensitive_purged_at is None:
        if sensitive_customer_message is None:
            raise InconsistentPersistenceStateError(
                "The active sensitive-payload lifecycle record has no content."
            )
        customer_message = sensitive_customer_message
    else:
        if sensitive_customer_message is not None:
            raise InconsistentPersistenceStateError(
                "The purged sensitive-payload lifecycle record still has content."
            )
        customer_message = PURGED_CUSTOMER_MESSAGE
    return Case.model_validate(
        {
            "id": str(model.id),
            "tenant_id": str(model.tenant_id),
            "domain_type": model.domain_type,
            "status": model.status,
            "order_ref": model.order_ref,
            "product_ref": model.product_ref,
            "customer_message": customer_message,
            "requested_action": model.requested_action,
            "attributes": cast(dict[str, JsonValue], model.attributes),
            "source_scope": model.source_scope,
            "source_provenance": model.source_provenance,
            "created_by": str(model.created_by),
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


def _sensitive_models_from_case(
    case: Case,
    *,
    retention_policy_version: str,
    retention_days: int,
) -> tuple[CaseSensitivePayloadModel, DataLifecycleEventModel]:
    if not retention_policy_version.strip():
        raise ValueError("sensitive payload retention policy version must not be blank")
    if retention_days < 1:
        raise ValueError("sensitive payload retention days must be positive")
    tenant_id = _required_uuid(case.tenant_id)
    case_id = _required_uuid(case.id)
    payload_hash = hashlib.sha256(case.customer_message.encode("utf-8")).hexdigest()
    payload = CaseSensitivePayloadModel(
        id=case_id,
        tenant_id=tenant_id,
        case_id=case_id,
        schema_version="case_sensitive_payload/1.0.0",
        customer_message=case.customer_message,
        payload_sha256=payload_hash,
        retention_policy_version=retention_policy_version,
        expires_at=case.created_at + timedelta(days=retention_days),
        purged_at=None,
        legacy_redacted_at=None,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )
    event_id = uuid4()
    event_content = (
        f"{case.tenant_id}:{case.id}:{payload.id}:{retention_policy_version}:"
        f"{case.created_at.isoformat()}"
    )
    event = DataLifecycleEventModel(
        id=event_id,
        tenant_id=tenant_id,
        case_id=case_id,
        schema_version="data_lifecycle_event/1.0.0",
        event_type="SENSITIVE_PAYLOAD_CREATED",
        resource_type="CASE_SENSITIVE_PAYLOAD",
        resource_id=payload.id,
        retention_policy_version=retention_policy_version,
        actor_id=_required_uuid(case.created_by),
        correlation_id=event_id,
        details={"source": "case.create.v1", "pii_included": False},
        occurred_at=case.created_at,
        content_hash=hashlib.sha256(event_content.encode("utf-8")).hexdigest(),
        operation_key=None,
    )
    return payload, event


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
        idempotency_key=evidence.idempotency_key,
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
            "idempotency_key": model.idempotency_key,
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
    if criteria.access_actor_id is not None:
        actor_uuid = _optional_uuid(criteria.access_actor_id)
        if actor_uuid is None:
            filters.append(CaseModel.id.is_(None))
        else:
            filters.append(
                (CaseModel.current_assignee_id == actor_uuid)
                | exists(
                    select(HumanReviewDecisionModel.id)
                    .join(
                        HumanReviewTaskModel,
                        (HumanReviewTaskModel.tenant_id == HumanReviewDecisionModel.tenant_id)
                        & (HumanReviewTaskModel.id == HumanReviewDecisionModel.review_task_id),
                    )
                    .where(
                        HumanReviewDecisionModel.tenant_id == tenant_id,
                        HumanReviewTaskModel.case_id == CaseModel.id,
                        HumanReviewDecisionModel.decided_by == actor_uuid,
                    )
                )
            )
    return filters


class SQLAlchemyCaseRepository:
    def __init__(
        self,
        session: Session,
        *,
        sensitive_payload_retention_policy_version: str = "development/30d",
        sensitive_payload_retention_days: int = 30,
    ) -> None:
        self._session = session
        self._sensitive_payload_retention_policy_version = (
            sensitive_payload_retention_policy_version
        )
        self._sensitive_payload_retention_days = sensitive_payload_retention_days

    def add(self, *, tenant_id: str, case: Case) -> None:
        _require_matching_tenant_scope(tenant_id=tenant_id, entity_tenant_id=case.tenant_id)
        payload, lifecycle_event = _sensitive_models_from_case(
            case,
            retention_policy_version=self._sensitive_payload_retention_policy_version,
            retention_days=self._sensitive_payload_retention_days,
        )
        self._session.add_all((case_model_from_entity(case), payload, lifecycle_event))

    def get(self, *, tenant_id: str, case_id: str) -> Case | None:
        tenant_uuid = _optional_uuid(tenant_id)
        case_uuid = _optional_uuid(case_id)
        if tenant_uuid is None or case_uuid is None:
            return None
        statement = (
            select(
                CaseModel,
                CaseSensitivePayloadModel.id,
                CaseSensitivePayloadModel.customer_message,
                CaseSensitivePayloadModel.purged_at,
            )
            .outerjoin(
                CaseSensitivePayloadModel,
                (CaseSensitivePayloadModel.tenant_id == CaseModel.tenant_id)
                & (CaseSensitivePayloadModel.case_id == CaseModel.id),
            )
            .where(
                CaseModel.tenant_id == tenant_uuid,
                CaseModel.id == case_uuid,
            )
        )
        row = self._session.execute(statement).one_or_none()
        if row is None:
            return None
        model, payload_id, sensitive_message, purged_at = row
        return case_entity_from_model(
            model,
            sensitive_payload_id=payload_id,
            sensitive_customer_message=sensitive_message,
            sensitive_purged_at=purged_at,
        )

    def list(self, *, tenant_id: str, criteria: CaseListCriteria) -> tuple[Case, ...]:
        tenant_uuid = _optional_uuid(tenant_id)
        if tenant_uuid is None:
            return ()
        if criteria.page < 1 or criteria.page_size < 1:
            raise ValueError("page and page_size must be positive")
        statement = (
            select(
                CaseModel,
                CaseSensitivePayloadModel.id,
                CaseSensitivePayloadModel.customer_message,
                CaseSensitivePayloadModel.purged_at,
            )
            .outerjoin(
                CaseSensitivePayloadModel,
                (CaseSensitivePayloadModel.tenant_id == CaseModel.tenant_id)
                & (CaseSensitivePayloadModel.case_id == CaseModel.id),
            )
            .where(*_case_filters(tenant_uuid, criteria))
            .order_by(CaseModel.created_at.desc(), CaseModel.id.desc())
            .offset((criteria.page - 1) * criteria.page_size)
            .limit(criteria.page_size)
        )
        items: list[Case] = []
        for model, payload_id, sensitive_message, purged_at in self._session.execute(statement):
            items.append(
                case_entity_from_model(
                    model,
                    sensitive_payload_id=payload_id,
                    sensitive_customer_message=sensitive_message,
                    sensitive_purged_at=purged_at,
                )
            )
        return tuple(items)

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

    def claim(self, *, tenant_id: str, evidence: EvidenceMetadata) -> EvidenceClaim:
        """Atomically claim an Evidence upload idempotency key.

        The caller has already inspected and hashed the bytes. A conflicting key
        is returned to the application so it can compare the immutable SHA-256
        without ever storing the request body in an idempotency record.
        """

        tenant_uuid = _require_matching_tenant_scope(
            tenant_id=tenant_id,
            entity_tenant_id=evidence.tenant_id,
        )
        if evidence.idempotency_key is None:
            raise ValueError("Evidence claim requires an idempotency key")
        values = {
            column.name: getattr(evidence_model_from_entity(evidence), column.name)
            for column in CaseEvidenceModel.__table__.columns
        }
        statement = (
            postgresql_insert(CaseEvidenceModel)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_case_evidence_tenant_case_idempotency_key")
            .returning(CaseEvidenceModel)
        )
        claimed_model = self._session.scalars(statement).one_or_none()
        if claimed_model is not None:
            return EvidenceClaim(
                claimed=True,
                evidence=evidence_entity_from_model(claimed_model),
            )
        existing = self._session.scalars(
            select(CaseEvidenceModel).where(
                CaseEvidenceModel.tenant_id == tenant_uuid,
                CaseEvidenceModel.case_id == _required_uuid(evidence.case_id),
                CaseEvidenceModel.idempotency_key == evidence.idempotency_key,
            )
        ).one_or_none()
        if existing is None:
            raise InconsistentPersistenceStateError(
                "Evidence idempotency conflicted without a matching scoped row."
            )
        return EvidenceClaim(
            claimed=False,
            evidence=evidence_entity_from_model(existing),
        )

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
