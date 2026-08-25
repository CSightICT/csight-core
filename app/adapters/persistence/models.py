"""SQLAlchemy mappings for the Sprint 1 identity, Case, and Evidence schema.

ORM objects stay inside the persistence adapter.  Repositories are responsible
for translating them to and from framework-independent domain entities.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.adapters.persistence.base import Base

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


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenantModel(TimestampMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("length(btrim(slug)) > 0", name="slug_nonempty"),
        CheckConstraint("slug = lower(slug)", name="slug_lowercase"),
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        UniqueConstraint("slug", name="uq_tenants_slug"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_users_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(btrim(email)) > 0", name="email_nonempty"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("length(btrim(password_hash)) > 0", name="password_hash_nonempty"),
        CheckConstraint("length(btrim(display_name)) > 0", name="display_name_nonempty"),
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )


class RoleModel(Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(
            f"name IN ({_sql_values(ROLE_NAMES)})",
            name="name_allowed",
        ),
        UniqueConstraint("name", name="uq_roles_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)


class UserRoleModel(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_user_roles_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_user_roles_tenant_id_user_id_users",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("role_id",),
            ("roles.id",),
            name="fk_user_roles_role_id_roles",
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)


class CaseModel(TimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_cases_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "created_by"),
            ("users.tenant_id", "users.id"),
            name="fk_cases_tenant_id_created_by_users",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"domain_type IN ({_sql_values(DOMAIN_TYPES)})",
            name="domain_type_allowed",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(CASE_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint(
            f"requested_action IN ({_sql_values(REQUESTED_ACTIONS)})",
            name="requested_action_allowed",
        ),
        CheckConstraint("length(btrim(order_ref)) > 0", name="order_ref_nonempty"),
        CheckConstraint("length(btrim(product_ref)) > 0", name="product_ref_nonempty"),
        CheckConstraint(
            "length(btrim(customer_message)) > 0",
            name="customer_message_nonempty",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_cases_tenant_id_id"),
        Index("ix_cases_tenant_created_id", "tenant_id", "created_at", "id"),
        Index(
            "ix_cases_tenant_status_created_id",
            "tenant_id",
            "status",
            "created_at",
            "id",
        ),
        Index("ix_cases_tenant_product_ref", "tenant_id", "product_ref"),
        Index("ix_cases_tenant_order_ref", "tenant_id", "order_ref"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    domain_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'product_defect_cs'"),
    )
    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'RECEIVED'"),
    )
    order_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    product_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_message: Mapped[str] = mapped_column(Text, nullable=False)
    requested_action: Mapped[str] = mapped_column(String(32), nullable=False)
    attributes: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class CaseEvidenceModel(TimestampMixin, Base):
    __tablename__ = "case_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_case_evidence_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_case_evidence_tenant_id_case_id_cases",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "created_by"),
            ("users.tenant_id", "users.id"),
            name="fk_case_evidence_tenant_id_created_by_users",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"evidence_type IN ({_sql_values(EVIDENCE_TYPES)})",
            name="evidence_type_allowed",
        ),
        CheckConstraint(
            f"upload_status IN ({_sql_values(EVIDENCE_UPLOAD_STATUSES)})",
            name="upload_status_allowed",
        ),
        CheckConstraint("length(btrim(storage_bucket)) > 0", name="storage_bucket_nonempty"),
        CheckConstraint("length(btrim(object_key)) > 0", name="object_key_nonempty"),
        CheckConstraint(
            "length(btrim(original_filename)) > 0",
            name="original_filename_nonempty",
        ),
        CheckConstraint("length(btrim(content_type)) > 0", name="content_type_nonempty"),
        CheckConstraint("size_bytes > 0", name="size_bytes_positive"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_lower_hex"),
        CheckConstraint(
            "evidence_type <> 'IMAGE' OR "
            "(width IS NOT NULL AND height IS NOT NULL AND width > 0 AND height > 0)",
            name="image_dimensions_positive",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_case_evidence_tenant_id_id"),
        UniqueConstraint(
            "storage_bucket",
            "object_key",
            name="uq_case_evidence_storage_bucket_object_key",
        ),
        Index(
            "ix_case_evidence_tenant_case_created_id",
            "tenant_id",
            "case_id",
            "created_at",
            "id",
        ),
        Index("ix_case_evidence_case_sha256", "case_id", "sha256"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'IMAGE'"),
    )
    upload_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'PENDING'"),
    )
    storage_bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class CaseStatusHistoryModel(Base):
    __tablename__ = "case_status_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_case_status_history_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_case_status_history_tenant_id_case_id_cases",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "actor_id"),
            ("users.tenant_id", "users.id"),
            name="fk_case_status_history_tenant_id_actor_id_users",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_sql_values(CASE_STATUSES)})",
            name="from_status_allowed",
        ),
        CheckConstraint(
            f"to_status IN ({_sql_values(CASE_STATUSES)})",
            name="to_status_allowed",
        ),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_nonempty"),
        Index(
            "ix_case_status_history_tenant_case_occurred_id",
            "tenant_id",
            "case_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_status: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdempotencyRecordModel(CreatedAtMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_idempotency_records_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "resource_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_idempotency_records_tenant_id_resource_id_cases",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            f"operation IN ({_sql_values(IDEMPOTENCY_OPERATIONS)})",
            name="operation_allowed",
        ),
        CheckConstraint(
            f"resource_type IN ({_sql_values(IDEMPOTENCY_RESOURCE_TYPES)})",
            name="resource_type_allowed",
        ),
        CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name="idempotency_key_nonempty",
        ),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_lower_hex"),
        CheckConstraint(
            "response_status BETWEEN 100 AND 599",
            name="response_status_http_range",
        ),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        UniqueConstraint(
            "tenant_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_tenant_operation_key",
        ),
        Index("ix_idempotency_records_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


PERSISTENCE_MODELS = (
    TenantModel,
    UserModel,
    RoleModel,
    UserRoleModel,
    CaseModel,
    CaseEvidenceModel,
    CaseStatusHistoryModel,
    IdempotencyRecordModel,
)
