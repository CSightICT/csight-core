"""Admin-only, PII-free onboarding-readiness contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.onboarding_readiness import (
    GetOnboardingReadiness,
    OnboardingReadinessConfiguration,
)
from app.bootstrap.operations import onboarding_readiness_configuration
from app.bootstrap.settings import Settings
from app.interface.http.dependencies import provide_current_principal
from app.interface.http.operations_services import OperationsServiceContainer
from app.interface.http.routers.operations import router
from app.platform.errors import ForbiddenError
from app.platform.onboarding_readiness import (
    OnboardingGateCode,
    OnboardingGateStatus,
    OnboardingReadinessFacts,
)
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 31, 10, 30, tzinfo=UTC)
TENANT_ID = str(uuid4())
USER_ID = str(uuid4())
ACTOR_ID = str(uuid4())
TENANT_SLUG = "private-customer-slug"


class _FixedClock:
    def now(self) -> datetime:
        return NOW


class _Repository:
    def __init__(self, facts: OnboardingReadinessFacts) -> None:
        self.facts = facts
        self.calls: list[dict[str, object]] = []

    def get_facts(
        self,
        *,
        tenant_id: str,
        configured_signed_actor_ids: tuple[str, ...],
        as_of_date: date,
    ) -> OnboardingReadinessFacts:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "configured_signed_actor_ids": configured_signed_actor_ids,
                "as_of_date": as_of_date,
            }
        )
        return self.facts


def _principal(role: Role = Role.ADMIN) -> Principal:
    return Principal(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        email="private-admin@example.test",
        display_name="Private Administrator",
        roles=frozenset({role}),
    )


def _facts(
    *,
    active: bool = True,
    admins: int = 1,
    reviewers: int = 1,
    actors: int = 1,
    indexes: int = 1,
    rule_sets: int = 1,
    routes: int = 3,
) -> OnboardingReadinessFacts:
    return OnboardingReadinessFacts(
        tenant_slug=TENANT_SLUG,
        tenant_is_active=active,
        active_admin_count=admins,
        active_reviewer_count=reviewers,
        configured_no_role_actor_count=actors,
        active_policy_index_count=indexes,
        active_rule_set_count=rule_sets,
        active_primary_model_route_count=routes,
    )


def _configuration() -> OnboardingReadinessConfiguration:
    return OnboardingReadinessConfiguration(
        signed_actor_ids_by_tenant={TENANT_ID: (ACTOR_ID,)},
        retention_policy_explicit=True,
        retention_automation_tenant_id=TENANT_ID,
        oidc_tenant_slugs=frozenset({TENANT_SLUG}),
        model_route_runtime_complete=True,
    )


def _service(
    repository: _Repository,
    configuration: OnboardingReadinessConfiguration | None = None,
) -> GetOnboardingReadiness:
    return GetOnboardingReadiness(
        repository=repository,
        configuration=configuration or _configuration(),
        clock=_FixedClock(),
    )


def _client(
    *,
    principal: Principal,
    service: GetOnboardingReadiness | None,
) -> TestClient:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[provide_current_principal] = lambda: principal
    if service is not None:
        unused: Any = object()
        application.state.operations_services = OperationsServiceContainer(
            get_overview=unused,
            get_failures=unused,
            get_onboarding_readiness=service,
        )
    return TestClient(application, raise_server_exceptions=False)


def _assert_public_contract_has_no_identifiers(value: object) -> None:
    serialized = str(value)
    for private_value in (
        TENANT_ID,
        USER_ID,
        ACTOR_ID,
        TENANT_SLUG,
        "private-admin@example.test",
        "Private Administrator",
    ):
        assert private_value not in serialized
    if isinstance(value, dict):
        assert not ({"tenant_id", "user_id", "actor_user_id", "tenant_slug"} & value.keys())
        for item in value.values():
            _assert_public_contract_has_no_identifiers(item)
    elif isinstance(value, list):
        for item in value:
            _assert_public_contract_has_no_identifiers(item)


def test_all_six_required_gates_must_pass_for_pilot_ready() -> None:
    repository = _Repository(_facts())

    result = _service(repository).execute(principal=_principal())

    assert result.pilot_ready is True
    assert {gate.code for gate in result.gates} == set(OnboardingGateCode)
    assert all(gate.status is OnboardingGateStatus.PASS for gate in result.gates)
    assert repository.calls == [
        {
            "tenant_id": TENANT_ID,
            "configured_signed_actor_ids": (ACTOR_ID,),
            "as_of_date": NOW.date(),
        }
    ]
    _assert_public_contract_has_no_identifiers(result.model_dump(mode="json"))


def test_unconfigured_customer_source_and_models_fail_closed_without_identifiers() -> None:
    repository = _Repository(_facts(actors=0, routes=0))
    configuration = OnboardingReadinessConfiguration(
        retention_policy_explicit=True,
        retention_automation_tenant_id=TENANT_ID,
        oidc_tenant_slugs=frozenset({TENANT_SLUG}),
    )

    result = _service(repository, configuration).execute(principal=_principal())
    statuses = {gate.code: gate.status for gate in result.gates}

    assert result.pilot_ready is False
    assert statuses[OnboardingGateCode.SIGNED_INTAKE_SOURCE] is OnboardingGateStatus.FAIL
    assert statuses[OnboardingGateCode.PRIMARY_MODEL_ROUTES] is OnboardingGateStatus.FAIL
    _assert_public_contract_has_no_identifiers(result.model_dump(mode="json"))


def test_three_database_routes_still_fail_until_every_runtime_path_enforces_them() -> None:
    repository = _Repository(_facts(routes=3))
    configuration = _configuration().model_copy(update={"model_route_runtime_complete": False})

    result = _service(repository, configuration).execute(principal=_principal())
    model_gate = next(
        gate for gate in result.gates if gate.code is OnboardingGateCode.PRIMARY_MODEL_ROUTES
    )

    assert result.pilot_ready is False
    assert model_gate.status is OnboardingGateStatus.FAIL
    assert "runtime enforcement" in model_gate.description


def test_inactive_tenant_cannot_be_reported_ready_even_when_every_artifact_exists() -> None:
    repository = _Repository(_facts(active=False))

    result = _service(repository).execute(principal=_principal())

    assert result.pilot_ready is False
    assert all(gate.status is OnboardingGateStatus.FAIL for gate in result.gates)
    assert all("Activate this tenant" in gate.description for gate in result.gates)


def test_non_admin_is_rejected_before_any_tenant_read() -> None:
    repository = _Repository(_facts())

    with pytest.raises(ForbiddenError):
        _service(repository).execute(principal=_principal(Role.REVIEWER))

    assert repository.calls == []


def test_http_contract_is_admin_only_no_store_and_pii_free() -> None:
    repository = _Repository(_facts())
    client = _client(principal=_principal(), service=_service(repository))

    response = client.get("/api/v1/operations/onboarding-readiness")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.json()["pilot_ready"] is True
    assert len(response.json()["gates"]) == 6
    assert set(response.json()) == {"pilot_ready", "gates"}
    assert all(set(gate) == {"code", "status", "description"} for gate in response.json()["gates"])
    _assert_public_contract_has_no_identifiers(response.json())


def test_http_contract_returns_403_for_reviewer_and_503_when_unconfigured() -> None:
    repository = _Repository(_facts())
    reviewer = _client(
        principal=_principal(Role.REVIEWER),
        service=_service(repository),
    ).get("/api/v1/operations/onboarding-readiness")
    unavailable = _client(principal=_principal(), service=None).get(
        "/api/v1/operations/onboarding-readiness"
    )

    assert reviewer.status_code == 403
    assert unavailable.status_code == 503
    assert repository.calls == []


def test_local_implicit_retention_defaults_do_not_count_as_explicit_onboarding() -> None:
    configuration = onboarding_readiness_configuration(Settings.model_construct())

    assert configuration.retention_policy_explicit is False
    assert configuration.retention_automation_tenant_id is None
    assert configuration.signed_actor_ids_by_tenant == {}
    assert configuration.oidc_tenant_slugs == frozenset()
    assert configuration.model_route_runtime_complete is False
