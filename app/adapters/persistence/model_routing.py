"""PostgreSQL persistence for immutable, tenant-scoped LLM route plans."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, Session, aliased, mapped_column, sessionmaker

from app.adapters.persistence.base import Base
from app.adapters.persistence.model_activation import LLMModelActivationEventModel
from app.adapters.persistence.models import TenantModel
from app.adapters.persistence.tenant_context import tenant_context
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.errors import IdempotencyKeyReusedError, InconsistentPersistenceStateError
from app.platform.model_activation import ModelReleaseTask
from app.platform.model_routing import (
    ModelRouteActivationConflictError,
    ModelRoutePlan,
    ModelRoutePlanConflictError,
)

_SUPPORTED_TASKS_SQL = (
    "'PRODUCT_DEFECT_TEXT_EXTRACTION_V2','POLICY_QUERY_BUILDER_V1','GROUNDED_POLICY_EXPLANATION_V1'"
)


class LLMModelRoutePlanModel(Base):
    __tablename__ = "llm_model_route_plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_llm_model_route_plans_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "task", "execution_mode", "model_activation_id"),
            (
                "llm_model_activation_events.tenant_id",
                "llm_model_activation_events.task",
                "llm_model_activation_events.execution_mode",
                "llm_model_activation_events.id",
            ),
            name="fk_llm_model_route_plans_activation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "task", "execution_mode", "previous_route_plan_id"),
            (
                "llm_model_route_plans.tenant_id",
                "llm_model_route_plans.task",
                "llm_model_route_plans.execution_mode",
                "llm_model_route_plans.id",
            ),
            name="fk_llm_model_route_plans_previous",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "activated_by"),
            ("users.tenant_id", "users.id"),
            name="fk_llm_model_route_plans_activated_by",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "schema_version = 'model_route_plan/1.0.0'",
            name="schema_version_supported",
        ),
        CheckConstraint(f"task IN ({_SUPPORTED_TASKS_SQL})", name="task_supported"),
        CheckConstraint(
            "execution_mode IN ('PRIMARY', 'SHADOW')",
            name="execution_mode_supported",
        ),
        CheckConstraint(
            "deployment_id ~ '^[a-z0-9][a-z0-9._-]{2,127}$'",
            name="deployment_id_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "automatic_cross_model_fallback = false",
            name="automatic_fallback_disabled",
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="request_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_nonempty"),
        CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name="idempotency_key_nonempty",
        ),
        CheckConstraint(
            "previous_route_plan_id IS NULL OR previous_route_plan_id <> id",
            name="previous_not_self",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_llm_model_route_plans_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "task",
            "execution_mode",
            "id",
            name="uq_llm_model_route_plans_tenant_mode_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "previous_route_plan_id",
            name="uq_llm_model_route_plans_previous",
        ),
        UniqueConstraint(
            "tenant_id",
            "task",
            "execution_mode",
            "idempotency_key",
            name="uq_llm_model_route_plans_idempotency",
        ),
        Index(
            "ix_llm_model_route_plans_active",
            "tenant_id",
            "task",
            "execution_mode",
            text("activated_at DESC"),
            text("id DESC"),
        ),
        Index(
            "uq_llm_model_route_plans_root",
            "tenant_id",
            "task",
            "execution_mode",
            unique=True,
            postgresql_where=text("previous_route_plan_id IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    model_activation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_route_plan_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    automatic_cross_model_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    activated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SQLAlchemyModelRoutePlanRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def get_by_idempotency_key(
        self,
        *,
        tenant_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
        idempotency_key: str,
    ) -> ModelRoutePlan | None:
        with tenant_context(tenant_id), self._factory() as session:
            model = session.scalar(
                select(LLMModelRoutePlanModel).where(
                    LLMModelRoutePlanModel.tenant_id == UUID(tenant_id),
                    LLMModelRoutePlanModel.task == task.value,
                    LLMModelRoutePlanModel.execution_mode == execution_mode.value,
                    LLMModelRoutePlanModel.idempotency_key == idempotency_key,
                )
            )
        return _route_plan(model) if model is not None else None

    def activate(
        self,
        *,
        route_plan: ModelRoutePlan,
        expected_current_route_plan_id: str | None,
    ) -> tuple[ModelRoutePlan, bool]:
        tenant_uuid = UUID(route_plan.tenant_id)
        with tenant_context(route_plan.tenant_id), self._factory.begin() as session:
            _lock_tenant(session, tenant_uuid)
            replay = session.scalar(
                select(LLMModelRoutePlanModel).where(
                    LLMModelRoutePlanModel.tenant_id == tenant_uuid,
                    LLMModelRoutePlanModel.task == route_plan.task.value,
                    LLMModelRoutePlanModel.execution_mode == route_plan.execution_mode.value,
                    LLMModelRoutePlanModel.idempotency_key == route_plan.idempotency_key,
                )
            )
            if replay is not None:
                if replay.request_hash != route_plan.request_hash:
                    raise IdempotencyKeyReusedError()
                return _route_plan(replay), True

            active_activation = _latest_activation_model(
                session,
                tenant_id=tenant_uuid,
                task=route_plan.task,
                execution_mode=route_plan.execution_mode,
            )
            active_activation_id = (
                str(active_activation.id) if active_activation is not None else None
            )
            if active_activation_id != route_plan.model_activation_id:
                raise ModelRouteActivationConflictError(
                    details={"current_activation_id": active_activation_id}
                )

            current = _latest_route_plan_model(
                session,
                tenant_id=tenant_uuid,
                task=route_plan.task,
                execution_mode=route_plan.execution_mode,
            )
            current_id = str(current.id) if current is not None else None
            if (
                current_id != expected_current_route_plan_id
                or current_id != route_plan.previous_route_plan_id
            ):
                raise ModelRoutePlanConflictError(details={"current_route_plan_id": current_id})

            model = LLMModelRoutePlanModel(
                id=UUID(route_plan.id),
                tenant_id=tenant_uuid,
                schema_version=route_plan.schema_version,
                task=route_plan.task.value,
                execution_mode=route_plan.execution_mode.value,
                model_activation_id=UUID(route_plan.model_activation_id),
                deployment_id=route_plan.deployment_id,
                previous_route_plan_id=(
                    UUID(route_plan.previous_route_plan_id)
                    if route_plan.previous_route_plan_id is not None
                    else None
                ),
                automatic_cross_model_fallback=route_plan.automatic_cross_model_fallback,
                activated_by=UUID(route_plan.activated_by),
                reason=route_plan.reason,
                idempotency_key=route_plan.idempotency_key,
                request_hash=route_plan.request_hash,
                activated_at=route_plan.activated_at,
            )
            session.add(model)
            session.flush()
            return _route_plan(model), False

    def get_active(
        self,
        *,
        tenant_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ModelRoutePlan | None:
        with tenant_context(tenant_id), self._factory() as session:
            model = _latest_route_plan_model(
                session,
                tenant_id=UUID(tenant_id),
                task=task,
                execution_mode=execution_mode,
            )
        return _route_plan(model) if model is not None else None

    def get(self, *, tenant_id: str, route_plan_id: str) -> ModelRoutePlan | None:
        return self.get_by_id(tenant_id=tenant_id, route_plan_id=route_plan_id)

    def get_by_id(self, *, tenant_id: str, route_plan_id: str) -> ModelRoutePlan | None:
        with tenant_context(tenant_id), self._factory() as session:
            model = session.scalar(
                select(LLMModelRoutePlanModel).where(
                    LLMModelRoutePlanModel.tenant_id == UUID(tenant_id),
                    LLMModelRoutePlanModel.id == UUID(route_plan_id),
                )
            )
        return _route_plan(model) if model is not None else None


def _lock_tenant(session: Session, tenant_id: UUID) -> None:
    found = session.scalar(
        select(TenantModel.id).where(TenantModel.id == tenant_id).with_for_update()
    )
    if found is None:
        raise InconsistentPersistenceStateError("The model route tenant does not exist.")


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


def _latest_route_plan_model(
    session: Session,
    *,
    tenant_id: UUID,
    task: ModelReleaseTask,
    execution_mode: AnalysisExecutionMode,
) -> LLMModelRoutePlanModel | None:
    child = aliased(LLMModelRoutePlanModel)
    return session.scalar(
        select(LLMModelRoutePlanModel)
        .where(
            LLMModelRoutePlanModel.tenant_id == tenant_id,
            LLMModelRoutePlanModel.task == task.value,
            LLMModelRoutePlanModel.execution_mode == execution_mode.value,
            ~select(child.id)
            .where(
                child.tenant_id == LLMModelRoutePlanModel.tenant_id,
                child.task == LLMModelRoutePlanModel.task,
                child.execution_mode == LLMModelRoutePlanModel.execution_mode,
                child.previous_route_plan_id == LLMModelRoutePlanModel.id,
            )
            .exists(),
        )
        .limit(1)
    )


def _route_plan(model: LLMModelRoutePlanModel) -> ModelRoutePlan:
    return ModelRoutePlan(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        schema_version=cast(Literal["model_route_plan/1.0.0"], model.schema_version),
        task=ModelReleaseTask(model.task),
        execution_mode=AnalysisExecutionMode(model.execution_mode),
        model_activation_id=str(model.model_activation_id),
        deployment_id=model.deployment_id,
        previous_route_plan_id=(
            str(model.previous_route_plan_id) if model.previous_route_plan_id is not None else None
        ),
        automatic_cross_model_fallback=cast(Literal[False], model.automatic_cross_model_fallback),
        activated_by=str(model.activated_by),
        reason=model.reason,
        idempotency_key=model.idempotency_key,
        request_hash=model.request_hash,
        activated_at=model.activated_at,
    )


__all__ = ["LLMModelRoutePlanModel", "SQLAlchemyModelRoutePlanRepository"]
