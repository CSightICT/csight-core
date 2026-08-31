"""Add sensitive payload lifecycle and Evidence idempotency foundations.

Revision ID: 20260829_0017_service_pilot_foundation
Revises: 20260828_0016_communication_learning_assets
Create Date: 2026-08-29
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import timedelta
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import context, op

revision: str = "20260829_0017_service_pilot_foundation"
down_revision: str | None = "20260828_0016_communication_learning_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SENSITIVE_PAYLOAD_SCHEMA_VERSION = "case_sensitive_payload/1.0.0"
LEGACY_RETENTION_POLICY_VERSION = "legacy-migration/30d"
LIFECYCLE_SCHEMA_VERSION = "data_lifecycle_event/1.0.0"


def upgrade() -> None:
    op.create_table(
        "case_sensitive_payloads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("customer_message", sa.Text(), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("retention_policy_version", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_case_sensitive_payloads_tenant_case",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"schema_version = '{SENSITIVE_PAYLOAD_SCHEMA_VERSION}'",
            name=op.f("ck_case_sensitive_payloads_schema_version_supported"),
        ),
        sa.CheckConstraint(
            "payload_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_case_sensitive_payloads_payload_sha256_valid"),
        ),
        sa.CheckConstraint(
            "length(btrim(retention_policy_version)) > 0",
            name=op.f("ck_case_sensitive_payloads_retention_policy_nonempty"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_case_sensitive_payloads_expiry_after_creation"),
        ),
        sa.CheckConstraint(
            "(purged_at IS NULL AND customer_message IS NOT NULL "
            "AND length(btrim(customer_message)) > 0) OR "
            "(purged_at IS NOT NULL AND customer_message IS NULL)",
            name=op.f("ck_case_sensitive_payloads_purge_state_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_sensitive_payloads")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_case_sensitive_payloads_tenant_id"),
        sa.UniqueConstraint("tenant_id", "case_id", name="uq_case_sensitive_payloads_tenant_case"),
    )
    op.create_index(
        "ix_case_sensitive_payloads_expiry",
        "case_sensitive_payloads",
        ["tenant_id", "expires_at", "case_id"],
        postgresql_where=sa.text("purged_at IS NULL"),
    )

    op.create_table(
        "data_lifecycle_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("retention_policy_version", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_data_lifecycle_events_tenant_case",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"schema_version = '{LIFECYCLE_SCHEMA_VERSION}'",
            name=op.f("ck_data_lifecycle_events_schema_version_supported"),
        ),
        sa.CheckConstraint(
            "event_type IN ('SENSITIVE_PAYLOAD_CREATED', 'SENSITIVE_PAYLOAD_MIGRATED', "
            "'SENSITIVE_PAYLOAD_PURGED', "
            "'EVIDENCE_RECONCILED', 'EVIDENCE_PURGED')",
            name=op.f("ck_data_lifecycle_events_event_type_allowed"),
        ),
        sa.CheckConstraint(
            "resource_type IN ('CASE_SENSITIVE_PAYLOAD', 'EVIDENCE')",
            name=op.f("ck_data_lifecycle_events_resource_type_allowed"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(details) = 'object'",
            name=op.f("ck_data_lifecycle_events_details_object"),
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_data_lifecycle_events_content_hash_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_lifecycle_events")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_data_lifecycle_events_tenant_id"),
    )
    op.create_index(
        "ix_data_lifecycle_events_tenant_case_time",
        "data_lifecycle_events",
        ["tenant_id", "case_id", "occurred_at", "id"],
    )

    op.add_column(
        "case_evidence",
        sa.Column("idempotency_key", sa.String(255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_case_evidence_tenant_case_idempotency_key",
        "case_evidence",
        ["tenant_id", "case_id", "idempotency_key"],
    )
    op.create_unique_constraint(
        "uq_case_evidence_tenant_case_idempotency_sha256",
        "case_evidence",
        ["tenant_id", "case_id", "idempotency_key", "sha256"],
    )
    _backfill_sensitive_payloads()


def _backfill_sensitive_payloads() -> None:
    if context.is_offline_mode():
        return
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, tenant_id, customer_message, created_at, updated_at "
            "FROM cases ORDER BY created_at, id"
        )
    ).mappings()
    payloads = sa.table(
        "case_sensitive_payloads",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("case_id", sa.Uuid()),
        sa.column("schema_version", sa.String()),
        sa.column("customer_message", sa.Text()),
        sa.column("payload_sha256", sa.String()),
        sa.column("retention_policy_version", sa.String()),
        sa.column("expires_at", sa.DateTime(timezone=True)),
        sa.column("purged_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    lifecycle = sa.table(
        "data_lifecycle_events",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("case_id", sa.Uuid()),
        sa.column("schema_version", sa.String()),
        sa.column("event_type", sa.String()),
        sa.column("resource_type", sa.String()),
        sa.column("resource_id", sa.Uuid()),
        sa.column("retention_policy_version", sa.String()),
        sa.column("actor_id", sa.Uuid()),
        sa.column("correlation_id", sa.Uuid()),
        sa.column("details", postgresql.JSONB()),
        sa.column("occurred_at", sa.DateTime(timezone=True)),
        sa.column("content_hash", sa.String()),
    )
    for row in rows:
        payload_id = uuid4()
        correlation_id = uuid4()
        message = str(row["customer_message"])
        payload_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        created_at = row["created_at"]
        connection.execute(
            payloads.insert().values(
                id=payload_id,
                tenant_id=row["tenant_id"],
                case_id=row["id"],
                schema_version=SENSITIVE_PAYLOAD_SCHEMA_VERSION,
                customer_message=message,
                payload_sha256=payload_hash,
                retention_policy_version=LEGACY_RETENTION_POLICY_VERSION,
                expires_at=created_at + timedelta(days=30),
                purged_at=None,
                created_at=created_at,
                updated_at=row["updated_at"],
            )
        )
        event_hash = hashlib.sha256(
            (
                f"{row['tenant_id']}:{row['id']}:{payload_id}:"
                f"{LEGACY_RETENTION_POLICY_VERSION}:{created_at.isoformat()}"
            ).encode()
        ).hexdigest()
        connection.execute(
            lifecycle.insert().values(
                id=uuid4(),
                tenant_id=row["tenant_id"],
                case_id=row["id"],
                schema_version=LIFECYCLE_SCHEMA_VERSION,
                event_type="SENSITIVE_PAYLOAD_MIGRATED",
                resource_type="CASE_SENSITIVE_PAYLOAD",
                resource_id=payload_id,
                retention_policy_version=LEGACY_RETENTION_POLICY_VERSION,
                actor_id=None,
                correlation_id=correlation_id,
                details={"source": "cases.customer_message", "pii_included": False},
                occurred_at=created_at,
                content_hash=event_hash,
            )
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_case_evidence_tenant_case_idempotency_sha256",
        "case_evidence",
        type_="unique",
    )
    op.drop_constraint(
        "uq_case_evidence_tenant_case_idempotency_key",
        "case_evidence",
        type_="unique",
    )
    op.drop_column("case_evidence", "idempotency_key")
    op.drop_index("ix_data_lifecycle_events_tenant_case_time", table_name="data_lifecycle_events")
    op.drop_table("data_lifecycle_events")
    op.drop_index("ix_case_sensitive_payloads_expiry", table_name="case_sensitive_payloads")
    op.drop_table("case_sensitive_payloads")
