"""Data-only repair proof in a newly created disposable PostgreSQL database."""

import hashlib
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from app.adapters.persistence.models import CaseEvidenceModel, TenantModel, UserModel
from app.adapters.persistence.unit_of_work import create_analysis_unit_of_work_factory
from app.platform.case import Case, RequestedAction
from tests.integration.test_analysis_application_e2e import NOW
from tests.integration.test_schema_drift_repair_migration import MigrationDatabase
from tests.integration.test_schema_drift_repair_migration import (
    migration_database as _database_fixture,
)

pytestmark = pytest.mark.integration
migration_database = _database_fixture
PREVIOUS = "20260910_0037_shadow_human_feedback"
FIRST = "689b29b3-3b67-48c9-b200-087539714ee5"
SECOND = "64e9c39d-3dab-46c8-9942-4d77aad2055e"
FIXTURE_SHA = "5f633dccce6bfd32efdf06f05ae35449d3d7fb575d065e53081c3e6d6b153039"


def test_audited_repair_is_atomic_scoped_idempotent_and_preserves_receipts(
    migration_database: MigrationDatabase,
) -> None:
    config, engine = migration_database.config, migration_database.engine
    command.upgrade(config, "head")  # No target rows on a blank database.
    command.check(config)
    command.downgrade(config, PREVIOUS)
    tenant, user = uuid4(), uuid4()
    with Session(engine) as session:
        session.add(TenantModel(id=tenant, slug=f"analysis-{tenant}", name="Repair fixture"))
        session.flush()
        session.add(
            UserModel(
                id=user,
                tenant_id=tenant,
                email="fixture@example.test",
                password_hash="not-a-login",
                display_name="Fixture",
            )
        )
        session.commit()
    case = Case.create(
        case_id=str(uuid4()),
        tenant_id=str(tenant),
        order_ref="FIXTURE-ORDER",
        product_ref="FIXTURE-PRODUCT",
        customer_message="Synthetic repair fixture.",
        requested_action=RequestedAction.EXCHANGE,
        attributes={},
        created_by=str(user),
        now=NOW,
    )
    with create_analysis_unit_of_work_factory(engine)() as uow:
        uow.cases.add(tenant_id=str(tenant), case=case)
        uow.commit()
    unrelated = str(uuid4())
    with Session(engine) as session:
        for identifier in (FIRST, SECOND, unrelated):
            session.add(
                CaseEvidenceModel(
                    id=UUID(identifier),
                    tenant_id=tenant,
                    case_id=UUID(case.id),
                    evidence_type="IMAGE",
                    upload_status="AVAILABLE",
                    storage_bucket="evidence",
                    object_key=f"tenants/{tenant}/cases/{case.id}/evidence/{identifier}/original",
                    original_filename="fixture.png",
                    content_type="image/png",
                    size_bytes=33 if identifier == FIRST else 32,
                    sha256=FIXTURE_SHA,
                    width=64,
                    height=48,
                    created_by=user,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        session.commit()
    with pytest.raises(RuntimeError, match="fixture changed"):
        command.upgrade(config, "head")
    with engine.begin() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM case_evidence WHERE upload_status='AVAILABLE'")
            )
            == 3
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM data_lifecycle_events "
                    "WHERE event_type='EVIDENCE_RECONCILED'"
                )
            )
            == 0
        )
        connection.execute(
            text("UPDATE case_evidence SET size_bytes=32 WHERE id=:id"), {"id": FIRST}
        )
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, PREVIOUS)
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM case_evidence WHERE upload_status='FAILED'")
            )
            == 2
        )
        assert (
            connection.scalar(
                text("SELECT upload_status FROM case_evidence WHERE id=:id"), {"id": unrelated}
            )
            == "AVAILABLE"
        )
        rows = (
            connection.execute(
                text("SELECT * FROM data_lifecycle_events WHERE event_type='EVIDENCE_RECONCILED'")
            )
            .mappings()
            .all()
        )
        assert len(rows) == 2
        for row in rows:
            assert row["actor_id"] is None
            canonical = {
                key: row[key]
                for key in (
                    "event_type",
                    "resource_type",
                    "retention_policy_version",
                    "details",
                    "operation_key",
                )
            }
            canonical.update(
                {key: str(row[key]) for key in ("tenant_id", "case_id", "resource_id")}
            )
            canonical["occurred_at"] = row["occurred_at"].isoformat()
            assert (
                hashlib.sha256(
                    json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                == row["content_hash"]
            )
        assert connection.scalar(text("SELECT count(*) FROM cases")) == 1
        assert connection.scalar(text("SELECT count(*) FROM human_review_decisions")) == 0
