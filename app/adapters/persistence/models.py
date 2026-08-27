"""SQLAlchemy mappings for the Sprint 1 identity, Case, and Evidence schema.

ORM objects stay inside the persistence adapter.  Repositories are responsible
for translating them to and from framework-independent domain entities.
"""

from datetime import date, datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
ANALYSIS_PIPELINE_VERSIONS = ("1.0.0", "2.0.0")
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
RELIABLE_ASYNC_OUTBOX_STATUSES = (
    "PENDING",
    "PROCESSING",
    "PUBLISHED",
    "CONSUMED",
    "FAILED",
)
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
POLICY_DOCUMENT_STATUSES = ("ACTIVE", "RETIRED")
POLICY_CLAUSE_TYPES = (
    "RULE",
    "EXCEPTION",
    "EVIDENCE_REQUIREMENT",
    "ESCALATION",
    "DEFINITION",
    "PROCEDURE",
)
POLICY_INGESTION_STATUSES = ("PENDING", "RUNNING", "SUCCEEDED", "FAILED")
POLICY_INDEX_STATUSES = ("BUILDING", "ACTIVE", "FAILED", "RETIRED")
POLICY_EXECUTION_PROFILE_STATUSES = ("ACTIVE", "RETIRED")
POLICY_QUERY_STRATEGIES = ("RAW", "DETERMINISTIC", "LLM")
POLICY_RETRIEVAL_RUN_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED")
GROUNDED_EXPLANATION_RUN_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED")
POLICY_EVALUATION_RUN_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED")
HUMAN_REVIEW_TASK_TYPES = (
    "STANDARD_REVIEW",
    "EVIDENCE_REVIEW",
    "MANAGER_REVIEW",
    "POLICY_EXCEPTION_REVIEW",
    "SAFETY_REVIEW",
)
HUMAN_REVIEW_PRIORITIES = ("LOW", "NORMAL", "HIGH", "CRITICAL")
HUMAN_REVIEW_STATUSES = (
    "PENDING",
    "CLAIMED",
    "WAITING_FOR_EVIDENCE",
    "ESCALATED",
    "RESOLVED",
)
HUMAN_REVIEW_ACTIONS = (
    "CREATED",
    "CLAIMED",
    "RELEASED",
    "EVIDENCE_REQUESTED",
    "RESUMED",
    "ESCALATED",
    "RESOLVED",
)
HUMAN_DECISION_TYPES = (
    "APPROVE_REFUND",
    "APPROVE_EXCHANGE",
    "APPROVE_RESHIPMENT",
    "APPROVE_REPAIR",
    "REJECT_REQUEST",
    "PROVIDE_INFORMATION",
    "NO_ACTION",
)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


RELIABLE_ASYNC_OUTBOX_STATE_CONSISTENCY = (
    "(status = 'PENDING' AND claimed_at IS NULL AND claim_token IS NULL "
    "AND claimed_by IS NULL AND published_at IS NULL AND consumed_at IS NULL "
    "AND failed_at IS NULL) OR "
    "(status = 'PROCESSING' AND claimed_at IS NOT NULL AND claim_token IS NOT NULL "
    "AND claimed_by IS NOT NULL AND published_at IS NULL AND consumed_at IS NULL "
    "AND failed_at IS NULL AND attempt_count > 0) OR "
    "(status = 'PUBLISHED' AND claimed_at IS NULL AND claim_token IS NULL "
    "AND claimed_by IS NULL AND published_at IS NOT NULL AND consumed_at IS NULL "
    "AND failed_at IS NULL AND attempt_count > 0) OR "
    "(status = 'CONSUMED' AND claimed_at IS NULL AND claim_token IS NULL "
    "AND claimed_by IS NULL AND published_at IS NOT NULL AND consumed_at IS NOT NULL "
    "AND failed_at IS NULL AND attempt_count > 0 AND consumer_attempt_count > 0) OR "
    "(status = 'FAILED' AND claimed_at IS NULL AND claim_token IS NULL "
    "AND claimed_by IS NULL AND consumed_at IS NULL AND failed_at IS NOT NULL "
    "AND failure_code IS NOT NULL AND attempt_count > 0 "
    "AND (last_error IS NOT NULL OR consumer_last_error IS NOT NULL))"
)


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


class ReliableAsyncOutboxMixin:
    """Shared delivery and consumer audit fields for identifier-only outboxes."""

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumer_attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    consumer_last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class LLMExtractionResultV2Model(CreatedAtMixin, Base):
    __tablename__ = "llm_extraction_results_v2"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_llm_results_v2_tenant_run_analysis_runs",
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
            name="fk_llm_results_v2_tenant_run_stage_type_stage_runs",
            ondelete="RESTRICT",
        ),
        CheckConstraint("stage_type = 'TEXT_EXTRACTION'", name="stage_type_text_extraction"),
        CheckConstraint("schema_version = '2.0'", name="schema_version_v2"),
        CheckConstraint("jsonb_typeof(issue_types) = 'array'", name="issue_types_array"),
        CheckConstraint("jsonb_typeof(claims) = 'array'", name="claims_array"),
        CheckConstraint("jsonb_typeof(requested_actions) = 'array'", name="actions_array"),
        CheckConstraint("jsonb_typeof(text_ambiguities) = 'array'", name="ambiguities_array"),
        CheckConstraint("jsonb_typeof(system_missing_information) = 'array'", name="missing_array"),
        CheckConstraint("completeness_rule_version = '1.0.0'", name="rule_version_v1"),
        CheckConstraint(
            "action_consistency IN ('MATCH','MISMATCH','ONLY_DECLARED','ONLY_EXTRACTED',"
            "'BOTH_UNSPECIFIED','MULTIPLE_EXTRACTED','NOT_COMPARABLE')",
            name="action_consistency_allowed",
        ),
        CheckConstraint("length(btrim(summary)) > 0", name="summary_nonempty"),
        UniqueConstraint("tenant_id", "analysis_run_id", name="uq_llm_results_v2_tenant_run"),
        UniqueConstraint("tenant_id", "stage_run_id", name="uq_llm_results_v2_tenant_stage"),
        UniqueConstraint("tenant_id", "id", name="uq_llm_results_v2_tenant_id"),
        Index("ix_llm_results_v2_tenant_run", "tenant_id", "analysis_run_id"),
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
    requested_actions: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    text_ambiguities: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    system_missing_information: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    action_consistency: Mapped[str] = mapped_column(String(64), nullable=False)
    completeness_rule_version: Mapped[str] = mapped_column(String(32), nullable=False)


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


