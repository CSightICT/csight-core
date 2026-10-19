"""Admin HTTP and composition contracts for immutable model route plans."""

import base64
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.bootstrap.operations as operations_bootstrap
from app.bootstrap.settings import Settings
from app.interface.http import register_exception_handlers
from app.interface.http.operations_services import OperationsServiceContainer
from app.interface.http.routers.operations import router
from app.interface.http.services import Sprint1ServiceContainer
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.errors import AuthenticationRequiredError
from app.platform.model_activation import (
    ActiveLLMRelease,
    LLMReleaseManifest,
    ModelActivationEvent,
    ModelReleaseModeNotAllowedError,
    ModelReleaseTask,
    RegisteredLLMRelease,
    SignedLLMReleaseManifest,
)
from app.platform.model_routing import (
    ActiveModelRoutePlanRequiredError,
    ModelRoutePlan,
    ModelRoutePlanActivationResult,
    ResolvedModelRoutePlan,
)
from app.platform.tenant import Principal, Role
from tests.case_assignment_support import AllowCaseAccess

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 31, 3, 0, tzinfo=UTC)
TENANT_ID = "10000000-0000-4000-8000-000000000001"
ADMIN_ID = "20000000-0000-4000-8000-000000000001"
REVIEWER_ID = "20000000-0000-4000-8000-000000000002"


class _ResolvePrincipal:
    def execute(self, token: str) -> Principal:
        if token not in {"admin-token", "reviewer-token"}:
            raise AuthenticationRequiredError()
        role = Role.ADMIN if token == "admin-token" else Role.REVIEWER
        return Principal(
            user_id=ADMIN_ID if role is Role.ADMIN else REVIEWER_ID,
            tenant_id=TENANT_ID,
            email=f"{role.value.lower()}@example.test",
            display_name=role.value,
            roles=frozenset({role}),
        )


class _ActivateRoute:
    def __init__(self, route_plan: ModelRoutePlan) -> None:
        self.route_plan = route_plan
        self.calls: list[dict[str, object]] = []

    def execute(self, **values: object) -> ModelRoutePlanActivationResult:
        self.calls.append(values)
        return ModelRoutePlanActivationResult(
            route_plan=self.route_plan,
            idempotent_replay=len(self.calls) > 1,
        )


class _RejectMode:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def execute(self, **values: object) -> object:
        self.calls.append(values)
        raise ModelReleaseModeNotAllowedError()


class _GetActiveRoute:
    def __init__(self, resolved: ResolvedModelRoutePlan, *, missing: bool = False) -> None:
        self.resolved = resolved
        self.missing = missing
        self.calls: list[dict[str, object]] = []

    def execute(self, **values: object) -> ResolvedModelRoutePlan:
        self.calls.append(values)
        if self.missing:
            raise ActiveModelRoutePlanRequiredError()
        return self.resolved


