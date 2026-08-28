"""Add customer communication simulations and tenant learning assets.

Revision ID: 20260828_0016_communication_learning_assets
Revises: 20260827_0015_vision_image_assessment
Create Date: 2026-08-28
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import context, op

revision: str = "20260828_0016_communication_learning_assets"
down_revision: str | None = "20260827_0015_vision_image_assessment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_communication_simulations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("review_report_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("template_name", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(32), nullable=False),
        sa.Column("recipient_label", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(32), nullable=False),
        sa.Column("side_effects_performed", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_report_id"],
            ["review_reports.tenant_id", "review_reports.id"],
            name="fk_customer_communication_simulations_report",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "schema_version = 'customer_communication_simulation/1.0.0'",
            name=op.f("ck_customer_communication_simulations_schema_version_supported"),
        ),
        sa.CheckConstraint(
            "channel = 'EMAIL'",
            name=op.f("ck_customer_communication_simulations_channel_email_only"),
        ),
        sa.CheckConstraint(
            "delivery_status = 'SIMULATED_NOT_SENT' AND side_effects_performed = false",
            name=op.f("ck_customer_communication_simulations_no_external_effects"),
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_customer_communication_simulations_content_hash_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_communication_simulations")),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_customer_communication_simulations_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "review_report_id",
            "channel",
            "template_name",
            "template_version",
            name="uq_customer_communication_simulations_report_template",
        ),
    )
    op.create_index(
        "ix_customer_communication_simulations_case_latest",
        "customer_communication_simulations",
        ["tenant_id", "case_id", "created_at", "id"],
    )

    op.create_table(
        "case_learning_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("review_report_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("subject_pseudonym", sa.String(64), nullable=True),
        sa.Column("feature_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("label_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("version_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("privacy_scope", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_report_id"],
            ["review_reports.tenant_id", "review_reports.id"],
            name="fk_case_learning_assets_report",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "schema_version = 'case_learning_asset/1.0.0'",
            name=op.f("ck_case_learning_assets_schema_version_supported"),
        ),
        sa.CheckConstraint(
            "subject_pseudonym IS NULL OR subject_pseudonym ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_case_learning_assets_subject_pseudonym_valid"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(feature_snapshot) = 'object' "
            "AND jsonb_typeof(label_snapshot) = 'object' "
            "AND jsonb_typeof(version_snapshot) = 'object' "
            "AND jsonb_typeof(privacy_scope) = 'object'",
            name=op.f("ck_case_learning_assets_snapshots_object"),
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_case_learning_assets_content_hash_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_learning_assets")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_case_learning_assets_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "review_report_id",
            "schema_version",
            name="uq_case_learning_assets_report_schema",
        ),
    )
    op.create_index(
        "ix_case_learning_assets_tenant_created",
        "case_learning_assets",
        ["tenant_id", "created_at", "id"],
    )
    _backfill_existing_review_reports()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _record(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _backfill_existing_review_reports() -> None:
    """Turn existing terminal reports into the same allowlisted tenant assets."""

    if context.is_offline_mode():
        return
    connection = op.get_bind()
    reports = connection.execute(
        sa.text(
            "SELECT id, tenant_id, case_id, case_snapshot, analysis_snapshot, "
            "policy_snapshot, review_snapshot, resolution_snapshot, dry_run_snapshot, "
            "qualification_snapshot, data_scope, generated_at, content_hash "
            "FROM review_reports ORDER BY generated_at, id"
        )
    ).mappings()
    assets = sa.table(
        "case_learning_assets",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("case_id", sa.Uuid()),
        sa.column("review_report_id", sa.Uuid()),
        sa.column("schema_version", sa.String()),
        sa.column("subject_pseudonym", sa.String()),
        sa.column("feature_snapshot", postgresql.JSONB()),
        sa.column("label_snapshot", postgresql.JSONB()),
        sa.column("version_snapshot", postgresql.JSONB()),
        sa.column("privacy_scope", postgresql.JSONB()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("content_hash", sa.String()),
    )
    for row in reports:
        data_scope = _record(row["data_scope"])
        if data_scope.get("report_generation") == "DEGRADED_INTEGRITY_FAILURE_SNAPSHOT":
            continue
        case_snapshot = _record(row["case_snapshot"])
        analysis = _record(row["analysis_snapshot"])
        policy = _record(row["policy_snapshot"])
        review = _record(row["review_snapshot"])
        resolution = _record(row["resolution_snapshot"])
        dry_run = _record(row["dry_run_snapshot"])
        intent = _record(dry_run.get("intent"))
        result = _record(dry_run.get("result"))
        qualification = _record(row["qualification_snapshot"])
        vision = _record(
            qualification.get("vision")
            or qualification.get("vision_model")
            or qualification.get("model")
        )
        commerce = _record(case_snapshot.get("synthetic_commerce_context"))
        customer = _record(commerce.get("customer"))
        customer_id = customer.get("customer_id")
        subject_pseudonym = None
        if isinstance(customer_id, str) and customer_id:
            subject_pseudonym = _canonical_hash(
                {"tenant_id": str(row["tenant_id"]), "customer_id": customer_id}
            )
        created_at = row["generated_at"].astimezone(UTC)
        payload = {
            "schema_version": "case_learning_asset/1.0.0",
            "asset_id": str(uuid4()),
            "tenant_id": str(row["tenant_id"]),
            "case_id": str(row["case_id"]),
            "review_report_id": str(row["id"]),
            "subject_pseudonym": subject_pseudonym,
            "feature_snapshot": {
                "product_ref": case_snapshot.get("product_ref"),
                "requested_action": case_snapshot.get("requested_action"),
                "analysis_status": analysis.get("status"),
                "policy_summary_status": policy.get("summary_status"),
            },
            "label_snapshot": {
                "human_decision": review.get("decision_type"),
                "resolution_status": resolution.get("status"),
                "action_type": intent.get("action_type"),
                "simulation_outcome": result.get("outcome"),
            },
            "version_snapshot": {
                "analysis_pipeline": analysis.get("pipeline_name"),
                "analysis_pipeline_version": analysis.get("pipeline_version"),
                "policy_rule_set_version": policy.get("rule_set_version"),
                "policy_rule_set_hash": policy.get("rule_set_hash"),
                "vision_model": vision.get("model_name") or vision.get("name"),
                "vision_model_version": vision.get("model_version") or vision.get("version"),
                "decision_schema_version": review.get("decision_schema_version"),
                "resolution_mapping_version": resolution.get("mapping_version"),
                "report_schema_version": "review_report/1.0.0",
            },
            "privacy_scope": {
                "tenant_scoped": True,
                "append_only": True,
                "raw_customer_message_included": False,
                "direct_contact_values_included": False,
                "postal_address_included": False,
                "human_rationale_included": False,
                "source_report_hash": row["content_hash"],
            },
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
        }
        connection.execute(
            assets.insert().values(
                id=payload["asset_id"],
                tenant_id=row["tenant_id"],
                case_id=row["case_id"],
                review_report_id=row["id"],
                schema_version=payload["schema_version"],
                subject_pseudonym=subject_pseudonym,
                feature_snapshot=payload["feature_snapshot"],
                label_snapshot=payload["label_snapshot"],
                version_snapshot=payload["version_snapshot"],
                privacy_scope=payload["privacy_scope"],
                created_at=created_at,
                content_hash=_canonical_hash(payload),
            )
        )


def downgrade() -> None:
    op.drop_index("ix_case_learning_assets_tenant_created", table_name="case_learning_assets")
    op.drop_table("case_learning_assets")
    op.drop_index(
        "ix_customer_communication_simulations_case_latest",
        table_name="customer_communication_simulations",
    )
    op.drop_table("customer_communication_simulations")
