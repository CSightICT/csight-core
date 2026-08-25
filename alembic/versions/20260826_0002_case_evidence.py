"""Create Sprint 1 identity, Case, Evidence, and idempotency tables.

Revision ID: 20260826_0002
Revises: 20260825_0001
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260826_0002"
down_revision: str | None = "20260825_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_NAMES = ("ADMIN", "REVIEWER", "QUALITY_VIEWER")
CASE_STATUSES = (
    "RECEIVED",
    "VALIDATING",
    "INVALID_INPUT",
    "QUEUED",
    "ANALYZING",
    "PARTIAL_SUCCESS",
    "ANALYSIS_FAILED",
    "ANALYSIS_COMPLETED",
    "RETRY_WAITING",
    "POLICY_EVALUATED",
    "APPROVAL_CANDIDATE",
    "HUMAN_REVIEW_REQUIRED",
    "ADDITIONAL_EVIDENCE_REQUIRED",
    "ESCALATED",
    "RESOLVED",
)
DOMAIN_TYPES = ("product_defect_cs",)
REQUESTED_ACTIONS = (
    "EXCHANGE",
    "REFUND",
    "RETURN",
    "REPAIR",
    "INFORMATION",
    "OTHER",
    "UNSPECIFIED",
)
EVIDENCE_TYPES = ("TEXT", "IMAGE", "DOCUMENT", "AUDIO", "METADATA")
EVIDENCE_UPLOAD_STATUSES = ("PENDING", "AVAILABLE", "FAILED")
IDEMPOTENCY_OPERATIONS = ("case.create.v1",)
IDEMPOTENCY_RESOURCE_TYPES = ("case",)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0",
            name=op.f("ck_tenants_name_nonempty"),
        ),
        sa.CheckConstraint(
            "slug = lower(slug)",
            name=op.f("ck_tenants_slug_lowercase"),
        ),
        sa.CheckConstraint(
            "length(btrim(slug)) > 0",
            name=op.f("ck_tenants_slug_nonempty"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            f"name IN ({_sql_values(ROLE_NAMES)})",
            name=op.f("ck_roles_name_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0",
            name=op.f("ck_users_display_name_nonempty"),
        ),
        sa.CheckConstraint(
            "email = lower(email)",
            name=op.f("ck_users_email_lowercase"),
        ),
        sa.CheckConstraint(
            "length(btrim(email)) > 0",
            name=op.f("ck_users_email_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(password_hash)) > 0",
            name=op.f("ck_users_password_hash_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_users_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("tenant_id", "email", name=op.f("uq_users_tenant_id_email")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_users_tenant_id_id")),
    )

    op.create_table(
        "user_roles",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ("role_id",),
            ("roles.id",),
            name=op.f("fk_user_roles_role_id_roles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_user_roles_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "user_id"),
            ("users.tenant_id", "users.id"),
            name=op.f("fk_user_roles_tenant_id_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "user_id",
            "role_id",
            name=op.f("pk_user_roles"),
        ),
    )

    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "domain_type",
            sa.String(length=64),
            server_default=sa.text("'product_defect_cs'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=64),
            server_default=sa.text("'RECEIVED'"),
            nullable=False,
        ),
        sa.Column("order_ref", sa.String(length=255), nullable=False),
        sa.Column("product_ref", sa.String(length=255), nullable=False),
        sa.Column("customer_message", sa.Text(), nullable=False),
        sa.Column("requested_action", sa.String(length=32), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(customer_message)) > 0",
            name=op.f("ck_cases_customer_message_nonempty"),
        ),
        sa.CheckConstraint(
            f"domain_type IN ({_sql_values(DOMAIN_TYPES)})",
            name=op.f("ck_cases_domain_type_allowed"),
        ),
        sa.CheckConstraint(
            "length(btrim(order_ref)) > 0",
            name=op.f("ck_cases_order_ref_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(product_ref)) > 0",
            name=op.f("ck_cases_product_ref_nonempty"),
        ),
        sa.CheckConstraint(
            f"requested_action IN ({_sql_values(REQUESTED_ACTIONS)})",
            name=op.f("ck_cases_requested_action_allowed"),
        ),
        sa.CheckConstraint(
            f"status IN ({_sql_values(CASE_STATUSES)})",
            name=op.f("ck_cases_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_cases_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "created_by"),
            ("users.tenant_id", "users.id"),
            name=op.f("fk_cases_tenant_id_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cases")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_cases_tenant_id_id")),
    )
    op.create_index(
        "ix_cases_tenant_created_id",
        "cases",
        ["tenant_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_cases_tenant_order_ref",
        "cases",
        ["tenant_id", "order_ref"],
        unique=False,
    )
    op.create_index(
        "ix_cases_tenant_product_ref",
        "cases",
        ["tenant_id", "product_ref"],
        unique=False,
    )
    op.create_index(
        "ix_cases_tenant_status_created_id",
        "cases",
        ["tenant_id", "status", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "case_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column(
            "evidence_type",
            sa.String(length=32),
            server_default=sa.text("'IMAGE'"),
            nullable=False,
        ),
        sa.Column(
            "upload_status",
            sa.String(length=32),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("storage_bucket", sa.String(length=63), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(content_type)) > 0",
            name=op.f("ck_case_evidence_content_type_nonempty"),
        ),
        sa.CheckConstraint(
            f"evidence_type IN ({_sql_values(EVIDENCE_TYPES)})",
            name=op.f("ck_case_evidence_evidence_type_allowed"),
        ),
        sa.CheckConstraint(
            "evidence_type <> 'IMAGE' OR "
            "(width IS NOT NULL AND height IS NOT NULL AND width > 0 AND height > 0)",
            name=op.f("ck_case_evidence_image_dimensions_positive"),
        ),
        sa.CheckConstraint(
            "length(btrim(object_key)) > 0",
            name=op.f("ck_case_evidence_object_key_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(original_filename)) > 0",
            name=op.f("ck_case_evidence_original_filename_nonempty"),
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_case_evidence_sha256_lower_hex"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name=op.f("ck_case_evidence_size_bytes_positive"),
        ),
        sa.CheckConstraint(
            "length(btrim(storage_bucket)) > 0",
            name=op.f("ck_case_evidence_storage_bucket_nonempty"),
        ),
        sa.CheckConstraint(
            f"upload_status IN ({_sql_values(EVIDENCE_UPLOAD_STATUSES)})",
            name=op.f("ck_case_evidence_upload_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_case_evidence_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name=op.f("fk_case_evidence_tenant_id_case_id_cases"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "created_by"),
            ("users.tenant_id", "users.id"),
            name=op.f("fk_case_evidence_tenant_id_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_evidence")),
        sa.UniqueConstraint(
            "storage_bucket",
            "object_key",
            name=op.f("uq_case_evidence_storage_bucket_object_key"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_case_evidence_tenant_id_id"),
        ),
    )
    op.create_index(
        "ix_case_evidence_case_sha256",
        "case_evidence",
        ["case_id", "sha256"],
        unique=False,
    )
    op.create_index(
        "ix_case_evidence_tenant_case_created_id",
        "case_evidence",
        ["tenant_id", "case_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "case_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=64), nullable=True),
        sa.Column("to_status", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_sql_values(CASE_STATUSES)})",
            name=op.f("ck_case_status_history_from_status_allowed"),
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) > 0",
            name=op.f("ck_case_status_history_reason_nonempty"),
        ),
        sa.CheckConstraint(
            f"to_status IN ({_sql_values(CASE_STATUSES)})",
            name=op.f("ck_case_status_history_to_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_case_status_history_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name=op.f("fk_case_status_history_tenant_id_case_id_cases"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "actor_id"),
            ("users.tenant_id", "users.id"),
            name=op.f("fk_case_status_history_tenant_id_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_status_history")),
    )
    op.create_index(
        "ix_case_status_history_tenant_case_occurred_id",
        "case_status_history",
        ["tenant_id", "case_id", "occurred_at", "id"],
        unique=False,
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_idempotency_records_expires_after_created"),
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name=op.f("ck_idempotency_records_idempotency_key_nonempty"),
        ),
        sa.CheckConstraint(
            f"operation IN ({_sql_values(IDEMPOTENCY_OPERATIONS)})",
            name=op.f("ck_idempotency_records_operation_allowed"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_idempotency_records_request_hash_lower_hex"),
        ),
        sa.CheckConstraint(
            f"resource_type IN ({_sql_values(IDEMPOTENCY_RESOURCE_TYPES)})",
            name=op.f("ck_idempotency_records_resource_type_allowed"),
        ),
        sa.CheckConstraint(
            "response_status BETWEEN 100 AND 599",
            name=op.f("ck_idempotency_records_response_status_http_range"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_idempotency_records_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "resource_id"),
            ("cases.tenant_id", "cases.id"),
            name=op.f("fk_idempotency_records_tenant_id_resource_id_cases"),
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_records")),
        sa.UniqueConstraint(
            "tenant_id",
            "operation",
            "idempotency_key",
            name=op.f("uq_idempotency_records_tenant_operation_key"),
        ),
    )
    op.create_index(
        "ix_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")

    op.drop_index(
        "ix_case_status_history_tenant_case_occurred_id",
        table_name="case_status_history",
    )
    op.drop_table("case_status_history")

    op.drop_index(
        "ix_case_evidence_tenant_case_created_id",
        table_name="case_evidence",
    )
    op.drop_index("ix_case_evidence_case_sha256", table_name="case_evidence")
    op.drop_table("case_evidence")

    op.drop_index("ix_cases_tenant_status_created_id", table_name="cases")
    op.drop_index("ix_cases_tenant_product_ref", table_name="cases")
    op.drop_index("ix_cases_tenant_order_ref", table_name="cases")
    op.drop_index("ix_cases_tenant_created_id", table_name="cases")
    op.drop_table("cases")

    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("tenants")
