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
ANALYSIS_PIPELINES = (
    "product_defect_text_extraction",
    "product_defect_multimodal_analysis",
)
ANALYSIS_PIPELINE_VERSIONS = ("1.0.0",)
ANALYSIS_TRIGGERS = ("USER_REQUEST",)
ANALYSIS_RUN_STATUSES = (
    "QUEUED",
    "RUNNING",
    "RETRY_WAITING",
    "PARTIAL_SUCCESS",
    "SUCCEEDED",
    "FAILED",
)
ANALYSIS_STAGE_TYPES = (
    "TEXT_EXTRACTION",
    "VISION_ANALYSIS",
    "EVIDENCE_ALIGNMENT",
    "POLICY_EVALUATION",
    "ROUTING",
    "REPORT_GENERATION",
)
ANALYSIS_STAGE_STATUSES = ("QUEUED", "RUNNING", "RETRY_WAITING", "SUCCEEDED", "FAILED")
ANALYSIS_ATTEMPT_STATUSES = (
    "RUNNING",
    "RETRY_WAITING",
    "SUCCEEDED",
    "FAILED",
    "ABANDONED",
)
EXTRACTED_REQUESTED_ACTIONS = (
    "REFUND",
    "EXCHANGE",
    "RESHIPMENT",
    "REPAIR",
    "INFORMATION",
    "OTHER",
    "UNKNOWN",
)
OUTBOX_STATUSES = ("PENDING", "PROCESSING", "PUBLISHED", "FAILED")
ANALYSIS_IDEMPOTENCY_OPERATIONS = ("analysis.create.v1",)
VISION_CANONICAL_LABELS = (
    "LEAKAGE",
    "CONTAINER_DAMAGE",
    "DENT",
    "CRACK",
    "SCRATCH",
    "DISCOLORATION",
    "MISSING_PART",
    "BREAKAGE",
    "MISSING_COMPONENT",
    "FUNCTIONAL_FAILURE",
    "PACKAGING_DAMAGE",
    "CONTAMINATION",
    "SURFACE_DAMAGE",
    "OTHER",
    "UNKNOWN",
)


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


