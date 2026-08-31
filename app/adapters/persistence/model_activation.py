"""PostgreSQL persistence for signed LLM releases and append-only activation events."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, aliased, mapped_column, sessionmaker

from app.adapters.persistence.base import Base
from app.adapters.persistence.models import TenantModel
from app.adapters.persistence.tenant_context import tenant_context
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.errors import IdempotencyKeyReusedError, InconsistentPersistenceStateError
from app.platform.model_activation import (
    ActiveLLMRelease,
    ModelActivationConflictError,
    ModelActivationEvent,
    ModelReleaseNotFoundError,
    ModelReleaseRegistrationConflictError,
    ModelReleaseTask,
    RegisteredLLMRelease,
    SignedLLMReleaseManifest,
)

_JSON_OBJECT = JSON().with_variant(JSONB, "postgresql")
_SUPPORTED_TASKS_SQL = (
    "'PRODUCT_DEFECT_TEXT_EXTRACTION_V2','POLICY_QUERY_BUILDER_V1','GROUNDED_POLICY_EXPLANATION_V1'"
)


class LLMReleaseManifestModel(Base):
    __tablename__ = "llm_release_manifests"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_llm_release_manifests_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "registered_by"),
            ("users.tenant_id", "users.id"),
            name="fk_llm_release_manifests_registered_by",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"task IN ({_SUPPORTED_TASKS_SQL})",
            name="task_supported",
        ),
        CheckConstraint(
            "manifest_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="manifest_digest_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "signature_algorithm = 'ED25519'",
            name="signature_algorithm_supported",
        ),
        CheckConstraint(
            "length(signature_base64) = 88",
            name="signature_length_valid",
        ),
        CheckConstraint(
            "jsonb_typeof(manifest) = 'object'",
            name="manifest_object",
        ).ddl_if(dialect="postgresql"),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_llm_release_manifests_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "task",
            "id",
            name="uq_llm_release_manifests_tenant_task_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "task",
            "package_name",
            "package_version",
            name="uq_llm_release_manifests_package_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "manifest_digest",
            name="uq_llm_release_manifests_digest",
        ),
        Index(
            "ix_llm_release_manifests_tenant_task_registered",
            "tenant_id",
            "task",
            "registered_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    package_name: Mapped[str] = mapped_column(String(128), nullable=False)
    package_version: Mapped[str] = mapped_column(String(128), nullable=False)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, object]] = mapped_column(_JSON_OBJECT, nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(16), nullable=False)
    signature_base64: Mapped[str] = mapped_column(String(88), nullable=False)
    registered_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LLMModelActivationEventModel(Base):
    __tablename__ = "llm_model_activation_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_llm_model_activation_events_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "task", "model_release_id"),
            (
                "llm_release_manifests.tenant_id",
                "llm_release_manifests.task",
                "llm_release_manifests.id",
            ),
            name="fk_llm_model_activation_events_release",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "task", "execution_mode", "previous_activation_id"),
            (
                "llm_model_activation_events.tenant_id",
                "llm_model_activation_events.task",
                "llm_model_activation_events.execution_mode",
                "llm_model_activation_events.id",
            ),
            name="fk_llm_model_activation_events_previous",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "activated_by"),
            ("users.tenant_id", "users.id"),
            name="fk_llm_model_activation_events_activated_by",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"task IN ({_SUPPORTED_TASKS_SQL})",
            name="task_supported",
        ),
        CheckConstraint(
            "execution_mode IN ('PRIMARY', 'SHADOW')",
            name="execution_mode_supported",
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="request_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_nonempty"),
        CheckConstraint("length(btrim(idempotency_key)) > 0", name="idempotency_key_nonempty"),
        CheckConstraint(
            "previous_activation_id IS NULL OR previous_activation_id <> id",
            name="previous_not_self",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_llm_model_activation_events_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "task",
            "execution_mode",
            "id",
            name="uq_llm_model_activation_events_tenant_mode_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "previous_activation_id",
            name="uq_llm_model_activation_events_previous",
        ),
        UniqueConstraint(
            "tenant_id",
            "task",
            "execution_mode",
            "idempotency_key",
            name="uq_llm_model_activation_events_idempotency",
        ),
        Index(
            "ix_llm_model_activation_events_active",
            "tenant_id",
            "task",
            "execution_mode",
            text("activated_at DESC"),
            text("id DESC"),
        ),
        Index(
            "uq_llm_model_activation_events_root",
            "tenant_id",
            "task",
            "execution_mode",
            unique=True,
            postgresql_where=text("previous_activation_id IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    model_release_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    previous_activation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    activated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SQLAlchemyModelActivationRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def register_release(
        self,
        *,
        tenant_id: str,
        release_id: str,
        value: SignedLLMReleaseManifest,
        registered_by: str,
        registered_at: datetime,
    ) -> tuple[RegisteredLLMRelease, bool]:
        tenant_uuid = UUID(tenant_id)
        manifest = value.manifest
        with tenant_context(tenant_id), self._factory.begin() as session:
            _lock_tenant(session, tenant_uuid)
            existing = session.scalar(
                select(LLMReleaseManifestModel).where(
                    LLMReleaseManifestModel.tenant_id == tenant_uuid,
                    LLMReleaseManifestModel.task == manifest.task.value,
                    LLMReleaseManifestModel.package_name == manifest.package_name,
                    LLMReleaseManifestModel.package_version == manifest.package_version,
                )
            )
            if existing is not None:
                if _same_signed_manifest(existing, value):
                    return _release(existing), True
                raise ModelReleaseRegistrationConflictError()
            duplicate_digest = session.scalar(
                select(LLMReleaseManifestModel.id).where(
                    LLMReleaseManifestModel.tenant_id == tenant_uuid,
                    LLMReleaseManifestModel.manifest_digest == manifest.manifest_digest,
                )
            )
            if duplicate_digest is not None:
                raise ModelReleaseRegistrationConflictError()
            model = LLMReleaseManifestModel(
                id=UUID(release_id),
                tenant_id=tenant_uuid,
                package_name=manifest.package_name,
                package_version=manifest.package_version,
                task=manifest.task.value,
                manifest=manifest.model_dump(mode="json"),
                manifest_digest=manifest.manifest_digest,
                signing_key_id=value.signing_key_id,
                signature_algorithm=value.signature_algorithm,
                signature_base64=value.signature_base64,
                registered_by=UUID(registered_by),
                registered_at=registered_at,
            )
            session.add(model)
            session.flush()
            return _release(model), False

    def get_release(
        self,
        *,
        tenant_id: str,
        release_id: str,
    ) -> RegisteredLLMRelease | None:
        with tenant_context(tenant_id), self._factory() as session:
            model = session.scalar(
                select(LLMReleaseManifestModel).where(
                    LLMReleaseManifestModel.tenant_id == UUID(tenant_id),
                    LLMReleaseManifestModel.id == UUID(release_id),
                )
            )
        return _release(model) if model is not None else None

    def activate(
        self,
        *,
        event: ModelActivationEvent,
        expected_current_activation_id: str | None,
    ) -> tuple[ModelActivationEvent, bool]:
        tenant_uuid = UUID(event.tenant_id)
        with tenant_context(event.tenant_id), self._factory.begin() as session:
            _lock_tenant(session, tenant_uuid)
            replay = session.scalar(
                select(LLMModelActivationEventModel).where(
                    LLMModelActivationEventModel.tenant_id == tenant_uuid,
                    LLMModelActivationEventModel.task == event.task.value,
                    LLMModelActivationEventModel.execution_mode == event.execution_mode.value,
                    LLMModelActivationEventModel.idempotency_key == event.idempotency_key,
                )
            )
            if replay is not None:
                if replay.request_hash != event.request_hash:
                    raise IdempotencyKeyReusedError()
                return _activation(replay), True

            release = session.scalar(
                select(LLMReleaseManifestModel).where(
                    LLMReleaseManifestModel.tenant_id == tenant_uuid,
                    LLMReleaseManifestModel.id == UUID(event.model_release_id),
                )
            )
            if release is None:
                raise ModelReleaseNotFoundError()
            if release.task != event.task.value:
                raise ModelReleaseRegistrationConflictError()

            current = _latest_activation_model(
                session,
                tenant_id=tenant_uuid,
                task=event.task,
                execution_mode=event.execution_mode,
            )
            current_id = str(current.id) if current is not None else None
            if (
                current_id != expected_current_activation_id
                or current_id != event.previous_activation_id
            ):
                raise ModelActivationConflictError(details={"current_activation_id": current_id})

            model = LLMModelActivationEventModel(
                id=UUID(event.id),
                tenant_id=tenant_uuid,
                task=event.task.value,
                execution_mode=event.execution_mode.value,
                model_release_id=UUID(event.model_release_id),
                previous_activation_id=(
                    UUID(event.previous_activation_id)
                    if event.previous_activation_id is not None
                    else None
                ),
                activated_by=UUID(event.activated_by),
                reason=event.reason,
                idempotency_key=event.idempotency_key,
                request_hash=event.request_hash,
                activated_at=event.activated_at,
            )
            session.add(model)
            session.flush()
            return _activation(model), False

    def get_active(
        self,
        *,
        tenant_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ActiveLLMRelease | None:
        tenant_uuid = UUID(tenant_id)
        with tenant_context(tenant_id), self._factory() as session:
            activation = _latest_activation_model(
                session,
                tenant_id=tenant_uuid,
                task=task,
                execution_mode=execution_mode,
            )
            if activation is None:
                return None
            release = session.scalar(
                select(LLMReleaseManifestModel).where(
                    LLMReleaseManifestModel.tenant_id == tenant_uuid,
                    LLMReleaseManifestModel.id == activation.model_release_id,
                )
            )
            if release is None:
                raise InconsistentPersistenceStateError(
                    "The active model release manifest is missing."
                )
            return ActiveLLMRelease(
                release=_release(release),
                activation=_activation(activation),
            )

    def get_by_activation_id(
        self,
        *,
        tenant_id: str,
        activation_id: str,
    ) -> ActiveLLMRelease | None:
        tenant_uuid = UUID(tenant_id)
        with tenant_context(tenant_id), self._factory() as session:
            activation = session.scalar(
                select(LLMModelActivationEventModel).where(
                    LLMModelActivationEventModel.tenant_id == tenant_uuid,
                    LLMModelActivationEventModel.id == UUID(activation_id),
                )
            )
            if activation is None:
                return None
            release = session.scalar(
                select(LLMReleaseManifestModel).where(
                    LLMReleaseManifestModel.tenant_id == tenant_uuid,
                    LLMReleaseManifestModel.id == activation.model_release_id,
                )
            )
            if release is None:
                raise InconsistentPersistenceStateError(
                    "The pinned model release manifest is missing."
                )
            return ActiveLLMRelease(
                release=_release(release),
                activation=_activation(activation),
            )


def _lock_tenant(session: Session, tenant_id: UUID) -> None:
    found = session.scalar(
        select(TenantModel.id).where(TenantModel.id == tenant_id).with_for_update()
    )
    if found is None:
        raise InconsistentPersistenceStateError("The model release tenant does not exist.")


def _latest_activation_model(
    session: Session,
    *,
    tenant_id: UUID,
    task: ModelReleaseTask,
    execution_mode: AnalysisExecutionMode,
) -> LLMModelActivationEventModel | None:
    child = aliased(LLMModelActivationEventModel)
    return session.scalar(
        select(LLMModelActivationEventModel)
        .where(
            LLMModelActivationEventModel.tenant_id == tenant_id,
            LLMModelActivationEventModel.task == task.value,
            LLMModelActivationEventModel.execution_mode == execution_mode.value,
            ~select(child.id)
            .where(
                child.tenant_id == LLMModelActivationEventModel.tenant_id,
                child.task == LLMModelActivationEventModel.task,
                child.execution_mode == LLMModelActivationEventModel.execution_mode,
                child.previous_activation_id == LLMModelActivationEventModel.id,
            )
            .exists(),
        )
        .limit(1)
    )


def _same_signed_manifest(
    model: LLMReleaseManifestModel,
    value: SignedLLMReleaseManifest,
) -> bool:
    return (
        model.manifest_digest == value.manifest.manifest_digest
        and model.signing_key_id == value.signing_key_id
        and model.signature_algorithm == value.signature_algorithm
        and model.signature_base64 == value.signature_base64
    )


def _release(model: LLMReleaseManifestModel) -> RegisteredLLMRelease:
    signed_manifest = SignedLLMReleaseManifest.model_validate(
        {
            "manifest": model.manifest,
            "signing_key_id": model.signing_key_id,
            "signature_algorithm": model.signature_algorithm,
            "signature_base64": model.signature_base64,
        }
    )
    return RegisteredLLMRelease(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        signed_manifest=signed_manifest,
        registered_by=str(model.registered_by),
        registered_at=model.registered_at,
    )


def _activation(model: LLMModelActivationEventModel) -> ModelActivationEvent:
    return ModelActivationEvent(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        task=ModelReleaseTask(model.task),
        execution_mode=AnalysisExecutionMode(model.execution_mode),
        model_release_id=str(model.model_release_id),
        previous_activation_id=(
            str(model.previous_activation_id) if model.previous_activation_id is not None else None
        ),
        activated_by=str(model.activated_by),
        reason=model.reason,
        idempotency_key=model.idempotency_key,
        request_hash=model.request_hash,
        activated_at=model.activated_at,
    )


__all__ = [
    "LLMModelActivationEventModel",
    "LLMReleaseManifestModel",
    "SQLAlchemyModelActivationRepository",
]
