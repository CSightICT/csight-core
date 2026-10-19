"""Application contracts for fixed, signed, tenant-scoped model routing."""

import base64
from datetime import UTC, datetime

import pytest

from app.application.model_routing import (
    ActivateModelRoutePlan,
    GetActiveModelRoutePlan,
    ResolveActiveModelRoutePlan,
    ResolvePinnedModelRoutePlan,
)
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.errors import ForbiddenError, IdempotencyKeyReusedError
from app.platform.model_activation import (
    ActiveLLMRelease,
    LLMReleaseManifest,
    LLMReleaseManifestContract,
    ModelActivationEvent,
    ModelReleaseIdentityMismatchError,
    ModelReleaseTask,
    RegisteredLLMRelease,
    RuntimeLLMIdentity,
    SignedLLMReleaseManifest,
)
from app.platform.model_routing import (
    ActiveModelRoutePlanRequiredError,
    ModelRouteActivationConflictError,
    ModelRouteDeploymentIdentity,
    ModelRouteDeploymentIdentityMismatchError,
    ModelRoutePlan,
    ModelRoutePlanConflictError,
)
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 31, 2, 0, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Ids:
    def __init__(self) -> None:
        self.value = 0

    def new_id(self) -> str:
        self.value += 1
        return f"route-{self.value}"


class _Verifier:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid

    def verify(self, value: SignedLLMReleaseManifest) -> bool:
        del value
        return self.valid


class _ActivationRepository:
    def __init__(self, active: ActiveLLMRelease | None) -> None:
        self.active = active
        self.by_id = {active.activation.id: active} if active is not None else {}
        self.calls = 0

    def get_active(self, **_: object) -> ActiveLLMRelease | None:
        self.calls += 1
        return self.active

    def get_by_activation_id(self, *, activation_id: str, **_: object) -> ActiveLLMRelease | None:
        return self.by_id.get(activation_id)


class _RouteRepository:
    def __init__(self, active: ModelRoutePlan | None = None) -> None:
        self.active = active
        self.by_key: dict[str, ModelRoutePlan] = {}
        self.by_id: dict[str, ModelRoutePlan] = {}
        if active is not None:
            self.by_id[active.id] = active

    def get_by_idempotency_key(self, *, idempotency_key: str, **_: object) -> ModelRoutePlan | None:
        return self.by_key.get(idempotency_key)

    def activate(
        self,
        *,
        route_plan: ModelRoutePlan,
        expected_current_route_plan_id: str | None,
    ) -> tuple[ModelRoutePlan, bool]:
        replay = self.by_key.get(route_plan.idempotency_key)
        if replay is not None:
            if replay.request_hash != route_plan.request_hash:
                raise IdempotencyKeyReusedError()
            return replay, True
        current_id = self.active.id if self.active is not None else None
        if current_id != expected_current_route_plan_id:
            raise ModelRoutePlanConflictError()
        self.active = route_plan
        self.by_key[route_plan.idempotency_key] = route_plan
        self.by_id[route_plan.id] = route_plan
        return route_plan, False

    def get_active(self, **_: object) -> ModelRoutePlan | None:
        return self.active

    def get(self, *, route_plan_id: str, **_: object) -> ModelRoutePlan | None:
        return self.by_id.get(route_plan_id)

    def get_by_id(self, *, route_plan_id: str, **_: object) -> ModelRoutePlan | None:
        return self.by_id.get(route_plan_id)


def _principal(role: Role = Role.ADMIN) -> Principal:
    return Principal(
        user_id="admin-1" if role is Role.ADMIN else "reviewer-1",
        tenant_id="tenant-1",
        email=f"{role.value.lower()}@example.test",
        display_name=role.value,
        roles=frozenset({role}),
    )


def _manifest(task: ModelReleaseTask) -> LLMReleaseManifest:
    digest = "sha256:" + "a" * 64
    return LLMReleaseManifest(
        candidate_id="qwen-route-candidate",
        package_name="csight-qwen-route",
        package_version="2026.08.31.1",
        task=task,
        artifact="Qwen/Qwen3.8-27B",
        artifact_revision="1" * 40,
        artifact_content_digest=digest,
        runtime_image="vllm/vllm-openai",
        runtime_image_digest=digest,
        dependency_lock_digest=digest,
        sbom_digest=digest,
        served_model_name="csight-qwen-route",
        model_version="Qwen3.8-27B-INT4",
        prompt_name=task.value.lower(),
        prompt_version="1.0.0",
        prompt_content_hash="b" * 64,
        input_schema_version="1.0",
        output_schema_version="1.0",
        precision="awq-int4",
        max_context_tokens=8192,
        max_num_sequences=1,
        gpu_memory_utilization=0.9,
        kv_cache_dtype="auto",
        qualification_dataset_digest=digest,
        qualification_result_digest=digest,
        candidate_matrix_digest=digest,
        candidate_assessment_digest=digest,
        qualified_at=NOW,
    )