def _active_release() -> ActiveLLMRelease:
    digest = "sha256:" + "a" * 64
    task = ModelReleaseTask.POLICY_QUERY_BUILDER_V1
    manifest = LLMReleaseManifest(
        candidate_id="qwen-policy-route",
        package_name="csight-qwen-policy-route",
        package_version="2026.08.31.1",
        task=task,
        artifact="Qwen/Qwen3.8-27B",
        artifact_revision="1" * 40,
        artifact_content_digest=digest,
        runtime_image="vllm/vllm-openai",
        runtime_image_digest=digest,
        dependency_lock_digest=digest,
        sbom_digest=digest,
        served_model_name="csight-qwen-policy",
        model_version="Qwen3.8-27B-INT4",
        prompt_name="policy_query_builder",
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
    signed = SignedLLMReleaseManifest(
        manifest=manifest,
        signing_key_id="release-key-1",
        signature_base64=base64.b64encode(b"s" * 64).decode(),
    )
    release = RegisteredLLMRelease(
        id="release-1",
        tenant_id=TENANT_ID,
        signed_manifest=signed,
        registered_by=ADMIN_ID,
        registered_at=NOW,
    )
    return ActiveLLMRelease(
        release=release,
        activation=ModelActivationEvent(
            id="activation-1",
            tenant_id=TENANT_ID,
            task=task,
            execution_mode=AnalysisExecutionMode.PRIMARY,
            model_release_id=release.id,
            activated_by=ADMIN_ID,
            reason="Qualified policy query release",
            idempotency_key="activate-policy-1",
            request_hash="c" * 64,
            activated_at=NOW,
        ),
    )


def _resolved() -> ResolvedModelRoutePlan:
    active_release = _active_release()
    route_plan = ModelRoutePlan(
        id="route-1",
        tenant_id=TENANT_ID,
        task=active_release.activation.task,
        execution_mode=active_release.activation.execution_mode,
        model_activation_id=active_release.activation.id,
        deployment_id="onprem-4090-primary",
        activated_by=ADMIN_ID,
        reason="Qualified fixed policy route",
        idempotency_key="route-key-1",
        request_hash="d" * 64,
        activated_at=NOW,
    )
    return ResolvedModelRoutePlan(route_plan=route_plan, active_release=active_release)


def _services(
    activate: _ActivateRoute,
    get_active: _GetActiveRoute,
) -> OperationsServiceContainer:
    unused: Any = object()
    return OperationsServiceContainer(
        get_overview=unused,
        get_failures=unused,
        activate_model_route=activate,  # pyright: ignore[reportArgumentType]
        get_active_model_route=get_active,  # pyright: ignore[reportArgumentType]
    )


def _client(
    activate: _ActivateRoute,
    get_active: _GetActiveRoute,
    *,
    configure_operations: bool = True,
) -> TestClient:
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(router)
    unused: Any = object()
    application.state.sprint1_services = Sprint1ServiceContainer(
        authenticate_user=unused,
        resolve_principal=_ResolvePrincipal(),
        create_case=unused,
        list_cases=unused,
        get_case=unused,
        get_case_status_history=unused,
        add_image_evidence=unused,
        list_case_evidence=unused,
        get_evidence_metadata=unused,
        create_evidence_access_url=unused,
        get_case_assignment=unused,
        assign_case=unused,
        authorize_case_access=AllowCaseAccess(),  # pyright: ignore[reportArgumentType]
    )
    if configure_operations:
        application.state.operations_services = _services(activate, get_active)
    return TestClient(application, raise_server_exceptions=False)


def _activation_body() -> dict[str, object]:
    return {
        "task": "POLICY_QUERY_BUILDER_V1",
        "execution_mode": "PRIMARY",
        "model_activation_id": "activation-1",
        "deployment_id": "onprem-4090-primary",
        "expected_current_route_plan_id": None,
        "reason": "Qualified fixed policy route",
    }


def test_admin_route_activation_is_202_then_idempotent_200_and_no_store() -> None:
    resolved = _resolved()
    activate = _ActivateRoute(resolved.route_plan)
    get_active = _GetActiveRoute(resolved)
    client = _client(activate, get_active)
    headers = {"Authorization": "Bearer admin-token", "Idempotency-Key": "route-key-1"}

    first = client.post(
        "/api/v1/operations/model-route-plans/activate",
        json=_activation_body(),
        headers=headers,
    )
    replay = client.post(
        "/api/v1/operations/model-route-plans/activate",
        json=_activation_body(),
        headers=headers,
    )
    active = client.get(
        "/api/v1/operations/model-route-plans/active",
        params={"task": "POLICY_QUERY_BUILDER_V1", "execution_mode": "PRIMARY"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert first.status_code == 202
    assert first.json()["route_plan"]["automatic_cross_model_fallback"] is False
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert active.status_code == 200
    assert active.json()["route_plan"]["model_activation_id"] == "activation-1"
    assert active.json()["active_release"]["activation"]["id"] == "activation-1"
    for response in (first, replay, active):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Pragma"] == "no-cache"
    assert activate.calls[0]["principal"].tenant_id == TENANT_ID  # type: ignore[union-attr]
    assert activate.calls[0]["idempotency_key"] == "route-key-1"


def test_route_endpoints_are_admin_only_fail_closed_and_no_store() -> None:
    resolved = _resolved()
    activate = _ActivateRoute(resolved.route_plan)
    missing = _GetActiveRoute(resolved, missing=True)
    client = _client(activate, missing)

    forbidden = client.post(
        "/api/v1/operations/model-route-plans/activate",
        json=_activation_body(),
        headers={"Authorization": "Bearer reviewer-token", "Idempotency-Key": "blocked"},
    )
    not_found = client.get(
        "/api/v1/operations/model-route-plans/active",
        params={"task": "POLICY_QUERY_BUILDER_V1", "execution_mode": "PRIMARY"},
        headers={"Authorization": "Bearer admin-token"},
    )
    unavailable = _client(activate, missing, configure_operations=False).get(
        "/api/v1/operations/model-route-plans/active",
        params={"task": "POLICY_QUERY_BUILDER_V1", "execution_mode": "PRIMARY"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert forbidden.status_code == 403
    assert activate.calls == []
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "ACTIVE_MODEL_ROUTE_PLAN_REQUIRED"
    assert unavailable.status_code == 503
    for response in (forbidden, not_found, unavailable):
        assert response.headers["Cache-Control"] == "no-store"


def test_model_route_openapi_requires_explicit_route_identity_and_documents_replay() -> None:
    resolved = _resolved()
    schema = cast(
        FastAPI, _client(_ActivateRoute(resolved.route_plan), _GetActiveRoute(resolved)).app
    ).openapi()
    post = schema["paths"]["/api/v1/operations/model-route-plans/activate"]["post"]
    release_post = schema["paths"]["/api/v1/operations/model-releases/{release_id}/activate"][
        "post"
    ]
    get = schema["paths"]["/api/v1/operations/model-route-plans/active"]["get"]

    assert {"200", "202", "403", "409", "422", "503"} <= set(post["responses"])
    assert {"200", "201", "403", "409", "422", "503"} <= set(release_post["responses"])
    idempotency = next(item for item in post["parameters"] if item["name"] == "Idempotency-Key")
    assert idempotency["in"] == "header"
    assert idempotency["required"] is True
    body_ref = post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    body_schema = schema["components"]["schemas"][body_ref.rsplit("/", 1)[-1]]
    assert {
        "task",
        "execution_mode",
        "model_activation_id",
        "deployment_id",
        "reason",
    } <= set(body_schema["required"])
    query_parameters = {item["name"]: item for item in get["parameters"]}
    assert query_parameters["task"]["required"] is True
    assert query_parameters["execution_mode"]["required"] is True


def test_shadow_mode_violation_is_public_409_for_release_and_route() -> None:
    resolved = _resolved()
    client = _client(_ActivateRoute(resolved.route_plan), _GetActiveRoute(resolved))
    release_reject = _RejectMode()
    route_reject = _RejectMode()
    app = cast(FastAPI, client.app)
    services = app.state.operations_services
    unused: Any = object()
    app.state.operations_services = replace(
        services,
        register_model_release=unused,
        activate_model_release=release_reject,
        get_active_model_release=unused,
        activate_model_route=route_reject,
    )
    headers = {"Authorization": "Bearer admin-token", "Idempotency-Key": "mode-blocked"}

    release = client.post(
        "/api/v1/operations/model-releases/release-shadow/activate",
        json={
            "execution_mode": "PRIMARY",
            "expected_current_activation_id": None,
            "reason": "Must remain Shadow",
        },
        headers=headers,
    )
    route = client.post(
        "/api/v1/operations/model-route-plans/activate",
        json=_activation_body(),
        headers=headers,
    )

    for response in (release, route):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "MODEL_RELEASE_MODE_NOT_ALLOWED"
        assert response.headers["Cache-Control"] == "no-store"
    assert len(release_reject.calls) == 1
    assert len(route_reject.calls) == 1


def test_operations_composition_reuses_activation_repository_and_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = object()
    activation_repository = object()
    route_repository = object()
    verifier = object()

    def _engine(settings: object) -> object:
        del settings
        return object()

    def _session_factory(engine: object) -> object:
        del engine
        return session_factory

    def _unused_repository(factory: object) -> object:
        del factory
        return object()

    def _activation_repository(factory: object) -> object:
        del factory
        return activation_repository

    def _route_repository(factory: object) -> object:
        del factory
        return route_repository

    def _configured(settings: object) -> bool:
        del settings
        return True

    def _verifier(**kwargs: object) -> object:
        del kwargs
        return verifier

    monkeypatch.setattr(operations_bootstrap, "get_engine", _engine)
    monkeypatch.setattr(
        operations_bootstrap,
        "create_session_factory",
        _session_factory,
    )
    monkeypatch.setattr(
        operations_bootstrap,
        "SQLAlchemyOperationsReadRepository",
        _unused_repository,
    )
    monkeypatch.setattr(
        operations_bootstrap,
        "SQLAlchemyOperationalFailureRepository",
        _unused_repository,
    )
    monkeypatch.setattr(
        operations_bootstrap,
        "SQLAlchemyModelActivationRepository",
        _activation_repository,
    )
    monkeypatch.setattr(
        operations_bootstrap,
        "SQLAlchemyModelRoutePlanRepository",
        _route_repository,
    )
    monkeypatch.setattr(
        operations_bootstrap,
        "model_activation_is_configured",
        _configured,
    )
    monkeypatch.setattr(
        operations_bootstrap.Ed25519ModelReleaseSignatureVerifier,
        "from_file",
        _verifier,
    )
    settings = cast(
        Settings,
        SimpleNamespace(
            model_release_signing_public_key_file=Path("public.pem"),
            model_release_signing_key_id="release-key-1",
            signed_intake_is_configured=False,
            signed_intake_sources={},
            oidc_is_configured=False,
            oidc_group_mappings={},
            sensitive_payload_retention_policy_version="development/30d",
            sensitive_payload_retention_days=30,
            privacy_lifecycle_automation_enabled=False,
            privacy_lifecycle_tenant_id=None,
        ),
    )

    services = operations_bootstrap.build_operations_services(settings)

    assert services.activate_model_release is not None
    assert services.activate_model_route is not None
    assert services.get_active_model_route is not None
    assert (
        services.activate_model_release._repository  # pyright: ignore[reportPrivateUsage]
        is activation_repository
    )
    assert (
        services.activate_model_route._activation_repository  # pyright: ignore[reportPrivateUsage]
        is activation_repository
    )
    assert (
        services.activate_model_release._signature_verifier  # pyright: ignore[reportPrivateUsage]
        is verifier
    )
    assert (
        services.activate_model_route._signature_verifier  # pyright: ignore[reportPrivateUsage]
        is verifier
    )
