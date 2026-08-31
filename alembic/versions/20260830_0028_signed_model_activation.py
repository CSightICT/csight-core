"""Add signed LLM release manifests and append-only activation events.

Revision ID: 20260830_0028_signed_model_activation
Revises: 20260830_0027_analysis_text_erasure
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260830_0028_signed_model_activation"
down_revision: str | None = "20260830_0027_analysis_text_erasure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("llm_release_manifests", "llm_model_activation_events")
_TENANT_EXPRESSION = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "llm_release_manifests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("package_name", sa.String(128), nullable=False),
        sa.Column("package_version", sa.String(128), nullable=False),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manifest_digest", sa.String(71), nullable=False),
        sa.Column("signing_key_id", sa.String(128), nullable=False),
        sa.Column("signature_algorithm", sa.String(16), nullable=False),
        sa.Column("signature_base64", sa.String(88), nullable=False),
        sa.Column("registered_by", sa.Uuid(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "task = 'PRODUCT_DEFECT_TEXT_EXTRACTION_V2'",
            name=op.f("ck_llm_release_manifests_task_supported"),
        ),
        sa.CheckConstraint(
            "manifest_digest ~ '^sha256:[0-9a-f]{64}$'",
            name=op.f("ck_llm_release_manifests_manifest_digest_valid"),
        ),
        sa.CheckConstraint(
            "signature_algorithm = 'ED25519'",
            name=op.f("ck_llm_release_manifests_signature_algorithm_supported"),
        ),
        sa.CheckConstraint(
            "length(signature_base64) = 88",
            name=op.f("ck_llm_release_manifests_signature_length_valid"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(manifest) = 'object'",
            name=op.f("ck_llm_release_manifests_manifest_object"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_llm_release_manifests_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "registered_by"],
            ["users.tenant_id", "users.id"],
            name="fk_llm_release_manifests_registered_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_release_manifests")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_llm_release_manifests_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "task", "id", name="uq_llm_release_manifests_tenant_task_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "package_name",
            "package_version",
            name="uq_llm_release_manifests_package_version",
        ),
        sa.UniqueConstraint("tenant_id", "manifest_digest", name="uq_llm_release_manifests_digest"),
    )
    op.create_index(
        "ix_llm_release_manifests_tenant_task_registered",
        "llm_release_manifests",
        ["tenant_id", "task", "registered_at"],
    )

    op.create_table(
        "llm_model_activation_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("execution_mode", sa.String(16), nullable=False),
        sa.Column("model_release_id", sa.Uuid(), nullable=False),
        sa.Column("previous_activation_id", sa.Uuid(), nullable=True),
        sa.Column("activated_by", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "task = 'PRODUCT_DEFECT_TEXT_EXTRACTION_V2'",
            name=op.f("ck_llm_model_activation_events_task_supported"),
        ),
        sa.CheckConstraint(
            "execution_mode IN ('PRIMARY', 'SHADOW')",
            name=op.f("ck_llm_model_activation_events_execution_mode_supported"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_llm_model_activation_events_request_hash_valid"),
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) > 0",
            name=op.f("ck_llm_model_activation_events_reason_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name=op.f("ck_llm_model_activation_events_idempotency_key_nonempty"),
        ),
        sa.CheckConstraint(
            "previous_activation_id IS NULL OR previous_activation_id <> id",
            name=op.f("ck_llm_model_activation_events_previous_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_llm_model_activation_events_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task", "model_release_id"],
            [
                "llm_release_manifests.tenant_id",
                "llm_release_manifests.task",
                "llm_release_manifests.id",
            ],
            name="fk_llm_model_activation_events_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task", "execution_mode", "previous_activation_id"],
            [
                "llm_model_activation_events.tenant_id",
                "llm_model_activation_events.task",
                "llm_model_activation_events.execution_mode",
                "llm_model_activation_events.id",
            ],
            name="fk_llm_model_activation_events_previous",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "activated_by"],
            ["users.tenant_id", "users.id"],
            name="fk_llm_model_activation_events_activated_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_model_activation_events")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_llm_model_activation_events_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "task",
            "execution_mode",
            "id",
            name="uq_llm_model_activation_events_tenant_mode_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "previous_activation_id",
            name="uq_llm_model_activation_events_previous",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "task",
            "execution_mode",
            "idempotency_key",
            name="uq_llm_model_activation_events_idempotency",
        ),
    )
    op.create_index(
        "ix_llm_model_activation_events_active",
        "llm_model_activation_events",
        ["tenant_id", "task", "execution_mode", sa.text("activated_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "uq_llm_model_activation_events_root",
        "llm_model_activation_events",
        ["tenant_id", "task", "execution_mode"],
        unique=True,
        postgresql_where=sa.text("previous_activation_id IS NULL"),
    )
    _install_append_only_contract()
    _install_least_privilege_rls()


def _install_append_only_contract() -> None:
    op.execute(
        """
        CREATE FUNCTION csight_reject_model_release_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Signed model release records are append-only';
        END;
        $$
        """
    )
    for table_name in _TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION csight_reject_model_release_mutation()
            """
        )


def _install_least_privilege_rls() -> None:
    for table_name in _TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table_name} TO csight_api_role")
        op.execute(f"GRANT SELECT ON {table_name} TO csight_worker_role")
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY csight_api_tenant_scope ON {table_name}
            FOR ALL TO csight_api_role
            USING ({_TENANT_EXPRESSION})
            WITH CHECK ({_TENANT_EXPRESSION})
            """
        )
        op.execute(
            f"""
            CREATE POLICY csight_worker_tenant_select ON {table_name}
            FOR SELECT TO csight_worker_role
            USING ({_TENANT_EXPRESSION})
            """
        )


def downgrade() -> None:
    for table_name in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS csight_worker_tenant_select ON {table_name}")
        op.execute(f"DROP POLICY IF EXISTS csight_api_tenant_scope ON {table_name}")
        op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL PRIVILEGES ON {table_name} FROM csight_worker_role")
        op.execute(f"REVOKE ALL PRIVILEGES ON {table_name} FROM csight_api_role")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS csight_reject_model_release_mutation()")
    op.drop_index(
        "uq_llm_model_activation_events_root",
        table_name="llm_model_activation_events",
    )
    op.drop_index(
        "ix_llm_model_activation_events_active",
        table_name="llm_model_activation_events",
    )
    op.drop_table("llm_model_activation_events")
    op.drop_index(
        "ix_llm_release_manifests_tenant_task_registered",
        table_name="llm_release_manifests",
    )
    op.drop_table("llm_release_manifests")