def _active(
    task: ModelReleaseTask = ModelReleaseTask.POLICY_QUERY_BUILDER_V1,
    *,
    activation_id: str = "activation-1",
) -> ActiveLLMRelease:
    signed = SignedLLMReleaseManifest(
        manifest=_manifest(task),
        signing_key_id="release-key-1",
        signature_base64=base64.b64encode(b"s" * 64).decode(),
    )
    release = RegisteredLLMRelease(
        id="release-1",
        tenant_id="tenant-1",
        signed_manifest=signed,
        registered_by="admin-1",
        registered_at=NOW,
    )
    return ActiveLLMRelease(
        release=release,
        activation=ModelActivationEvent(
            id=activation_id,
            tenant_id="tenant-1",
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
            model_release_id=release.id,
            activated_by="admin-1",
            reason="Qualified release",
            idempotency_key=f"activate-{activation_id}",
            request_hash="c" * 64,
            activated_at=NOW,
        ),
    )


def _deployment_identity(
    manifest: LLMReleaseManifestContract,
    *,
    deployment_id: str = "onprem-4090-primary",
) -> ModelRouteDeploymentIdentity:
    if not isinstance(manifest, LLMReleaseManifest):
        raise TypeError("legacy deployment fixture requires a v1 manifest")
    return ModelRouteDeploymentIdentity(
        deployment_id=deployment_id,
        runtime_identity=RuntimeLLMIdentity.model_validate(
            {field: getattr(manifest, field) for field in RuntimeLLMIdentity.model_fields}
        ),
    )


def _service(
    routes: _RouteRepository,
    activations: _ActivationRepository,
    *,
    verifier: _Verifier | None = None,
) -> ActivateModelRoutePlan:
    return ActivateModelRoutePlan(
        route_repository=routes,
        activation_repository=activations,  # type: ignore[arg-type]
        signature_verifier=verifier or _Verifier(),
        clock=_Clock(),
        id_generator=_Ids(),
    )


@pytest.mark.parametrize("task", list(ModelReleaseTask))
def test_all_supported_llm_tasks_have_a_release_contract(task: ModelReleaseTask) -> None:
    assert _manifest(task).task is task


def test_admin_activates_fixed_route_and_replay_is_side_effect_free() -> None:
    task = ModelReleaseTask.POLICY_QUERY_BUILDER_V1
    active = _active(task)
    activations = _ActivationRepository(active)
    routes = _RouteRepository()
    service = _service(routes, activations)

    first = service.execute(
        principal=_principal(),
        task=task,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        model_activation_id=active.activation.id,
        deployment_id="onprem-4090-primary",
        expected_current_route_plan_id=None,
        reason="Qualified route for policy retrieval",
        idempotency_key="route-key-1",
    )
    calls_after_first = activations.calls
    replay = service.execute(
        principal=_principal(),
        task=task,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        model_activation_id=active.activation.id,
        deployment_id="onprem-4090-primary",
        expected_current_route_plan_id=None,
        reason="Qualified route for policy retrieval",
        idempotency_key="route-key-1",
    )

    assert first.idempotent_replay is False
    assert first.route_plan.automatic_cross_model_fallback is False
    assert first.route_plan.previous_route_plan_id is None
    assert replay.idempotent_replay is True
    assert replay.route_plan.id == first.route_plan.id
    assert activations.calls == calls_after_first

    with pytest.raises(IdempotencyKeyReusedError):
        service.execute(
            principal=_principal(),
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
            model_activation_id=active.activation.id,
            deployment_id="onprem-4090-secondary",
            expected_current_route_plan_id=None,
            reason="Different request",
            idempotency_key="route-key-1",
        )


