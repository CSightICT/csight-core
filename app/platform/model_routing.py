"""Framework-free, fixed-route contracts for signed LLM releases."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.errors import CSightError
from app.platform.model_activation import (
    ActiveLLMRelease,
    ModelReleaseTask,
    RuntimeLLMIdentityContract,
)

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_DEPLOYMENT_PATTERN = r"^[a-z0-9][a-z0-9._-]{2,127}$"
MODEL_ROUTE_ENFORCEMENT_CONTRACT_VERSION = "model_route_enforcement/1.0.0"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ModelRoutePlan(_Contract):
    """One immutable link from a tenant task to an approved release activation."""

    schema_version: Literal["model_route_plan/1.0.0"] = "model_route_plan/1.0.0"
    id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64)
    task: ModelReleaseTask
    execution_mode: AnalysisExecutionMode
    model_activation_id: str = Field(min_length=1, max_length=64)
    deployment_id: str = Field(pattern=_DEPLOYMENT_PATTERN)
    previous_route_plan_id: str | None = Field(default=None, max_length=64)
    automatic_cross_model_fallback: Literal[False] = False
    activated_by: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=255, repr=False)
    request_hash: str = Field(pattern=_HASH_PATTERN)
    activated_at: datetime

    @field_validator("activated_at")
    @classmethod
    def require_activated_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("activated_at must be timezone-aware")
        return value.astimezone(UTC)


class ResolvedModelRoutePlan(_Contract):
    route_plan: ModelRoutePlan
    active_release: ActiveLLMRelease


class ModelRouteDeploymentIdentity(_Contract):
    """Identity of the model deployment reached by one Worker process."""

    deployment_id: str = Field(pattern=_DEPLOYMENT_PATTERN)
    runtime_identity: RuntimeLLMIdentityContract


class ResolvedPinnedModelRoutePlan(_Contract):
    """A historical route and signed release resolved without consulting current state."""

    route_plan: ModelRoutePlan
    pinned_release: ActiveLLMRelease


class ModelRoutePlanActivationResult(_Contract):
    route_plan: ModelRoutePlan
    idempotent_replay: bool


class ModelRoutePlanConflictError(CSightError):
    code = "MODEL_ROUTE_PLAN_CONFLICT"
    default_message = "The active model route plan changed before activation completed."


class ModelRouteActivationConflictError(CSightError):
    code = "MODEL_ROUTE_ACTIVATION_CONFLICT"
    default_message = "The model release activation is no longer active for this route."


class ActiveModelRoutePlanRequiredError(CSightError):
    code = "ACTIVE_MODEL_ROUTE_PLAN_REQUIRED"
    default_message = "No active model route plan exists for this execution profile."
    retryable: ClassVar[bool] = False


class PinnedModelRoutePlanRequiredError(CSightError):
    code = "PINNED_MODEL_ROUTE_PLAN_REQUIRED"
    default_message = "The analysis stage does not reference an available model route plan."
    retryable: ClassVar[bool] = False


class PinnedModelActivationRequiredError(CSightError):
    code = "PINNED_MODEL_ACTIVATION_REQUIRED"
    default_message = "The model activation pinned by this analysis stage is unavailable."
    retryable: ClassVar[bool] = False


class PinnedModelRoutePlanMismatchError(CSightError):
    code = "PINNED_MODEL_ROUTE_PLAN_MISMATCH"
    default_message = "The pinned model route does not match the analysis execution profile."
    retryable: ClassVar[bool] = False


class ModelRouteDeploymentIdentityMismatchError(CSightError):
    code = "MODEL_ROUTE_DEPLOYMENT_IDENTITY_MISMATCH"
    default_message = "The Worker deployment does not match the pinned model route."
    retryable: ClassVar[bool] = False


__all__ = [
    "MODEL_ROUTE_ENFORCEMENT_CONTRACT_VERSION",
    "ActiveModelRoutePlanRequiredError",
    "ModelRouteActivationConflictError",
    "ModelRouteDeploymentIdentity",
    "ModelRouteDeploymentIdentityMismatchError",
    "ModelRoutePlan",
    "ModelRoutePlanActivationResult",
    "ModelRoutePlanConflictError",
    "PinnedModelActivationRequiredError",
    "PinnedModelRoutePlanMismatchError",
    "PinnedModelRoutePlanRequiredError",
    "ResolvedModelRoutePlan",
    "ResolvedPinnedModelRoutePlan",
]