class PolicyIngestionRunModel(TimestampMixin, Base):
    __tablename__ = "policy_ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(POLICY_INGESTION_STATUSES)})", name="status_allowed"
        ),
        CheckConstraint("expected_document_count >= 0", name="expected_documents_nonnegative"),
        CheckConstraint("ingested_document_count >= 0", name="ingested_documents_nonnegative"),
        CheckConstraint("expected_clause_count >= 0", name="expected_clauses_nonnegative"),
        CheckConstraint("ingested_clause_count >= 0", name="ingested_clauses_nonnegative"),
        Index(
            "uq_policy_ingestion_runs_succeeded_identity",
            "corpus_source_hash",
            "manifest_hash",
            "builder_version",
            unique=True,
            postgresql_where=text("status = 'SUCCEEDED'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    corpus_name: Mapped[str] = mapped_column(String(255), nullable=False)
    corpus_version: Mapped[str] = mapped_column(String(64), nullable=False)
    corpus_source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ingested_document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_clause_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ingested_clause_count: Mapped[int] = mapped_column(Integer, nullable=False)
    builder_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class PolicyDocumentModel(CreatedAtMixin, Base):
    __tablename__ = "policy_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",), ("tenants.id",), name="fk_policy_documents_tenant", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ("ingestion_run_id",),
            ("policy_ingestion_runs.id",),
            name="fk_policy_documents_ingestion_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"document_status IN ({_sql_values(POLICY_DOCUMENT_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="dates_valid"
        ),
        UniqueConstraint(
            "tenant_id", "document_id", "document_version", name="uq_policy_documents_version"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_policy_documents_tenant_id"),
        Index(
            "ix_policy_documents_tenant_effective_status",
            "tenant_id",
            "document_status",
            "effective_from",
            "effective_to",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(128), nullable=False)
    authority_level: Mapped[str] = mapped_column(String(128), nullable=False)
    product_categories: Mapped[list[str]] = mapped_column(ARRAY(String(128)), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supersedes_document_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    superseded_by_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    superseded_by_document_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingestion_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class PolicyClauseModel(CreatedAtMixin, Base):
    __tablename__ = "policy_clauses"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",), ("tenants.id",), name="fk_policy_clauses_tenant", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ("tenant_id", "document_row_id"),
            ("policy_documents.tenant_id", "policy_documents.id"),
            name="fk_policy_clauses_tenant_document",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("ingestion_run_id",),
            ("policy_ingestion_runs.id",),
            name="fk_policy_clauses_ingestion_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"clause_type IN ({_sql_values(POLICY_CLAUSE_TYPES)})", name="type_allowed"
        ),
        CheckConstraint(
            f"document_status IN ({_sql_values(POLICY_DOCUMENT_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="dates_valid"
        ),
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "document_version",
            "clause_id",
            name="uq_policy_clauses_version_clause",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_policy_clauses_tenant_id"),
        Index(
            "ix_policy_clauses_tenant_effective_status",
            "tenant_id",
            "document_status",
            "effective_from",
            "effective_to",
        ),
        Index("ix_policy_clauses_tenant_policy_type", "tenant_id", "policy_type"),
        Index("ix_policy_clauses_categories_gin", "product_categories", postgresql_using="gin"),
        Index("ix_policy_clauses_defects_gin", "defect_types", postgresql_using="gin"),
        Index("ix_policy_clauses_actions_gin", "actions", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_row_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    clause_id: Mapped[str] = mapped_column(String(320), nullable=False)
    section_path: Mapped[list[str]] = mapped_column(ARRAY(String(500)), nullable=False)
    clause_type: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    parent_clause_id: Mapped[str | None] = mapped_column(String(320), nullable=True)
    policy_type: Mapped[str] = mapped_column(String(128), nullable=False)
    product_categories: Mapped[list[str]] = mapped_column(ARRAY(String(128)), nullable=False)
    defect_types: Mapped[list[str]] = mapped_column(ARRAY(String(128)), nullable=False)
    actions: Mapped[list[str]] = mapped_column(ARRAY(String(128)), nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingestion_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class PolicyEmbeddingProfileModel(CreatedAtMixin, Base):
    __tablename__ = "policy_embedding_profiles"
    __table_args__ = (
        UniqueConstraint(
            "profile_name", "profile_version", name="uq_policy_embedding_profiles_version"
        ),
        CheckConstraint("embedding_dimension > 0", name="dimension_positive"),
        CheckConstraint("max_query_tokens > 0", name="query_tokens_positive"),
        CheckConstraint("max_document_tokens > 0", name="document_tokens_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_artifact: Mapped[str] = mapped_column(String(255), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    pooling_strategy: Mapped[str] = mapped_column(String(128), nullable=False)
    normalize_embeddings: Mapped[bool] = mapped_column(Boolean, nullable=False)
    query_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    query_instruction_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    document_template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    document_template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    max_query_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    max_document_tokens: Mapped[int] = mapped_column(Integer, nullable=False)


class PolicyClauseEmbeddingModel(CreatedAtMixin, Base):
    __tablename__ = "policy_clause_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "policy_clause_row_id"),
            ("policy_clauses.tenant_id", "policy_clauses.id"),
            name="fk_policy_clause_embeddings_tenant_clause",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("embedding_profile_id",),
            ("policy_embedding_profiles.id",),
            name="fk_policy_clause_embeddings_profile",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "policy_clause_row_id",
            "embedding_profile_id",
            name="uq_policy_clause_embeddings_clause_profile",
        ),
        CheckConstraint("embedding_dimension > 0", name="dimension_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_clause_row_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    embedding_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    document_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyIndexVersionModel(CreatedAtMixin, Base):
    __tablename__ = "policy_index_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_policy_index_versions_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("embedding_profile_id",),
            ("policy_embedding_profiles.id",),
            name="fk_policy_index_versions_profile",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"status IN ({_sql_values(POLICY_INDEX_STATUSES)})", name="status_allowed"),
        CheckConstraint("expected_clause_count >= 0", name="expected_clauses_nonnegative"),
        CheckConstraint("indexed_clause_count >= 0", name="indexed_clauses_nonnegative"),
        UniqueConstraint(
            "tenant_id", "index_name", "index_version", name="uq_policy_index_versions_version"
        ),
        Index(
            "uq_policy_index_versions_one_active",
            "tenant_id",
            "index_name",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    index_name: Mapped[str] = mapped_column(String(128), nullable=False)
    index_version: Mapped[str] = mapped_column(String(64), nullable=False)
    corpus_name: Mapped[str] = mapped_column(String(255), nullable=False)
    corpus_version: Mapped[str] = mapped_column(String(64), nullable=False)
    corpus_source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lexical_profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    lexical_profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    lexical_k1: Mapped[float] = mapped_column(Float, nullable=False)
    lexical_b: Mapped[float] = mapped_column(Float, nullable=False)
    embedding_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fusion_profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    fusion_profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fusion_rrf_k: Mapped[int] = mapped_column(Integer, nullable=False)
    fusion_lexical_weight: Mapped[float] = mapped_column(Float, nullable=False)
    fusion_dense_weight: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_clause_count: Mapped[int] = mapped_column(Integer, nullable=False)
    indexed_clause_count: Mapped[int] = mapped_column(Integer, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PolicyRerankerProfileModel(CreatedAtMixin, Base):
    __tablename__ = "policy_reranker_profiles"
    __table_args__ = (
        UniqueConstraint(
            "profile_name", "profile_version", name="uq_policy_reranker_profiles_version"
        ),
        CheckConstraint(
            "max_query_tokens > 0 AND max_document_tokens > 0 AND max_pair_tokens > 0",
            name="token_limits_positive",
        ),
        CheckConstraint(
            "max_query_tokens + max_document_tokens <= max_pair_tokens",
            name="token_budgets_fit",
        ),
        CheckConstraint(
            "candidate_k > 0 AND candidate_k <= 50 AND final_k > 0 AND final_k <= candidate_k",
            name="ranking_limits_valid",
        ),
        CheckConstraint("batch_size > 0 AND batch_size <= 50", name="batch_size_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_artifact: Mapped[str] = mapped_column(String(255), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    instruction_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    query_template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    query_template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    query_template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    document_template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    document_template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    max_query_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    max_document_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    max_pair_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_k: Mapped[int] = mapped_column(Integer, nullable=False)
    final_k: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    device: Mapped[str] = mapped_column(String(32), nullable=False)
    score_semantics: Mapped[str] = mapped_column(Text, nullable=False)


class PolicyRetrievalExecutionProfileModel(CreatedAtMixin, Base):
    __tablename__ = "policy_retrieval_execution_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ("base_index_version_id",),
            ("policy_index_versions.id",),
            name="fk_policy_retrieval_execution_profiles_base_index",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("reranker_profile_id",),
            ("policy_reranker_profiles.id",),
            name="fk_policy_retrieval_execution_profiles_reranker",
            ondelete="RESTRICT",
        ),
        CheckConstraint("candidate_mode = 'HYBRID_RRF'", name="candidate_mode_allowed"),
        CheckConstraint(
            "candidate_k > 0 AND candidate_k <= 50 AND final_k > 0 AND final_k <= candidate_k",
            name="ranking_limits_valid",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(POLICY_EXECUTION_PROFILE_STATUSES)})",
            name="status_allowed",
        ),
        UniqueConstraint(
            "base_index_version_id",
            "profile_name",
            "profile_version",
            name="uq_policy_retrieval_execution_profiles_version",
        ),
        Index(
            "uq_policy_retrieval_execution_profiles_one_active",
            "base_index_version_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    base_index_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reranker_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    candidate_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_k: Mapped[int] = mapped_column(Integer, nullable=False)
    final_k: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyQueryBuilderProfileModel(CreatedAtMixin, Base):
    __tablename__ = "policy_query_builder_profiles"
    __table_args__ = (
        CheckConstraint(
            f"strategy IN ({_sql_values(POLICY_QUERY_STRATEGIES)})", name="strategy_allowed"
        ),
        CheckConstraint(
            "max_queries BETWEEN 1 AND 3 AND max_query_tokens > 0", name="limits_valid"
        ),
        UniqueConstraint(
            "profile_name", "profile_version", name="uq_policy_query_builder_profiles_version"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_artifact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    max_queries: Mapped[int] = mapped_column(Integer, nullable=False)
    max_query_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    filter_hint_policy: Mapped[str] = mapped_column(String(128), nullable=False)
    filter_hint_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyRetrievalRunModel(CreatedAtMixin, Base):
    __tablename__ = "policy_retrieval_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ("query_builder_profile_id",),
            ("policy_query_builder_profiles.id",),
            name="fk_policy_retrieval_runs_query_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("base_index_version_id",),
            ("policy_index_versions.id",),
            name="fk_policy_retrieval_runs_index",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_policy_retrieval_runs_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_policy_retrieval_runs_analysis",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "text_result_id"),
            ("llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"),
            name="fk_policy_retrieval_runs_text_v2",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "requested_by"),
            ("users.tenant_id", "users.id"),
            name="fk_policy_retrieval_runs_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"strategy IN ({_sql_values(POLICY_QUERY_STRATEGIES)})", name="strategy_allowed"
        ),
        CheckConstraint(
            f"status IN ({_sql_values(POLICY_RETRIEVAL_RUN_STATUSES)})", name="status_allowed"
        ),
        CheckConstraint("top_k BETWEEN 1 AND 50", name="top_k_valid"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_lower_hex"),
        CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="status_timestamps_consistent",
        ),
        CheckConstraint(
            "execution_attempt_count >= 0",
            name="execution_attempts_valid",
        ),
        CheckConstraint(
            "(status = 'RUNNING' AND claim_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND execution_attempt_count > 0) OR "
            "(status <> 'RUNNING' AND claim_token IS NULL AND lease_expires_at IS NULL)",
            name="execution_claim_consistent",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_policy_retrieval_runs_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "case_id",
            "id",
            name="uq_policy_retrieval_runs_tenant_case_id",
        ),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_policy_retrieval_runs_tenant_key"
        ),
        Index(
            "ix_policy_retrieval_runs_tenant_case_created",
            "tenant_id",
            "case_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_policy_retrieval_runs_running_lease",
            "lease_expires_at",
            "id",
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    text_result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    query_builder_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    base_index_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    base_retrieval_profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    multi_query_fusion_profile: Mapped[str] = mapped_column(String(128), nullable=False)
    multi_query_fusion_version: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    execution_attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class PolicyRetrievalRunQueryModel(CreatedAtMixin, Base):
    __tablename__ = "policy_retrieval_run_queries"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "retrieval_run_id"),
            ("policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"),
            name="fk_policy_retrieval_run_queries_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint("query_id ~ '^Q[1-3]$'", name="query_id_valid"),
        CheckConstraint("position BETWEEN 1 AND 3", name="position_valid"),
        CheckConstraint("query_hash ~ '^[0-9a-f]{64}$'", name="hash_lower_hex"),
        CheckConstraint(
            "(query_source = 'CASE_CUSTOMER_MESSAGE' AND query_text IS NULL) OR "
            "(query_source = 'GENERATED' AND length(btrim(query_text)) > 0)",
            name="raw_not_duplicated",
        ),
        UniqueConstraint(
            "tenant_id",
            "retrieval_run_id",
            "query_id",
            name="uq_policy_retrieval_run_queries_query",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    retrieval_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    query_id: Mapped[str] = mapped_column(String(8), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_source: Mapped[str] = mapped_column(String(64), nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    filter_hints: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class PolicyRetrievalRunHitModel(CreatedAtMixin, Base):
    __tablename__ = "policy_retrieval_run_hits"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "retrieval_run_id"),
            ("policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"),
            name="fk_policy_retrieval_run_hits_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_clause_row_id"),
            ("policy_clauses.tenant_id", "policy_clauses.id"),
            name="fk_policy_retrieval_run_hits_clause",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "rank > 0 AND best_query_rank > 0 AND fusion_score > 0", name="ranking_valid"
        ),
        UniqueConstraint(
            "tenant_id", "retrieval_run_id", "rank", name="uq_policy_retrieval_run_hits_rank"
        ),
        UniqueConstraint(
            "tenant_id",
            "retrieval_run_id",
            "policy_clause_row_id",
            name="uq_policy_retrieval_run_hits_clause",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    retrieval_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_clause_row_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fusion_score: Mapped[float] = mapped_column(Float, nullable=False)
    best_query_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_query_ids: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    per_query_ranks: Mapped[list[object]] = mapped_column(JSONB, nullable=False)


class PolicyRetrievalOutboxEventModel(ReliableAsyncOutboxMixin, CreatedAtMixin, Base):
    __tablename__ = "policy_retrieval_outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "retrieval_run_id"),
            ("policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"),
            name="fk_policy_retrieval_outbox_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id", "retrieval_run_id"),
            (
                "policy_retrieval_runs.tenant_id",
                "policy_retrieval_runs.case_id",
                "policy_retrieval_runs.id",
            ),
            name="fk_policy_retrieval_outbox_run_case",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(RELIABLE_ASYNC_OUTBOX_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "consumer_attempt_count >= 0",
            name="consumer_attempts_valid",
        ),
        CheckConstraint(
            RELIABLE_ASYNC_OUTBOX_STATE_CONSISTENCY,
            name="state_consistent",
        ),
        UniqueConstraint("tenant_id", "retrieval_run_id", name="uq_policy_retrieval_outbox_run"),
        Index(
            "ix_policy_retrieval_outbox_pending_dispatch",
            "available_at",
            "created_at",
            "id",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_policy_retrieval_outbox_processing_claimed",
            "claimed_at",
            "id",
            postgresql_where=text("status = 'PROCESSING'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    retrieval_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)


class GroundingProfileModel(CreatedAtMixin, Base):
    __tablename__ = "grounding_profiles"
    __table_args__ = (
        UniqueConstraint("profile_name", "profile_version", name="uq_grounding_profiles_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_artifact: Mapped[str] = mapped_column(String(255), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    validator_name: Mapped[str] = mapped_column(String(128), nullable=False)
    validator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyCitationPackModel(CreatedAtMixin, Base):
    __tablename__ = "policy_citation_packs"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "retrieval_run_id"),
            ("policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"),
            name="fk_policy_citation_packs_retrieval_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_policy_citation_packs_case",
            ondelete="RESTRICT",
        ),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="content_hash_lower_hex"),
        CheckConstraint(
            "retrieval_profile_hash ~ '^[0-9a-f]{64}$'",
            name="retrieval_profile_hash_lower_hex",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_policy_citation_packs_tenant_id"),
        UniqueConstraint(
            "tenant_id", "retrieval_run_id", name="uq_policy_citation_packs_retrieval_run"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    retrieval_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieval_profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyCitationPackItemModel(CreatedAtMixin, Base):
    __tablename__ = "policy_citation_pack_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "citation_pack_id"),
            ("policy_citation_packs.tenant_id", "policy_citation_packs.id"),
            name="fk_policy_citation_pack_items_pack",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_clause_row_id"),
            ("policy_clauses.tenant_id", "policy_clauses.id"),
            name="fk_policy_citation_pack_items_clause",
            ondelete="RESTRICT",
        ),
        CheckConstraint("rank > 0", name="rank_positive"),
        CheckConstraint("citation_id ~ '^CIT-[0-9]{3}$'", name="citation_id_valid"),
        UniqueConstraint(
            "tenant_id", "citation_pack_id", "rank", name="uq_citation_pack_items_rank"
        ),
        UniqueConstraint(
            "tenant_id",
            "citation_pack_id",
            "citation_id",
            name="uq_citation_pack_items_citation_id",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_policy_citation_pack_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "policy_clause_row_id",
            name="uq_policy_citation_pack_items_tenant_id_clause",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    citation_pack_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    citation_id: Mapped[str] = mapped_column(String(16), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_clause_row_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_clause_id: Mapped[str] = mapped_column(String(320), nullable=False)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    section_path: Mapped[list[str]] = mapped_column(ARRAY(String(500)), nullable=False)
    clause_type: Mapped[str] = mapped_column(String(64), nullable=False)
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    query_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    matched_query_ids: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    retrieval_profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class GroundedExplanationRunModel(CreatedAtMixin, Base):
    __tablename__ = "grounded_explanation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "retrieval_run_id"),
            ("policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"),
            name="fk_grounded_explanation_runs_retrieval",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "citation_pack_id"),
            ("policy_citation_packs.tenant_id", "policy_citation_packs.id"),
            name="fk_grounded_explanation_runs_pack",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_grounded_explanation_runs_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "requested_by"),
            ("users.tenant_id", "users.id"),
            name="fk_grounded_explanation_runs_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("grounding_profile_id",),
            ("grounding_profiles.id",),
            name="fk_grounded_explanation_runs_profile",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(GROUNDED_EXPLANATION_RUN_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_lower_hex"),
        CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="status_timestamps_consistent",
        ),
        CheckConstraint(
            "execution_attempt_count >= 0",
            name="execution_attempts_valid",
        ),
        CheckConstraint(
            "(status = 'RUNNING' AND claim_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND execution_attempt_count > 0) OR "
            "(status <> 'RUNNING' AND claim_token IS NULL AND lease_expires_at IS NULL)",
            name="execution_claim_consistent",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_grounded_explanation_runs_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "case_id",
            "id",
            name="uq_grounded_explanation_runs_tenant_case_id",
        ),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_grounded_explanation_runs_tenant_key"
        ),
        Index(
            "ix_grounded_explanation_runs_case_created",
            "tenant_id",
            "case_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_grounded_explanation_runs_running_lease",
            "lease_expires_at",
            "id",
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    retrieval_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    citation_pack_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    grounding_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    execution_attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class GroundedExplanationResultModel(CreatedAtMixin, Base):
    __tablename__ = "grounded_explanation_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "grounded_explanation_run_id"),
            ("grounded_explanation_runs.tenant_id", "grounded_explanation_runs.id"),
            name="fk_grounded_explanation_results_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "grounded_explanation_run_id",
            name="uq_grounded_explanation_results_run",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    grounded_explanation_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    policy_statements: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    unresolved_conditions: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    validation_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GroundedExplanationOutboxEventModel(ReliableAsyncOutboxMixin, CreatedAtMixin, Base):
    __tablename__ = "grounded_explanation_outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "grounded_explanation_run_id"),
            ("grounded_explanation_runs.tenant_id", "grounded_explanation_runs.id"),
            name="fk_grounded_explanation_outbox_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id", "grounded_explanation_run_id"),
            (
                "grounded_explanation_runs.tenant_id",
                "grounded_explanation_runs.case_id",
                "grounded_explanation_runs.id",
            ),
            name="fk_grounded_explanation_outbox_run_case",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(RELIABLE_ASYNC_OUTBOX_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "consumer_attempt_count >= 0",
            name="consumer_attempts_valid",
        ),
        CheckConstraint(
            RELIABLE_ASYNC_OUTBOX_STATE_CONSISTENCY,
            name="state_consistent",
        ),
        UniqueConstraint(
            "tenant_id",
            "grounded_explanation_run_id",
            name="uq_grounded_explanation_outbox_run",
        ),
        Index(
            "ix_grounded_explanation_outbox_pending_dispatch",
            "available_at",
            "created_at",
            "id",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_grounded_explanation_outbox_processing_claimed",
            "claimed_at",
            "id",
            postgresql_where=text("status = 'PROCESSING'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    grounded_explanation_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)


class PolicyRuleSetModel(CreatedAtMixin, Base):
    __tablename__ = "policy_rule_sets"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",), ("tenants.id",), name="fk_policy_rule_sets_tenant", ondelete="RESTRICT"
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="dates_valid"
        ),
        CheckConstraint("source_type = 'SYNTHETIC_REFERENCE'", name="source_type_allowed"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$' AND source_corpus_hash ~ '^[0-9a-f]{64}$'",
            name="hashes_valid",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_policy_rule_sets_tenant_id"),
        UniqueConstraint(
            "tenant_id", "rule_set_name", "rule_set_version", name="uq_policy_rule_sets_version"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_set_name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_corpus_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_corpus_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_corpus_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    field_registry_version: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_registry_version: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyRuleSetActivationModel(CreatedAtMixin, Base):
    __tablename__ = "policy_rule_set_activations"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "rule_set_id"),
            ("policy_rule_sets.tenant_id", "policy_rule_sets.id"),
            name="fk_policy_rule_set_activations_rule_set",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "created_by"),
            ("users.tenant_id", "users.id"),
            name="fk_policy_rule_set_activations_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint("retired_at IS NULL OR retired_at >= activated_at", name="dates_valid"),
        Index(
            "uq_policy_rule_set_activations_one_active",
            "tenant_id",
            "rule_set_name",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_set_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_set_name: Mapped[str] = mapped_column(String(128), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activation_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class PolicyRuleModel(CreatedAtMixin, Base):
    __tablename__ = "policy_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "rule_set_id"),
            ("policy_rule_sets.tenant_id", "policy_rule_sets.id"),
            name="fk_policy_rules_rule_set",
            ondelete="RESTRICT",
        ),
        CheckConstraint("priority BETWEEN 0 AND 10000", name="priority"),
        CheckConstraint("prohibit_final_decision", name="no_final_decision"),
        CheckConstraint(
            "jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) > 0",
            name="conditions_nonempty",
        ),
        CheckConstraint(
            "jsonb_typeof(effects) = 'array' AND jsonb_array_length(effects) > 0",
            name="effects_nonempty",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_policy_rules_tenant_id"),
        UniqueConstraint(
            "tenant_id", "rule_set_id", "rule_id", "rule_version", name="uq_policy_rules_identity"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_set_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    conditions: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    effects: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    prohibit_final_decision: Mapped[bool] = mapped_column(Boolean, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyRuleSourceClauseModel(CreatedAtMixin, Base):
    __tablename__ = "policy_rule_source_clauses"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "policy_rule_id"),
            ("policy_rules.tenant_id", "policy_rules.id"),
            name="fk_policy_rule_source_clauses_rule",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_clause_row_id"),
            ("policy_clauses.tenant_id", "policy_clauses.id"),
            name="fk_policy_rule_source_clauses_clause",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "policy_rule_id",
            "policy_clause_row_id",
            name="uq_policy_rule_source_clause",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_rule_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_clause_row_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version: Mapped[str] = mapped_column(String(64), nullable=False)
    clause_id: Mapped[str] = mapped_column(String(320), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyEvaluationRunModel(CreatedAtMixin, Base):
    __tablename__ = "policy_evaluation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_policy_evaluation_runs_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_policy_evaluation_runs_analysis",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "rule_set_id"),
            ("policy_rule_sets.tenant_id", "policy_rule_sets.id"),
            name="fk_policy_evaluation_runs_rule_set",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "requested_by"),
            ("users.tenant_id", "users.id"),
            name="fk_policy_evaluation_runs_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(POLICY_EVALUATION_RUN_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="timestamps_valid",
        ),
        CheckConstraint(
            "execution_attempt_count >= 0",
            name="execution_attempts_valid",
        ),
        CheckConstraint(
            "(status = 'RUNNING' AND claim_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND execution_attempt_count > 0) OR "
            "(status <> 'RUNNING' AND claim_token IS NULL AND lease_expires_at IS NULL)",
            name="execution_claim_consistent",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_policy_evaluation_runs_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "case_id",
            "id",
            name="uq_policy_evaluation_runs_tenant_case_id",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_policy_evaluation_runs_key"),
        Index("ix_policy_evaluation_runs_case_created", "tenant_id", "case_id", "created_at", "id"),
        Index(
            "ix_policy_evaluation_runs_running_lease",
            "lease_expires_at",
            "id",
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_set_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    execution_attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class PolicyEvaluationInputSnapshotModel(CreatedAtMixin, Base):
    __tablename__ = "policy_evaluation_input_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "policy_evaluation_run_id"),
            ("policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"),
            name="fk_policy_evaluation_input_snapshots_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "llm_extraction_result_v2_id"),
            ("llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"),
            name="fk_policy_evaluation_input_snapshots_extraction",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "policy_evaluation_run_id", name="uq_policy_evaluation_snapshot_run"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_evaluation_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    llm_extraction_result_v2_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    vision_analysis_run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    alignment_result_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    input_values: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    source_qualification_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyRuleEvaluationResultModel(CreatedAtMixin, Base):
    __tablename__ = "policy_rule_evaluation_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "policy_evaluation_run_id"),
            ("policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"),
            name="fk_policy_rule_evaluation_results_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_rule_id"),
            ("policy_rules.tenant_id", "policy_rules.id"),
            name="fk_policy_rule_evaluation_results_rule",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "rule_status IN ('MATCHED','NOT_MATCHED','INDETERMINATE','NOT_APPLICABLE')",
            name="status_allowed",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_policy_rule_evaluation_results_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "policy_evaluation_run_id",
            "policy_rule_id",
            name="uq_policy_rule_evaluation_result",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_evaluation_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_rule_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_clause_ids: Mapped[list[str]] = mapped_column(ARRAY(String(320)), nullable=False)


class PolicyConditionEvaluationResultModel(CreatedAtMixin, Base):
    __tablename__ = "policy_condition_evaluation_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "policy_rule_evaluation_result_id"),
            ("policy_rule_evaluation_results.tenant_id", "policy_rule_evaluation_results.id"),
            name="fk_policy_condition_evaluation_results_rule_result",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "condition_status IN "
            "('SATISFIED','UNSATISFIED','UNKNOWN','NOT_EVALUATED','NOT_APPLICABLE')",
            name="status_allowed",
        ),
        UniqueConstraint(
            "tenant_id",
            "policy_rule_evaluation_result_id",
            "condition_index",
            name="uq_policy_condition_evaluation_result",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_rule_evaluation_result_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    condition_index: Mapped[int] = mapped_column(Integer, nullable=False)
    condition_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actual_value: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)


class PolicyEvaluationEffectModel(CreatedAtMixin, Base):
    __tablename__ = "policy_evaluation_effects"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "policy_rule_evaluation_result_id"),
            ("policy_rule_evaluation_results.tenant_id", "policy_rule_evaluation_results.id"),
            name="fk_policy_evaluation_effects_rule_result",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "effect_type IN "
            "('MARK_REVIEW_ELIGIBILITY','REQUIRE_ADDITIONAL_EVIDENCE',"
            "'REQUIRE_HUMAN_REVIEW','REQUIRE_MANAGER_REVIEW','PROHIBIT_AUTOMATION',"
            "'FLAG_POLICY_EXCEPTION')",
            name="type_allowed",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_rule_evaluation_result_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    effect_type: Mapped[str] = mapped_column(String(64), nullable=False)
    effect_value: Mapped[str | None] = mapped_column(String(128), nullable=True)


class PolicyEvaluationOutboxEventModel(ReliableAsyncOutboxMixin, CreatedAtMixin, Base):
    __tablename__ = "policy_evaluation_outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "policy_evaluation_run_id"),
            ("policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"),
            name="fk_policy_evaluation_outbox_events_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id", "policy_evaluation_run_id"),
            (
                "policy_evaluation_runs.tenant_id",
                "policy_evaluation_runs.case_id",
                "policy_evaluation_runs.id",
            ),
            name="fk_policy_evaluation_outbox_run_case",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(RELIABLE_ASYNC_OUTBOX_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "consumer_attempt_count >= 0",
            name="consumer_attempts_valid",
        ),
        CheckConstraint(
            RELIABLE_ASYNC_OUTBOX_STATE_CONSISTENCY,
            name="state_consistent",
        ),
        UniqueConstraint(
            "tenant_id", "policy_evaluation_run_id", name="uq_policy_evaluation_outbox_run"
        ),
        Index(
            "ix_policy_evaluation_outbox_pending_dispatch",
            "available_at",
            "created_at",
            "id",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_policy_evaluation_outbox_processing_claimed",
            "claimed_at",
            "id",
            postgresql_where=text("status = 'PROCESSING'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_evaluation_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)


class HumanReviewTaskModel(TimestampMixin, Base):
    __tablename__ = "human_review_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_human_review_tasks_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_evaluation_run_id"),
            ("policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"),
            name="fk_human_review_tasks_policy_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "current_assignee_id"),
            ("users.tenant_id", "users.id"),
            name="fk_human_review_tasks_assignee",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"task_type IN ({_sql_values(HUMAN_REVIEW_TASK_TYPES)})", name="type_allowed"
        ),
        CheckConstraint(
            f"priority IN ({_sql_values(HUMAN_REVIEW_PRIORITIES)})", name="priority_allowed"
        ),
        CheckConstraint(f"status IN ({_sql_values(HUMAN_REVIEW_STATUSES)})", name="status_allowed"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(status = 'CLAIMED' AND current_assignee_id IS NOT NULL) OR "
            "(status <> 'CLAIMED' AND current_assignee_id IS NULL)",
            name="assignee_status_consistent",
        ),
        CheckConstraint(
            "(status = 'RESOLVED' AND resolved_at IS NOT NULL) OR "
            "(status <> 'RESOLVED' AND resolved_at IS NULL)",
            name="resolved_timestamp_consistent",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_human_review_tasks_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "policy_evaluation_run_id",
            "task_type",
            name="uq_human_review_tasks_policy_run_type",
        ),
        Index(
            "ix_human_review_tasks_queue",
            "tenant_id",
            "status",
            "priority",
            "created_at",
            "id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_evaluation_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_assignee_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    mapping_rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    mapping_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HumanReviewPacketModel(CreatedAtMixin, Base):
    __tablename__ = "human_review_packets"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "review_task_id"),
            ("human_review_tasks.tenant_id", "human_review_tasks.id"),
            name="fk_human_review_packets_task",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_human_review_packets_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name="fk_human_review_packets_analysis",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_evaluation_run_id"),
            ("policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"),
            name="fk_human_review_packets_policy_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "rule_set_id"),
            ("policy_rule_sets.tenant_id", "policy_rule_sets.id"),
            name="fk_human_review_packets_rule_set",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "llm_extraction_result_v2_id"),
            ("llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"),
            name="fk_human_review_packets_extraction",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "completeness_result_id"),
            ("llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"),
            name="fk_human_review_packets_completeness",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "citation_pack_id"),
            ("policy_citation_packs.tenant_id", "policy_citation_packs.id"),
            name="fk_human_review_packets_citation_pack",
            ondelete="RESTRICT",
        ),
        CheckConstraint("jsonb_typeof(vision_result_ids) = 'array'", name="vision_ids_array"),
        CheckConstraint(
            "jsonb_typeof(case_metadata_snapshot) = 'object'", name="case_snapshot_object"
        ),
        CheckConstraint(
            "jsonb_typeof(qualification_snapshot) = 'object'",
            name="qualification_snapshot_object",
        ),
        CheckConstraint(
            "jsonb_typeof(policy_effects) = 'array' AND jsonb_array_length(policy_effects) > 0",
            name="effects_nonempty",
        ),
        CheckConstraint(
            "rule_set_hash ~ '^[0-9a-f]{64}$' AND packet_hash ~ '^[0-9a-f]{64}$'",
            name="hashes_valid",
        ),
        UniqueConstraint("tenant_id", "review_task_id", name="uq_human_review_packets_task"),
        UniqueConstraint("tenant_id", "id", name="uq_human_review_packets_tenant_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_evaluation_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_set_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    llm_extraction_result_v2_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    completeness_result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    vision_result_ids: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    alignment_result_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    citation_pack_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    grounding_result_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    case_metadata_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    qualification_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    policy_effects: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    policy_summary_status: Mapped[str] = mapped_column(String(64), nullable=False)
    packet_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class HumanReviewActionModel(CreatedAtMixin, Base):
    __tablename__ = "human_review_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "review_task_id"),
            ("human_review_tasks.tenant_id", "human_review_tasks.id"),
            name="fk_human_review_actions_task",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "actor_id"),
            ("users.tenant_id", "users.id"),
            name="fk_human_review_actions_actor",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"action_type IN ({_sql_values(HUMAN_REVIEW_ACTIONS)})", name="type_allowed"
        ),
        CheckConstraint(
            f"to_status IN ({_sql_values(HUMAN_REVIEW_STATUSES)})", name="to_status_allowed"
        ),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_sql_values(HUMAN_REVIEW_STATUSES)})",
            name="from_status_allowed",
        ),
        CheckConstraint("resulting_task_version = expected_task_version + 1", name="version_step"),
        CheckConstraint("jsonb_typeof(reason_codes) = 'array'", name="reasons_array"),
        CheckConstraint("jsonb_typeof(action_payload) = 'object'", name="payload_object"),
        CheckConstraint(
            "(action_type = 'CREATED' AND actor_id IS NULL AND actor_role IS NULL) OR "
            "(action_type <> 'CREATED' AND actor_id IS NOT NULL AND "
            "actor_role IN ('ADMIN','REVIEWER'))",
            name="human_actor_required",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_human_review_actions_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "review_task_id",
            "resulting_task_version",
            name="uq_human_review_actions_task_version",
        ),
        Index(
            "ix_human_review_actions_task_created",
            "tenant_id",
            "review_task_id",
            "created_at",
            "id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason_codes: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    action_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    expected_task_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_task_version: Mapped[int] = mapped_column(Integer, nullable=False)


class HumanReviewAssignmentModel(CreatedAtMixin, Base):
    __tablename__ = "human_review_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "review_task_id"),
            ("human_review_tasks.tenant_id", "human_review_tasks.id"),
            name="fk_human_review_assignments_task",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "assignee_id"),
            ("users.tenant_id", "users.id"),
            name="fk_human_review_assignments_assignee",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "assigned_by"),
            ("users.tenant_id", "users.id"),
            name="fk_human_review_assignments_assigner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "assignment_type IN ('SELF_CLAIM','ADMIN_ASSIGNMENT','ESCALATION_CLAIM')",
            name="type_allowed",
        ),
        CheckConstraint(
            "released_at IS NULL OR released_at >= assigned_at", name="released_after_assigned"
        ),
        Index(
            "uq_human_review_assignments_current",
            "tenant_id",
            "review_task_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assignee_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assigned_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assignment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HumanReviewDecisionModel(CreatedAtMixin, Base):
    __tablename__ = "human_review_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "review_task_id"),
            ("human_review_tasks.tenant_id", "human_review_tasks.id"),
            name="fk_human_review_decisions_task",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "decided_by"),
            ("users.tenant_id", "users.id"),
            name="fk_human_review_decisions_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"decision_type IN ({_sql_values(HUMAN_DECISION_TYPES)})", name="type_allowed"
        ),
        CheckConstraint("length(btrim(rationale)) BETWEEN 10 AND 2000", name="rationale_length"),
        CheckConstraint("jsonb_typeof(reason_codes) = 'array'", name="reasons_array"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="hash_valid"),
        CheckConstraint(
            "outcome_relation IN ('CONSISTENT_WITH_RECOMMENDATION',"
            "'DIFFERS_FROM_RECOMMENDATION','NO_COMPARABLE_RECOMMENDATION',"
            "'INDETERMINATE_POLICY')",
            name="outcome_relation_allowed",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_human_review_decisions_tenant_id"),
        UniqueConstraint("tenant_id", "review_task_id", name="uq_human_review_decisions_task"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_codes: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(String(2000), nullable=False)
    outcome_relation: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_relation_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class HumanReviewDecisionBasisModel(CreatedAtMixin, Base):
    __tablename__ = "human_review_decision_basis"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "human_review_decision_id"),
            ("human_review_decisions.tenant_id", "human_review_decisions.id"),
            name="fk_human_review_decision_basis_decision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_rule_result_id"),
            ("policy_rule_evaluation_results.tenant_id", "policy_rule_evaluation_results.id"),
            name="fk_human_review_decision_basis_rule_result",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_clause_row_id"),
            ("policy_clauses.tenant_id", "policy_clauses.id"),
            name="fk_human_review_decision_basis_clause",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "citation_item_id"),
            ("policy_citation_pack_items.tenant_id", "policy_citation_pack_items.id"),
            name="fk_human_review_decision_basis_citation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "citation_item_id", "policy_clause_row_id"),
            (
                "policy_citation_pack_items.tenant_id",
                "policy_citation_pack_items.id",
                "policy_citation_pack_items.policy_clause_row_id",
            ),
            name="fk_human_review_decision_basis_citation_clause",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_evidence_id"),
            ("case_evidence.tenant_id", "case_evidence.id"),
            name="fk_human_review_decision_basis_evidence",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_result_id"),
            ("llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"),
            name="fk_human_review_decision_basis_analysis",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "basis_type IN ('POLICY_RULE_RESULT','POLICY_CITATION','CASE_EVIDENCE',"
            "'ANALYSIS_RESULT')",
            name="type_allowed",
        ),
        CheckConstraint(
            "(basis_type = 'POLICY_RULE_RESULT' AND policy_rule_result_id IS NOT NULL "
            "AND policy_clause_row_id IS NULL AND citation_item_id IS NULL "
            "AND case_evidence_id IS NULL AND analysis_result_id IS NULL) OR "
            "(basis_type = 'POLICY_CITATION' AND policy_rule_result_id IS NULL "
            "AND policy_clause_row_id IS NOT NULL AND citation_item_id IS NOT NULL "
            "AND case_evidence_id IS NULL AND analysis_result_id IS NULL) OR "
            "(basis_type = 'CASE_EVIDENCE' AND policy_rule_result_id IS NULL "
            "AND policy_clause_row_id IS NULL AND citation_item_id IS NULL "
            "AND case_evidence_id IS NOT NULL AND analysis_result_id IS NULL) OR "
            "(basis_type = 'ANALYSIS_RESULT' AND policy_rule_result_id IS NULL "
            "AND policy_clause_row_id IS NULL AND citation_item_id IS NULL "
            "AND case_evidence_id IS NULL AND analysis_result_id IS NOT NULL)",
            name="typed_reference_consistent",
        ),
        UniqueConstraint(
            "tenant_id",
            "human_review_decision_id",
            "basis_type",
            "reference_id",
            name="uq_human_review_decision_basis_reference",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    human_review_decision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    basis_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(320), nullable=False)
    policy_rule_result_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    policy_clause_row_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    citation_item_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    case_evidence_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    analysis_result_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class HumanReviewRequestEventModel(ReliableAsyncOutboxMixin, CreatedAtMixin, Base):
    __tablename__ = "human_review_request_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name="fk_human_review_request_events_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_evaluation_run_id"),
            ("policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"),
            name="fk_human_review_request_events_policy_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "case_id", "policy_evaluation_run_id"),
            (
                "policy_evaluation_runs.tenant_id",
                "policy_evaluation_runs.case_id",
                "policy_evaluation_runs.id",
            ),
            name="fk_human_review_request_events_policy_run_case",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(RELIABLE_ASYNC_OUTBOX_STATUSES)})",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "consumer_attempt_count >= 0",
            name="consumer_attempts_valid",
        ),
        CheckConstraint(
            RELIABLE_ASYNC_OUTBOX_STATE_CONSISTENCY,
            name="state_consistent",
        ),
        UniqueConstraint(
            "tenant_id", "policy_evaluation_run_id", name="uq_human_review_request_events_run"
        ),
        Index(
            "ix_human_review_request_events_pending_dispatch",
            "available_at",
            "created_at",
            "id",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_human_review_request_events_processing_claimed",
            "claimed_at",
            "id",
            postgresql_where=text("status = 'PROCESSING'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    policy_evaluation_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)


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
    LLMExtractionResultV2Model,
    AnalysisRunEvidenceModel,
    VisionAnalysisResultModel,
    VisionDetectionModel,
    AnalysisRequestIdempotencyRecordModel,
    OutboxEventModel,
    PolicyIngestionRunModel,
    PolicyDocumentModel,
    PolicyClauseModel,
    PolicyEmbeddingProfileModel,
    PolicyClauseEmbeddingModel,
    PolicyIndexVersionModel,
    PolicyRerankerProfileModel,
    PolicyRetrievalExecutionProfileModel,
    PolicyQueryBuilderProfileModel,
    PolicyRetrievalRunModel,
    PolicyRetrievalRunQueryModel,
    PolicyRetrievalRunHitModel,
    PolicyRetrievalOutboxEventModel,
    GroundingProfileModel,
    PolicyCitationPackModel,
    PolicyCitationPackItemModel,
    GroundedExplanationRunModel,
    GroundedExplanationResultModel,
    GroundedExplanationOutboxEventModel,
    PolicyRuleSetModel,
    PolicyRuleSetActivationModel,
    PolicyRuleModel,
    PolicyRuleSourceClauseModel,
    PolicyEvaluationRunModel,
    PolicyEvaluationInputSnapshotModel,
    PolicyRuleEvaluationResultModel,
    PolicyConditionEvaluationResultModel,
    PolicyEvaluationEffectModel,
    PolicyEvaluationOutboxEventModel,
    HumanReviewTaskModel,
    HumanReviewPacketModel,
    HumanReviewActionModel,
    HumanReviewAssignmentModel,
    HumanReviewDecisionModel,
    HumanReviewDecisionBasisModel,
    HumanReviewRequestEventModel,
)