def test_route_activation_is_admin_only_and_cas_bound_to_active_release() -> None:
    task = ModelReleaseTask.GROUNDED_POLICY_EXPLANATION_V1
    active = _active(task)
    activations = _ActivationRepository(active)
    routes = _RouteRepository()
    service = _service(routes, activations)
    with pytest.raises(ForbiddenError):
        service.execute(
            principal=_principal(Role.REVIEWER),
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
            model_activation_id=active.activation.id,
            deployment_id="onprem-4090-explain",
            expected_current_route_plan_id=None,
            reason="Grounded explanation route",
            idempotency_key="route-key-2",
        )
    with pytest.raises(ModelRouteActivationConflictError):
        service.execute(
            principal=_principal(),
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
            model_activation_id="stale-activation",
            deployment_id="onprem-4090-explain",
            expected_current_route_plan_id=None,
            reason="Grounded explanation route",
            idempotency_key="route-key-2",
        )


def test_resolution_fails_closed_when_route_or_active_activation_is_stale() -> None:
    task = ModelReleaseTask.POLICY_QUERY_BUILDER_V1
    active = _active(task)
    routes = _RouteRepository()
    resolver = ResolveActiveModelRoutePlan(
        route_repository=routes,
        activation_repository=_ActivationRepository(active),  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
    )

    with pytest.raises(ActiveModelRoutePlanRequiredError):
        resolver.execute(
            tenant_id="tenant-1",
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
        )

    result = _service(routes, _ActivationRepository(active)).execute(
        principal=_principal(),
        task=task,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        model_activation_id=active.activation.id,
        deployment_id="onprem-4090-primary",
        expected_current_route_plan_id=None,
        reason="Qualified route",
        idempotency_key="route-key-3",
    )
    assert (
        resolver.execute(
            tenant_id="tenant-1",
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
        ).route_plan
        == result.route_plan
    )

    stale_resolver = ResolveActiveModelRoutePlan(
        route_repository=routes,
        activation_repository=_ActivationRepository(_active(task, activation_id="activation-2")),  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
    )
    with pytest.raises(ModelRouteActivationConflictError):
        stale_resolver.execute(
            tenant_id="tenant-1",
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
        )

    with pytest.raises(ForbiddenError):
        GetActiveModelRoutePlan(resolver).execute(
            principal=_principal(Role.REVIEWER),
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
        )


def test_pinned_resolution_uses_historical_route_activation_and_deployment() -> None:
    task = ModelReleaseTask.POLICY_QUERY_BUILDER_V1
    historical = _active(task, activation_id="activation-1")
    current = _active(task, activation_id="activation-2")
    route = ModelRoutePlan(
        id="route-1",
        tenant_id="tenant-1",
        task=task,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        model_activation_id=historical.activation.id,
        deployment_id="onprem-4090-primary",
        activated_by="admin-1",
        reason="Pinned historical route",
        idempotency_key="route-key-historical",
        request_hash="e" * 64,
        activated_at=NOW,
    )
    routes = _RouteRepository(route)
    activations = _ActivationRepository(current)
    activations.by_id[historical.activation.id] = historical
    resolver = ResolvePinnedModelRoutePlan(
        route_repository=routes,
        activation_repository=activations,  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
        deployment_identity=_deployment_identity(historical.release.signed_manifest.manifest),
    )

    resolved = resolver.execute(
        tenant_id="tenant-1",
        route_plan_id=route.id,
        task=task,
        execution_mode=AnalysisExecutionMode.PRIMARY,
    )

    assert resolved.route_plan == route
    assert resolved.pinned_release.activation.id == "activation-1"
    assert activations.active is current

    mismatched = ResolvePinnedModelRoutePlan(
        route_repository=routes,
        activation_repository=activations,  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
        deployment_identity=_deployment_identity(
            historical.release.signed_manifest.manifest,
            deployment_id="onprem-4090-secondary",
        ),
    )
    with pytest.raises(ModelRouteDeploymentIdentityMismatchError):
        mismatched.execute(
            tenant_id="tenant-1",
            route_plan_id=route.id,
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
        )

    wrong_runtime = _deployment_identity(historical.release.signed_manifest.manifest).model_copy(
        update={
            "runtime_identity": _deployment_identity(
                historical.release.signed_manifest.manifest
            ).runtime_identity.model_copy(update={"model_version": "wrong-version"})
        }
    )
    with pytest.raises(ModelReleaseIdentityMismatchError):
        ResolvePinnedModelRoutePlan(
            route_repository=routes,
            activation_repository=activations,  # type: ignore[arg-type]
            signature_verifier=_Verifier(),
            deployment_identity=wrong_runtime,
        ).execute(
            tenant_id="tenant-1",
            route_plan_id=route.id,
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
        )
