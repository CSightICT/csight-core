"""Correct seven audited legacy fixture Evidence statuses, preserving all history.

Revision ID: 20260910_0038_fixture_evidence_repair
Revises: 20260910_0037_shadow_human_feedback
"""

import hashlib
import json
from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa

from alembic import op

revision: str = "20260910_0038_fixture_evidence_repair"
down_revision: str = "20260910_0037_shadow_human_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed IDs from the 2026-09-10 read-only DB + MinIO audit, NOT a tenant-wide repair.
TARGETS = (
    "689b29b3-3b67-48c9-b200-087539714ee5",
    "64e9c39d-3dab-46c8-9942-4d77aad2055e",
    "2bceab6d-73b6-4b0c-a02c-999fbf9a5e65",
    "65e58190-d050-46f7-bd5d-f3ff2a836826",
    "07719b89-2718-4614-810f-8961442768a9",
    "5d165c26-cc24-48d6-a9d0-304051f5abf9",
    "14c0cd28-39e4-4f97-8b9e-1ec12b0c15b3",
)
FIXTURE_SHA = "5f633dccce6bfd32efdf06f05ae35449d3d7fb575d065e53081c3e6d6b153039"


def upgrade() -> None:
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text("""
            SELECT e.*, t.slug, c.source_scope,
                EXISTS (SELECT 1 FROM analysis_run_evidence a WHERE a.evidence_id=e.id)
                OR EXISTS (SELECT 1 FROM vision_analysis_results v WHERE v.evidence_id=e.id)
                AS referenced
            FROM case_evidence e JOIN tenants t ON t.id=e.tenant_id
            JOIN cases c ON c.id=e.case_id AND c.tenant_id=e.tenant_id
            WHERE e.id::text IN :targets ORDER BY e.id FOR UPDATE OF e
        """).bindparams(sa.bindparam("targets", expanding=True)),
            {"targets": TARGETS},
        )
        .mappings()
        .all()
    )
    now = connection.scalar(sa.text("SELECT CURRENT_TIMESTAMP"))
    for row in rows:
        key = f"fixture-evidence-repair/0038:{row['id']}"
        canonical_key = (
            f"tenants/{row['tenant_id']}/cases/{row['case_id']}/evidence/{row['id']}/original"
        )
        if not (
            row["slug"] == f"analysis-{row['tenant_id']}"
            and row["source_scope"] == "NOT_ATTESTED"
            and row["sha256"] == FIXTURE_SHA
            and row["size_bytes"] == 32
            and row["width"] == 64
            and row["height"] == 48
            and row["storage_bucket"] == "evidence"
            and row["content_type"] == "image/png"
            and row["evidence_type"] == "IMAGE"
            and row["object_key"] == canonical_key
            and not row["referenced"]
            and row["created_at"].isoformat() == "2026-08-26T06:00:00+00:00"
        ):
            raise RuntimeError("Audited fixture changed; repair aborted")
        receipt = connection.scalar(
            sa.text("""
            SELECT count(*) FROM data_lifecycle_events
            WHERE tenant_id=:tenant AND operation_key=:key
              AND resource_id=:id AND event_type='EVIDENCE_RECONCILED'
        """),
            {"tenant": row["tenant_id"], "key": key, "id": row["id"]},
        )
        if row["upload_status"] == "FAILED" and receipt == 1:
            continue
        if (
            row["upload_status"] != "AVAILABLE"
            or receipt != 0
            or row["updated_at"] != row["created_at"]
        ):
            raise RuntimeError("Audited fixture state changed; repair aborted")
        details = {
            "reason": "audited_legacy_fixture_object_missing",
            "from_status": "AVAILABLE",
            "to_status": "FAILED",
            "pii_included": False,
            "initiator": "SCHEMA_OWNER_DATA_MIGRATION_0038",
        }
        canonical = {
            "event_type": "EVIDENCE_RECONCILED",
            "tenant_id": str(row["tenant_id"]),
            "case_id": str(row["case_id"]),
            "resource_type": "EVIDENCE",
            "resource_id": str(row["id"]),
            "retention_policy_version": "evidence-consistency/1.0.0",
            "details": details,
            "operation_key": key,
            "occurred_at": now.isoformat(),
        }
        content_hash = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        connection.execute(
            sa.text("""
            INSERT INTO data_lifecycle_events
                (id,tenant_id,case_id,schema_version,event_type,resource_type,resource_id,
                 retention_policy_version,actor_id,correlation_id,details,occurred_at,
                 content_hash,operation_key)
            VALUES (:event_id,:tenant,:case,'data_lifecycle_event/1.0.0','EVIDENCE_RECONCILED',
                'EVIDENCE',:id,'evidence-consistency/1.0.0',NULL,:correlation,
                CAST(:details AS jsonb),:now,:hash,:key)
        """),
            {
                "event_id": uuid5(NAMESPACE_URL, key),
                "tenant": row["tenant_id"],
                "case": row["case_id"],
                "id": row["id"],
                "correlation": uuid4(),
                "details": json.dumps(details),
                "now": now,
                "hash": content_hash,
                "key": key,
            },
        )
        connection.execute(
            sa.text("""
            UPDATE case_evidence SET upload_status='FAILED',updated_at=:now
            WHERE id=:id AND tenant_id=:tenant
        """),
            {"now": now, "id": row["id"], "tenant": row["tenant_id"]},
        )


def downgrade() -> None:
    # Data-only migration: keep corrected availability and append-only repair receipts.
    pass