class AnalysisRunModel(TimestampMixin, Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_analysis_runs_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_analysis_runs_tenant_id_case_id_cases",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "requested_by"),
            ("users.tenant_id", "users.id"),
            name="fk_analysis_runs_tenant_id_requested_by_users",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"pipeline_name IN ({_sql_values(ANALYSIS_PIPELINES)})",
            name="pipeline_name_allowed",
        ),
        CheckConstraint(
            f"pipeline_version IN ({_sql_values(ANALYSIS_PIPELINE_VERSIONS)})",
            name="pipeline_version_allowed",
        ),
        CheckConstraint(
            f"trigger_type IN ({_sql_values(ANALYSIS_TRIGGERS)})",
            name="trigger_type_allowed",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(ANALYSIS_RUN_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint("length(btrim(correlation_id)) > 0", name="correlation_id_nonempty"),
        CheckConstraint("length(btrim(idempotency_key)) > 0", name="idempotency_key_nonempty"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_lower_hex"),
        CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status IN ('RUNNING', 'RETRY_WAITING') AND started_at IS NOT NULL "
            "AND completed_at IS NULL) OR "
            "(status IN ('PARTIAL_SUCCESS', 'SUCCEEDED', 'FAILED') AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="status_timestamps_consistent",
        ),
        CheckConstraint(
            "(status = 'FAILED' AND failure_code IS NOT NULL) OR (status <> 'FAILED')",
            name="failed_has_code",
        ),
        CheckConstraint(
            "status <> 'SUCCEEDED' OR (failure_code IS NULL AND failure_message IS NULL)",
            name="succeeded_has_no_failure",
        ),
        CheckConstraint(
            "(failure_code IS NULL AND failure_message IS NULL AND failure_retryable IS NULL) OR "
            "(failure_code IS NOT NULL AND failure_message IS NOT NULL "
            "AND failure_retryable IS NOT NULL)",
            name="failure_fields_consistent",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_analysis_runs_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_analysis_runs_tenant_idempotency_key",
        ),
        Index(
            "ix_analysis_runs_tenant_case_created_id",
            "tenant_id",
            "case_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_analysis_runs_tenant_case_status_created_id",
            "tenant_id",
            "case_id",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_analysis_runs_tenant_case_pipeline_created_id",
            "tenant_id",
            "case_id",
            "pipeline_name",
            "pipeline_version",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    pipeline_name: Mapped[str] = mapped_column(String(128), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    failure_retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class AnalysisStageRunModel(TimestampMixin, Base):
    __tablename__ = "analysis_stage_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_analysis_stage_runs_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_analysis_stage_runs_tenant_id_analysis_run_id_analysis_runs",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"stage_type IN ({_sql_values(ANALYSIS_STAGE_TYPES)})",
            name="stage_type_allowed",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(ANALYSIS_STAGE_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "input_token_count IS NULL OR input_token_count >= 0",
            name="input_token_count_nonnegative",
        ),
        CheckConstraint(
            "output_token_count IS NULL OR output_token_count >= 0",
            name="output_token_count_nonnegative",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_ms_nonnegative"),
        CheckConstraint(
            "(latency_ms IS NULL AND execution_provider_name IS NULL "
            "AND execution_model_name IS NULL AND execution_model_version IS NULL "
            "AND execution_model_revision IS NULL AND provider_request_id IS NULL "
            "AND input_token_count IS NULL AND output_token_count IS NULL) OR "
            "(latency_ms IS NOT NULL AND execution_provider_name IS NOT NULL "
            "AND execution_model_name IS NOT NULL AND execution_model_version IS NOT NULL)",
            name="provider_execution_consistent",
        ),
        CheckConstraint(
            "(status = 'RUNNING' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'RUNNING' AND claim_token IS NULL AND lease_expires_at IS NULL)",
            name="running_claim_consistent",
        ),
        CheckConstraint(
            "(status = 'RETRY_WAITING' AND next_attempt_at IS NOT NULL) OR "
            "(status <> 'RETRY_WAITING' AND next_attempt_at IS NULL)",
            name="retry_schedule_consistent",
        ),
        CheckConstraint(
            "(status = 'QUEUED' AND attempt_count = 0 AND started_at IS NULL "
            "AND completed_at IS NULL) OR "
            "(status IN ('RUNNING', 'RETRY_WAITING') AND attempt_count > 0 "
            "AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status = 'SUCCEEDED' AND attempt_count > 0 AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'FAILED' AND attempt_count >= 0 AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="status_timestamps_consistent",
        ),
        CheckConstraint(
            "(status = 'FAILED' AND failure_code IS NOT NULL) OR status <> 'FAILED'",
            name="failed_has_code",
        ),
        CheckConstraint(
            "status <> 'SUCCEEDED' OR (failure_code IS NULL AND failure_message IS NULL)",
            name="succeeded_has_no_failure",
        ),
        CheckConstraint(
            "(failure_code IS NULL AND failure_message IS NULL AND failure_retryable IS NULL) OR "
            "(failure_code IS NOT NULL AND failure_message IS NOT NULL "
            "AND failure_retryable IS NOT NULL)",
            name="failure_fields_consistent",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_analysis_stage_runs_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "id",
            name="uq_analysis_stage_runs_tenant_analysis_run_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "stage_type",
            name="uq_analysis_stage_runs_tenant_run_stage_type",
        ),
        UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "id",
            "stage_type",
            name="uq_analysis_stage_runs_tenant_run_id_stage_type",
        ),
        Index(
            "ix_analysis_stage_runs_tenant_run_created_id",
            "tenant_id",
            "analysis_run_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_analysis_stage_runs_running_lease",
            "lease_expires_at",
            "id",
            postgresql_where=text("status = 'RUNNING'"),
        ),
        Index(
            "ix_analysis_stage_runs_retry_schedule",
            "next_attempt_at",
            "id",
            postgresql_where=text("status = 'RETRY_WAITING'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    stage_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_provider_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    execution_model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_model_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempt_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    failure_retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class AnalysisStageAttemptModel(CreatedAtMixin, Base):
    __tablename__ = "analysis_stage_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_analysis_stage_attempts_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id", "stage_run_id"),
            (
                "analysis_stage_runs.tenant_id",
                "analysis_stage_runs.analysis_run_id",
                "analysis_stage_runs.id",
            ),
            name="fk_analysis_stage_attempts_tenant_run_stage_analysis_stage_runs",
            ondelete="RESTRICT",
        ),
        CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        CheckConstraint(
            f"status IN ({_sql_values(ANALYSIS_ATTEMPT_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint(
            "input_token_count IS NULL OR input_token_count >= 0",
            name="input_token_count_nonnegative",
        ),
        CheckConstraint(
            "output_token_count IS NULL OR output_token_count >= 0",
            name="output_token_count_nonnegative",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_ms_nonnegative"),
        CheckConstraint(
            "(latency_ms IS NULL AND execution_provider_name IS NULL "
            "AND execution_model_name IS NULL AND execution_model_version IS NULL "
            "AND execution_model_revision IS NULL AND provider_request_id IS NULL "
            "AND input_token_count IS NULL AND output_token_count IS NULL) OR "
            "(latency_ms IS NOT NULL AND execution_provider_name IS NOT NULL "
            "AND execution_model_name IS NOT NULL AND execution_model_version IS NOT NULL)",
            name="provider_execution_consistent",
        ),
        CheckConstraint(
            "(status = 'RUNNING' AND completed_at IS NULL) OR "
            "(status <> 'RUNNING' AND completed_at IS NOT NULL)",
            name="completion_consistent",
        ),
        CheckConstraint(
            "status NOT IN ('FAILED', 'RETRY_WAITING', 'ABANDONED') OR failure_code IS NOT NULL",
            name="failure_outcome_has_code",
        ),
        CheckConstraint(
            "(failure_code IS NULL AND failure_message IS NULL AND failure_retryable IS NULL) OR "
            "(failure_code IS NOT NULL AND failure_message IS NOT NULL "
            "AND failure_retryable IS NOT NULL)",
            name="failure_fields_consistent",
        ),
        UniqueConstraint("execution_token", name="uq_analysis_stage_attempts_execution_token"),
        UniqueConstraint(
            "tenant_id",
            "stage_run_id",
            "attempt_number",
            name="uq_analysis_stage_attempts_tenant_stage_attempt_number",
        ),
        Index(
            "ix_analysis_stage_attempts_tenant_stage_attempt",
            "tenant_id",
            "stage_run_id",
            "attempt_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    stage_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_token: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_provider_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    execution_model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_model_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    failure_retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class LLMExtractionResultModel(CreatedAtMixin, Base):
    __tablename__ = "llm_extraction_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_llm_extraction_results_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_llm_extraction_results_tenant_run_analysis_runs",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id", "stage_run_id", "stage_type"),
            (
                "analysis_stage_runs.tenant_id",
                "analysis_stage_runs.analysis_run_id",
                "analysis_stage_runs.id",
                "analysis_stage_runs.stage_type",
            ),
            name="fk_llm_results_tenant_run_stage_type_stage_runs",
            ondelete="RESTRICT",
        ),
        CheckConstraint("stage_type = 'TEXT_EXTRACTION'", name="stage_type_text_extraction"),
        CheckConstraint("length(btrim(schema_version)) > 0", name="schema_version_nonempty"),
        CheckConstraint("length(btrim(language)) > 0", name="language_nonempty"),
        CheckConstraint("jsonb_typeof(issue_types) = 'array'", name="issue_types_array"),
        CheckConstraint("jsonb_array_length(issue_types) > 0", name="issue_types_nonempty"),
        CheckConstraint("jsonb_typeof(claims) = 'array'", name="claims_array"),
        CheckConstraint(
            "jsonb_typeof(missing_information) = 'array'",
            name="missing_information_array",
        ),
        CheckConstraint(
            f"requested_action IN ({_sql_values(EXTRACTED_REQUESTED_ACTIONS)})",
            name="requested_action_allowed",
        ),
        CheckConstraint("length(btrim(summary)) > 0", name="summary_nonempty"),
        CheckConstraint("length(summary) <= 4000", name="summary_max_length"),
        UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            name="uq_llm_extraction_results_tenant_analysis_run",
        ),
        UniqueConstraint(
            "tenant_id",
            "stage_run_id",
            name="uq_llm_extraction_results_tenant_stage_run",
        ),
        Index(
            "ix_llm_extraction_results_tenant_run",
            "tenant_id",
            "analysis_run_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    stage_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    stage_type: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'TEXT_EXTRACTION'")
    )
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(35), nullable=False)
    issue_types: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    claims: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    requested_action: Mapped[str] = mapped_column(String(32), nullable=False)
    missing_information: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)


class AnalysisRunEvidenceModel(CreatedAtMixin, Base):
    __tablename__ = "analysis_run_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_analysis_run_evidence_tenant_run_analysis_runs",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "evidence_id"),
            ("case_evidence.tenant_id", "case_evidence.id"),
            name="fk_analysis_run_evidence_tenant_evidence_case_evidence",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_lower_hex"),
        UniqueConstraint(
            "tenant_id", "analysis_run_id", "evidence_id", name="uq_analysis_run_evidence_item"
        ),
        UniqueConstraint(
            "tenant_id", "analysis_run_id", "position", name="uq_analysis_run_evidence_position"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_analysis_run_evidence_tenant_id_id"),
        Index(
            "ix_analysis_run_evidence_tenant_run_position",
            "tenant_id",
            "analysis_run_id",
            "position",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class VisionAnalysisResultModel(CreatedAtMixin, Base):
    __tablename__ = "vision_analysis_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_vision_results_tenant_run_analysis_runs",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id", "stage_run_id", "stage_type"),
            (
                "analysis_stage_runs.tenant_id",
                "analysis_stage_runs.analysis_run_id",
                "analysis_stage_runs.id",
                "analysis_stage_runs.stage_type",
            ),
            name="fk_vision_results_tenant_run_stage_type_stage_runs",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "evidence_id"),
            ("case_evidence.tenant_id", "case_evidence.id"),
            name="fk_vision_results_tenant_evidence_case_evidence",
            ondelete="RESTRICT",
        ),
        CheckConstraint("stage_type = 'VISION_ANALYSIS'", name="stage_type_vision_analysis"),
        CheckConstraint("image_width > 0 AND image_height > 0", name="image_dimensions_positive"),
        CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        CheckConstraint("jsonb_typeof(image_quality) = 'object'", name="image_quality_object"),
        UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "evidence_id",
            name="uq_vision_results_tenant_run_evidence",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_vision_results_tenant_id_id"),
        Index(
            "ix_vision_results_tenant_run_created",
            "tenant_id",
            "analysis_run_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    stage_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    stage_type: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'VISION_ANALYSIS'")
    )
    evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dataset_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    threshold_version: Mapped[str] = mapped_column(String(100), nullable=False)
    preprocess_version: Mapped[str] = mapped_column(String(100), nullable=False)
    postprocess_version: Mapped[str] = mapped_column(String(100), nullable=False)
    framework: Mapped[str | None] = mapped_column(String(100), nullable=True)
    runtime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    precision: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    image_quality: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class VisionDetectionModel(CreatedAtMixin, Base):
    __tablename__ = "vision_detections"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "vision_result_id"),
            ("vision_analysis_results.tenant_id", "vision_analysis_results.id"),
            name="fk_vision_detections_tenant_result_vision_results",
            ondelete="RESTRICT",
        ),
        CheckConstraint("detection_index >= 0", name="detection_index_nonnegative"),
        CheckConstraint(
            f"canonical_label IN ({_sql_values(VISION_CANONICAL_LABELS)})",
            name="canonical_label_allowed",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint("geometry_type = 'BOUNDING_BOX'", name="geometry_type_bbox"),
        CheckConstraint(
            "coordinate_system = 'normalized_xyxy'",
            name="coordinate_system_normalized",
        ),
        CheckConstraint("x1 >= 0 AND x1 < x2 AND x2 <= 1", name="x_coordinates_ordered"),
        CheckConstraint("y1 >= 0 AND y1 < y2 AND y2 <= 1", name="y_coordinates_ordered"),
        UniqueConstraint(
            "tenant_id", "vision_result_id", "detection_index", name="uq_vision_detection_index"
        ),
        Index(
            "ix_vision_detections_tenant_result_index",
            "tenant_id",
            "vision_result_id",
            "detection_index",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    vision_result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    detection_index: Mapped[int] = mapped_column(Integer, nullable=False)
    detection_id: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical_label: Mapped[str] = mapped_column(String(64), nullable=False)
    model_class_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_class_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    coordinate_system: Mapped[str] = mapped_column(String(32), nullable=False)
    x1: Mapped[float] = mapped_column(nullable=False)
    y1: Mapped[float] = mapped_column(nullable=False)
    x2: Mapped[float] = mapped_column(nullable=False)
    y2: Mapped[float] = mapped_column(nullable=False)


class AnalysisRequestIdempotencyRecordModel(CreatedAtMixin, Base):
    __tablename__ = "analysis_request_idempotency_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_analysis_request_idempotency_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_analysis_request_idempotency_tenant_case_cases",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_analysis_request_idempotency_tenant_run_analysis_runs",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            f"operation IN ({_sql_values(ANALYSIS_IDEMPOTENCY_OPERATIONS)})",
            name="operation_allowed",
        ),
        CheckConstraint("length(btrim(idempotency_key)) > 0", name="key_nonempty"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_lower_hex"),
        CheckConstraint("response_status = 202", name="response_accepted"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        UniqueConstraint(
            "tenant_id",
            "operation",
            "idempotency_key",
            name="uq_analysis_request_idempotency_tenant_operation_key",
        ),
        Index("ix_analysis_request_idempotency_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxEventModel(TimestampMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_outbox_events_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "aggregate_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_outbox_events_tenant_aggregate_analysis_runs",
            ondelete="RESTRICT",
        ),
        CheckConstraint("aggregate_type = 'analysis_run'", name="aggregate_type_analysis_run"),
        CheckConstraint("event_type = 'analysis.requested.v1'", name="event_type_allowed"),
        CheckConstraint("event_version = '1.0'", name="event_version_allowed"),
        CheckConstraint(
            f"status IN ({_sql_values(OUTBOX_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_object"),
        CheckConstraint(
            "payload ?& ARRAY['event_id','event_type','event_version','tenant_id','case_id',"
            "'analysis_run_id','stage_run_id','correlation_id','occurred_at']",
            name="payload_required_keys",
        ),
        CheckConstraint(
            "(payload - ARRAY['event_id','event_type','event_version','tenant_id','case_id',"
            "'analysis_run_id','stage_run_id','correlation_id','occurred_at']) = '{}'::jsonb",
            name="payload_allowed_keys",
        ),
        CheckConstraint(
            "payload->>'event_id' = id::text AND payload->>'event_type' = event_type AND "
            "payload->>'event_version' = event_version AND "
            "payload->>'tenant_id' = tenant_id::text AND "
            "payload->>'analysis_run_id' = aggregate_id::text",
            name="payload_identity_consistent",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND claimed_at IS NULL AND claim_token IS NULL "
            "AND claimed_by IS NULL AND published_at IS NULL) OR "
            "(status = 'PROCESSING' AND claimed_at IS NOT NULL AND claim_token IS NOT NULL "
            "AND claimed_by IS NOT NULL AND published_at IS NULL AND attempt_count > 0) OR "
            "(status = 'PUBLISHED' AND claimed_at IS NULL AND claim_token IS NULL "
            "AND claimed_by IS NULL AND published_at IS NOT NULL AND attempt_count > 0) OR "
            "(status = 'FAILED' AND claimed_at IS NULL AND claim_token IS NULL "
            "AND claimed_by IS NULL AND published_at IS NULL AND attempt_count > 0 "
            "AND last_error IS NOT NULL)",
            name="status_claim_timestamps_consistent",
        ),
        Index(
            "ix_outbox_events_pending_dispatch",
            "available_at",
            "created_at",
            "id",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_outbox_events_processing_claimed",
            "claimed_at",
            "id",
            postgresql_where=text("status = 'PROCESSING'"),
        ),
        Index(
            "ix_outbox_events_tenant_aggregate_created_id",
            "tenant_id",
            "aggregate_type",
            "aggregate_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)


PERSISTENCE_MODELS = (
    TenantModel,
    UserModel,
    RoleModel,
    UserRoleModel,
    CaseModel,
    CaseEvidenceModel,
    CaseStatusHistoryModel,
    IdempotencyRecordModel,
    AnalysisRunModel,
    AnalysisStageRunModel,
    AnalysisStageAttemptModel,
    LLMExtractionResultModel,
    AnalysisRunEvidenceModel,
    VisionAnalysisResultModel,
    VisionDetectionModel,
    AnalysisRequestIdempotencyRecordModel,
    OutboxEventModel,
)
