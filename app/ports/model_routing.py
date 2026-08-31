"""Ports for append-only, tenant-scoped LLM route plans."""

from typing import Protocol

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.model_activation import ModelReleaseTask
from app.platform.model_routing import (
    ModelRoutePlan,
    ResolvedModelRoutePlan,
    ResolvedPinnedModelRoutePlan,
)


class ModelRoutePlanRepository(Protocol):
    def get_by_idempotency_key(
        self,
        *,
        tenant_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
        idempotency_key: str,
    ) -> ModelRoutePlan | None: ...

    def activate(
        self,
        *,
        route_plan: ModelRoutePlan,
        expected_current_route_plan_id: str | None,
    ) -> tuple[ModelRoutePlan, bool]: ...

    def get_active(
        self,
        *,
        tenant_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ModelRoutePlan | None: ...

    def get(
        self,
        *,
        tenant_id: str,
        route_plan_id: str,
    ) -> ModelRoutePlan | None: ...

    def get_by_id(
        self,
        *,
        tenant_id: str,
        route_plan_id: str,
    ) -> ModelRoutePlan | None: ...


class ActiveModelRouteResolver(Protocol):
    def execute(
        self,
        *,
        tenant_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ResolvedModelRoutePlan: ...


class PinnedModelRouteExecutionGuard(Protocol):
    def execute(
        self,
        *,
        tenant_id: str,
        route_plan_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ResolvedPinnedModelRoutePlan: ...


__all__ = [
    "ActiveModelRouteResolver",
    "ModelRoutePlanRepository",
    "PinnedModelRouteExecutionGuard",
]
