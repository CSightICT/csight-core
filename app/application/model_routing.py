"""Admin activation and fail-closed resolution for fixed LLM route plans."""

from __future__ import annotations

import hashlib
import json
import re

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.errors import ForbiddenError, IdempotencyKeyReusedError, ValidationError
from app.platform.model_activation import (
    ActiveModelReleaseRequiredError,
    ModelReleaseIdentityMismatchError,
    ModelReleaseSignatureInvalidError,
    ModelReleaseTask,
    RuntimeLLMIdentity,
)
from app.platform.model_routing import (
    ActiveModelRoutePlanRequiredError,
    ModelRouteActivationConflictError,
    ModelRouteDeploymentIdentity,
    ModelRouteDeploymentIdentityMismatchError,
    ModelRoutePlan,
    ModelRoutePlanActivationResult,
    PinnedModelActivationRequiredError,
    PinnedModelRoutePlanMismatchError,
    PinnedModelRoutePlanRequiredError,
    ResolvedModelRoutePlan,
    ResolvedPinnedModelRoutePlan,
)
from app.platform.tenant import Principal, Role
from app.ports.model_activation import (
    ModelActivationRepository,
    ModelReleaseSignatureVerifier,
)
from app.ports.model_routing import ModelRoutePlanRepository
from app.ports.runtime import Clock, IdGenerator

_DEPLOYMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")


