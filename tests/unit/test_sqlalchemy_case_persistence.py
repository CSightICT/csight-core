"""Pure tests for ORM/domain mapping and the explicit SQLAlchemy UoW lifecycle."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.adapters.persistence.models import IdempotencyRecordModel
from app.adapters.persistence.repositories import (
    SQLAlchemyCaseRepository,
    SQLAlchemyCaseStatusHistoryRepository,
    SQLAlchemyEvidenceRepository,
    SQLAlchemyIdempotencyRepository,
    case_entity_from_model,
    case_model_from_entity,
    evidence_entity_from_model,
    evidence_model_from_entity,
    history_entity_from_model,
    history_model_from_entity,
    idempotency_entity_from_model,
    idempotency_model_values,
)
from app.adapters.persistence.unit_of_work import SQLAlchemyCaseUnitOfWork
from app.platform.case import (
    Case,
    CaseStatus,
    CaseStatusTransition,
    IdempotencyRecord,
    RequestedAction,
)
from app.platform.errors import InconsistentPersistenceStateError
from app.platform.evidence import EvidenceMetadata, EvidenceType, EvidenceUploadStatus
from app.platform.privacy_lifecycle import PURGED_CUSTOMER_MESSAGE
from app.ports.case_repository import CaseListCriteria
from app.ports.unit_of_work import CaseUnitOfWork

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 26, 2, 3, 4, tzinfo=UTC)
TENANT_ID = "00000000-0000-4000-8000-000000000001"
USER_ID = "00000000-0000-4000-8000-000000000002"
CASE_ID = "00000000-0000-4000-8000-000000000003"
HISTORY_ID = "00000000-0000-4000-8000-000000000004"
EVIDENCE_ID = "00000000-0000-4000-8000-000000000005"
IDEMPOTENCY_ID = "00000000-0000-4000-8000-000000000006"
OTHER_TENANT_ID = "00000000-0000-4000-8000-000000000007"


def _case() -> Case:
    return Case(
        id=CASE_ID,
        tenant_id=TENANT_ID,
        status=CaseStatus.RECEIVED,
        order_ref="ORD-1",
        product_ref="SKU-1",
        customer_message="The package arrived damaged.",
        requested_action=RequestedAction.EXCHANGE,
        attributes={"nested": {"days": 3}, "fragile": True},
        created_by=USER_ID,
        created_at=NOW,
        updated_at=NOW,
    )


def _history() -> CaseStatusTransition:
    return CaseStatusTransition(
        id=HISTORY_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        from_status=None,
        to_status=CaseStatus.RECEIVED,
        actor_id=USER_ID,
        reason="case_created",
        occurred_at=NOW,
    )


def _evidence() -> EvidenceMetadata:
    return EvidenceMetadata(
        id=EVIDENCE_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        evidence_type=EvidenceType.IMAGE,
        upload_status=EvidenceUploadStatus.PENDING,
        storage_bucket="csight-evidence",
        object_key=f"tenants/{TENANT_ID}/cases/{CASE_ID}/evidence/{EVIDENCE_ID}/original",
        original_filename="damage.png",
        content_type="image/png",
        size_bytes=1024,
        sha256="a" * 64,
        width=640,
        height=480,
        created_by=USER_ID,
        created_at=NOW,
        updated_at=NOW,
    )


def _idempotency() -> IdempotencyRecord:
    return IdempotencyRecord(
        id=IDEMPOTENCY_ID,
        tenant_id=TENANT_ID,
        operation="case.create.v1",
        idempotency_key="request-1",
        request_hash="b" * 64,
        resource_type="case",
        resource_id=CASE_ID,
        response_status=201,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )


def test_case_mapping_round_trip_normalizes_uuid_boundary() -> None:
    case = _case()

    model = case_model_from_entity(case)

    assert model.id == UUID(CASE_ID)
    assert model.tenant_id == UUID(TENANT_ID)
    assert model.created_by == UUID(USER_ID)
    assert (
        case_entity_from_model(
            model,
            sensitive_payload_id=UUID(CASE_ID),
            sensitive_customer_message=case.customer_message,
        )
        == case
    )


def test_case_mapping_never_falls_back_to_legacy_sensitive_content() -> None:
    model = case_model_from_entity(_case())

    with pytest.raises(InconsistentPersistenceStateError, match="missing"):
        case_entity_from_model(model)

    purged = case_entity_from_model(
        model,
        sensitive_payload_id=UUID(CASE_ID),
        sensitive_customer_message=None,
        sensitive_purged_at=NOW + timedelta(days=30),
    )

    assert purged.customer_message == PURGED_CUSTOMER_MESSAGE
    assert purged.customer_message != model.customer_message


def test_history_evidence_and_idempotency_mapping_round_trip() -> None:
    history = _history()
    evidence = _evidence()
    idempotency = _idempotency()
    idempotency_model = IdempotencyRecordModel(**idempotency_model_values(idempotency))

    assert history_entity_from_model(history_model_from_entity(history)) == history
    assert evidence_entity_from_model(evidence_model_from_entity(evidence)) == evidence
    assert idempotency_entity_from_model(idempotency_model) == idempotency


def test_invalid_query_ids_fail_closed_without_issuing_sql() -> None:
    session_mock = MagicMock(spec=Session)
    session = cast(Session, session_mock)
    cases = SQLAlchemyCaseRepository(session)
    evidence = SQLAlchemyEvidenceRepository(session)

    assert cases.get(tenant_id="not-a-uuid", case_id=CASE_ID) is None
    assert cases.list(tenant_id="not-a-uuid", criteria=CaseListCriteria()) == ()
    assert cases.count(tenant_id="not-a-uuid", criteria=CaseListCriteria()) == 0
    assert evidence.get(tenant_id=TENANT_ID, case_id=CASE_ID, evidence_id="invalid") is None
    assert evidence.list(tenant_id="invalid", case_id=CASE_ID) == ()
    session_mock.scalars.assert_not_called()


def test_write_repositories_reject_entity_tenant_mismatch_before_persistence() -> None:
    session_mock = MagicMock(spec=Session)
    session = cast(Session, session_mock)

    with pytest.raises(ValueError, match="repository tenant scope"):
        SQLAlchemyCaseRepository(session).add(
            tenant_id=OTHER_TENANT_ID,
            case=_case(),
        )
    with pytest.raises(ValueError, match="repository tenant scope"):
        SQLAlchemyCaseStatusHistoryRepository(session).add(
            tenant_id=OTHER_TENANT_ID,
            transition=_history(),
        )
    with pytest.raises(ValueError, match="repository tenant scope"):
        SQLAlchemyEvidenceRepository(session).add(
            tenant_id=OTHER_TENANT_ID,
            evidence=_evidence(),
        )
    with pytest.raises(ValueError, match="repository tenant scope"):
        SQLAlchemyIdempotencyRepository(session).claim(
            tenant_id=OTHER_TENANT_ID,
            record=_idempotency(),
        )

    session_mock.add.assert_not_called()
    session_mock.scalars.assert_not_called()


def test_uow_delegates_flush_commit_and_always_rolls_back_then_closes() -> None:
    session_mock = MagicMock(spec=Session)
    unit_of_work = SQLAlchemyCaseUnitOfWork(cast(Session, session_mock))

    assert isinstance(unit_of_work, CaseUnitOfWork)
    with unit_of_work as entered:
        assert entered is unit_of_work
        entered.flush()
        entered.commit()

    session_mock.flush.assert_called_once_with()
    session_mock.commit.assert_called_once_with()
    session_mock.rollback.assert_called_once_with()
    session_mock.close.assert_called_once_with()


def test_uow_rolls_back_and_closes_when_the_body_raises() -> None:
    session_mock = MagicMock(spec=Session)
    unit_of_work = SQLAlchemyCaseUnitOfWork(cast(Session, session_mock))

    with pytest.raises(RuntimeError, match="boom"), unit_of_work:
        raise RuntimeError("boom")

    session_mock.commit.assert_not_called()
    session_mock.rollback.assert_called_once_with()
    session_mock.close.assert_called_once_with()