class ActivateModelRoutePlan:
    def __init__(
        self,
        *,
        route_repository: ModelRoutePlanRepository,
        activation_repository: ModelActivationRepository,
        signature_verifier: ModelReleaseSignatureVerifier,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._route_repository = route_repository
        self._activation_repository = activation_repository
        self._signature_verifier = signature_verifier
        self._clock = clock
        self._id_generator = id_generator

    def execute(
        self,
        *,
        principal: Principal,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
        model_activation_id: str,
        deployment_id: str,
        expected_current_route_plan_id: str | None,
        reason: str,
        idempotency_key: str,
    ) -> ModelRoutePlanActivationResult:
        _require_admin(principal)
        normalized_activation_id = model_activation_id.strip()
        normalized_deployment_id = deployment_id.strip()
        normalized_reason = reason.strip()
        normalized_key = idempotency_key.strip()
        normalized_expected_id = (
            expected_current_route_plan_id.strip()
            if expected_current_route_plan_id is not None
            else None
        )
        if not 1 <= len(normalized_activation_id) <= 64:
            raise ValidationError("Model activation ID must contain between 1 and 64 characters.")
        if _DEPLOYMENT_PATTERN.fullmatch(normalized_deployment_id) is None:
            raise ValidationError("Deployment ID has an invalid format.")
        if normalized_expected_id is not None and not 1 <= len(normalized_expected_id) <= 64:
            raise ValidationError(
                "Expected route plan ID must contain between 1 and 64 characters."
            )
        if not 1 <= len(normalized_reason) <= 1000:
            raise ValidationError("Model route reason must contain between 1 and 1000 characters.")
        if not 1 <= len(normalized_key) <= 255:
            raise ValidationError("Idempotency-Key must contain between 1 and 255 characters.")

        request_hash = _route_request_hash(
            task=task,
            execution_mode=execution_mode,
            model_activation_id=normalized_activation_id,
            deployment_id=normalized_deployment_id,
            expected_current_route_plan_id=normalized_expected_id,
            reason=normalized_reason,
        )
        replay = self._route_repository.get_by_idempotency_key(
            tenant_id=principal.tenant_id,
            task=task,
            execution_mode=execution_mode,
            idempotency_key=normalized_key,
        )
        if replay is not None:
            if replay.request_hash != request_hash:
                raise IdempotencyKeyReusedError()
            return ModelRoutePlanActivationResult(route_plan=replay, idempotent_replay=True)

        active_release = self._activation_repository.get_active(
            tenant_id=principal.tenant_id,
            task=task,
            execution_mode=execution_mode,
        )
        if active_release is None:
            raise ActiveModelReleaseRequiredError()
        if active_release.activation.id != normalized_activation_id:
            raise ModelRouteActivationConflictError(
                details={"current_activation_id": active_release.activation.id}
            )
        if not self._signature_verifier.verify(active_release.release.signed_manifest):
            raise ModelReleaseSignatureInvalidError()

        current = self._route_repository.get_active(
            tenant_id=principal.tenant_id,
            task=task,
            execution_mode=execution_mode,
        )
        previous_id = current.id if current is not None else None
        route_plan = ModelRoutePlan(
            id=self._id_generator.new_id(),
            tenant_id=principal.tenant_id,
            task=task,
            execution_mode=execution_mode,
            model_activation_id=normalized_activation_id,
            deployment_id=normalized_deployment_id,
            previous_route_plan_id=previous_id,
            activated_by=principal.user_id,
            reason=normalized_reason,
            idempotency_key=normalized_key,
            request_hash=request_hash,
            activated_at=self._clock.now(),
        )
        activated, idempotent_replay = self._route_repository.activate(
            route_plan=route_plan,
            expected_current_route_plan_id=normalized_expected_id,
        )
        return ModelRoutePlanActivationResult(
            route_plan=activated,
            idempotent_replay=idempotent_replay,
        )


class ResolveActiveModelRoutePlan:
    """Resolve only a route that still references the active signed release."""

    def __init__(
        self,
        *,
        route_repository: ModelRoutePlanRepository,
        activation_repository: ModelActivationRepository,
        signature_verifier: ModelReleaseSignatureVerifier,
    ) -> None:
        self._route_repository = route_repository
        self._activation_repository = activation_repository
        self._signature_verifier = signature_verifier

    def execute(
        self,
        *,
        tenant_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ResolvedModelRoutePlan:
        route_plan = self._route_repository.get_active(
            tenant_id=tenant_id,
            task=task,
            execution_mode=execution_mode,
        )
        if route_plan is None:
            raise ActiveModelRoutePlanRequiredError()
        active_release = self._activation_repository.get_active(
            tenant_id=tenant_id,
            task=task,
            execution_mode=execution_mode,
        )
        if active_release is None:
            raise ActiveModelReleaseRequiredError()
        if route_plan.model_activation_id != active_release.activation.id:
            raise ModelRouteActivationConflictError(
                details={"current_activation_id": active_release.activation.id}
            )
        if not self._signature_verifier.verify(active_release.release.signed_manifest):
            raise ModelReleaseSignatureInvalidError()
        return ResolvedModelRoutePlan(
            route_plan=route_plan,
            active_release=active_release,
        )


class GetActiveModelRoutePlan:
    def __init__(self, resolver: ResolveActiveModelRoutePlan) -> None:
        self._resolver = resolver

    def execute(
        self,
        *,
        principal: Principal,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ResolvedModelRoutePlan:
        _require_admin(principal)
        return self._resolver.execute(
            tenant_id=principal.tenant_id,
            task=task,
            execution_mode=execution_mode,
        )


class ResolvePinnedModelRoutePlan:
    """Validate a stage's immutable route without reading either current pointer."""

    def __init__(
        self,
        *,
        route_repository: ModelRoutePlanRepository,
        activation_repository: ModelActivationRepository,
        signature_verifier: ModelReleaseSignatureVerifier,
        deployment_identity: ModelRouteDeploymentIdentity,
    ) -> None:
        self._route_repository = route_repository
        self._activation_repository = activation_repository
        self._signature_verifier = signature_verifier
        self._deployment_identity = deployment_identity

    def execute(
        self,
        *,
        tenant_id: str,
        route_plan_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ResolvedPinnedModelRoutePlan:
        route_plan = self._route_repository.get_by_id(
            tenant_id=tenant_id,
            route_plan_id=route_plan_id,
        )
        if route_plan is None:
            raise PinnedModelRoutePlanRequiredError()
        if (
            route_plan.tenant_id != tenant_id
            or route_plan.task is not task
            or route_plan.execution_mode is not execution_mode
        ):
            raise PinnedModelRoutePlanMismatchError()
        if route_plan.deployment_id != self._deployment_identity.deployment_id:
            raise ModelRouteDeploymentIdentityMismatchError(
                details={"expected_deployment_id": route_plan.deployment_id}
            )
        pinned_release = self._activation_repository.get_by_activation_id(
            tenant_id=tenant_id,
            activation_id=route_plan.model_activation_id,
        )
        if pinned_release is None:
            raise PinnedModelActivationRequiredError()
        activation = pinned_release.activation
        manifest = pinned_release.release.signed_manifest.manifest
        if (
            activation.id != route_plan.model_activation_id
            or activation.tenant_id != tenant_id
            or activation.task is not task
            or activation.execution_mode is not execution_mode
            or manifest.task is not task
            or activation.model_release_id != pinned_release.release.id
        ):
            raise PinnedModelRoutePlanMismatchError()
        if not self._signature_verifier.verify(pinned_release.release.signed_manifest):
            raise ModelReleaseSignatureInvalidError()
        expected_runtime_identity = RuntimeLLMIdentity.model_validate(
            {field: getattr(manifest, field) for field in RuntimeLLMIdentity.model_fields}
        )
        if self._deployment_identity.runtime_identity != expected_runtime_identity:
            raise ModelReleaseIdentityMismatchError()
        return ResolvedPinnedModelRoutePlan(
            route_plan=route_plan,
            pinned_release=pinned_release,
        )


def _require_admin(principal: Principal) -> None:
    if Role.ADMIN not in principal.roles:
        raise ForbiddenError()


def _route_request_hash(
    *,
    task: ModelReleaseTask,
    execution_mode: AnalysisExecutionMode,
    model_activation_id: str,
    deployment_id: str,
    expected_current_route_plan_id: str | None,
    reason: str,
) -> str:
    encoded = json.dumps(
        {
            "task": task.value,
            "execution_mode": execution_mode.value,
            "model_activation_id": model_activation_id,
            "deployment_id": deployment_id,
            "expected_current_route_plan_id": expected_current_route_plan_id,
            "reason": reason,
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ActivateModelRoutePlan",
    "GetActiveModelRoutePlan",
    "ResolveActiveModelRoutePlan",
    "ResolvePinnedModelRoutePlan",
]
