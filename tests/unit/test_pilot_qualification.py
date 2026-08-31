"""Frozen limited-pilot qualification thresholds."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.pilot_readiness import GetPilotReadiness
from app.bootstrap.settings import Settings
from app.interface.http.dependencies import provide_current_principal
from app.interface.http.operations_services import OperationsServiceContainer
from app.interface.http.routers.operations import router
from app.platform.onboarding_readiness import (
    OnboardingGateCode,
    OnboardingGateStatus,
    OnboardingReadiness,
    OnboardingReadinessGate,
)
from app.platform.pilot_qualification import (
    GateStatus,
    PilotQualificationEvidence,
    assess_limited_pilot,
)
from app.platform.pilot_readiness import (
    PilotQualificationEvidenceArtifact,
    PilotReadinessGateStatus,
)
from app.platform.tenant import Principal, Role
from scripts.validate_limited_pilot_release import apply_runtime_configuration_gates

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def _evidence() -> PilotQualificationEvidence:
    return PilotQualificationEvidence.model_validate(
        {
            "schema_version": "limited_pilot_qualification/1.0.0",
            "baseline": {
                "workflow_p95_ms": 10_000,
                "tokens_per_case": 100,
                "peak_memory_mib": 1000,
            },
            "candidate": {
                "concurrent_sessions": 20,
                "requested_cases": 20,
                "terminal_cases": 20,
                "lost_cases": 0,
                "duplicate_cases": 0,
                "stuck_cases": 0,
                "queue_remaining": 0,
                "restart_count": 0,
                "oom_count": 0,
                "version_metadata_records": 20,
                "workflow_p95_ms": 12_000,
                "tokens_per_case": 110,
                "peak_memory_mib": 1100,
                "non_model_read_p95_ms": 500,
                "non_model_mutation_p95_ms": 1000,
                "review_queue_wait_p95_ms": 2000,
                "backup_rpo_minutes": 60,
                "restore_rto_minutes": 240,
                "accessibility_serious_or_critical_violations": 0,
                "responsive_overflow_viewports": 0,
                "rls_cross_tenant_rows": 0,
                "migration_scenarios_passed": 5,
                "shadow_comparison_cases": 100,
                "shadow_forbidden_downstream_events": 0,
                "external_gpu_calls": 0,
                "real_business_side_effects": 0,
                "default_suite_external_network_calls": 0,
                "security_e2e_scenarios_passed": 5,
                "restore_drill_passed": True,
                "operations_alert_delivery_passed": True,
                "rollback_profile_switch_passed": True,
                "dlq_recovery_drill_passed": True,
                "strict_database_roles_active": True,
                "sensitive_payload_contract_complete": True,
                "storage_reconciliation_passed": True,
                "retention_automation_drill_passed": True,
                "otel_signal_delivery_passed": True,
            },
        }
    )


def test_exact_release_boundaries_pass() -> None:
    result = assess_limited_pilot(_evidence())

    assert result.eligible is True
    assert len(result.checks) == 25
    assert {check.status for check in result.checks} == {GateStatus.PASS}


def test_one_stuck_case_and_resource_regression_block_release() -> None:
    evidence = _evidence()
    candidate = evidence.candidate.model_copy(update={"stuck_cases": 1, "peak_memory_mib": 1100.1})

    result = assess_limited_pilot(evidence.model_copy(update={"candidate": candidate}))

    assert result.eligible is False
    failed = {check.name for check in result.checks if check.status is GateStatus.FAIL}
    assert failed == {"no_loss_duplicate_or_stall", "peak_memory_regression"}


def test_missing_retention_automation_drill_blocks_release() -> None:
    evidence = _evidence()
    candidate = evidence.candidate.model_copy(update={"retention_automation_drill_passed": False})

    result = assess_limited_pilot(evidence.model_copy(update={"candidate": candidate}))

    assert result.eligible is False
    failed = {check.name for check in result.checks if check.status is GateStatus.FAIL}
    assert failed == {"privacy_lifecycle"}


def test_production_pilot_gate_requires_oidc_and_telemetry_while_local_is_compatible() -> None:
    qualified = assess_limited_pilot(_evidence())

    production = apply_runtime_configuration_gates(
        qualified,
        settings=Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="production",
        ),
    )
    local = apply_runtime_configuration_gates(
        qualified,
        settings=Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
    )
    telemetry_configured = apply_runtime_configuration_gates(
        qualified,
        settings=Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="production",
            otel_enabled=True,
            otel_exporter="otlp_http",
            otel_exporter_otlp_endpoint="https://collector.example",
        ),
    )

    assert production.eligible is False
    production_checks = {check.name: check for check in production.checks}
    assert production_checks["oidc_configuration"].status is GateStatus.FAIL
    assert production_checks["telemetry_configuration"].status is GateStatus.FAIL
    assert production_checks["retention_automation_configuration"].status is GateStatus.FAIL
    assert local == qualified
    telemetry_checks = {check.name: check for check in telemetry_configured.checks}
    assert telemetry_checks["telemetry_configuration"].status is GateStatus.PASS
    assert telemetry_configured.eligible is False  # OIDC remains fail-closed.


def _pilot_readiness_service(*, verified_at: datetime | None) -> GetPilotReadiness:
    onboarding = Mock()
    onboarding.execute.return_value = OnboardingReadiness(
        pilot_ready=True,
        gates=tuple(
            OnboardingReadinessGate(
                code=code,
                status=OnboardingGateStatus.PASS,
                description="Configuration is ready.",
            )
            for code in OnboardingGateCode
        ),
    )
    repository = Mock()
    repository.load.return_value = (
        PilotQualificationEvidenceArtifact(
            evidence=_evidence(),
            verified_at=verified_at,
            evidence_digest="a" * 64,
        )
        if verified_at is not None
        else None
    )
    clock = Mock()
    clock.now.return_value = NOW
    return GetPilotReadiness(
        onboarding=onboarding,
        evidence_repository=repository,
        clock=clock,
        evidence_max_age=timedelta(hours=24),
    )


def _admin() -> Principal:
    return Principal(
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        email="admin@example.invalid",
        display_name="Admin",
        roles=frozenset({Role.ADMIN}),
    )


def test_pilot_readiness_requires_fresh_25_gate_evidence() -> None:
    fresh = _pilot_readiness_service(verified_at=NOW - timedelta(hours=1)).execute(
        principal=_admin()
    )
    stale = _pilot_readiness_service(verified_at=NOW - timedelta(hours=25)).execute(
        principal=_admin()
    )
    missing = _pilot_readiness_service(verified_at=None).execute(principal=_admin())

    assert fresh.configuration_ready is True
    assert fresh.operationally_qualified is True
    assert fresh.pilot_ready is True
    operational = [gate for gate in fresh.gates if gate.kind.value == "OPERATIONAL"]
    assert len(operational) == 25
    assert all(gate.status is PilotReadinessGateStatus.PASS for gate in operational)
    assert stale.operationally_qualified is False
    assert all(
        gate.status is PilotReadinessGateStatus.FAIL
        for gate in stale.gates
        if gate.kind.value == "OPERATIONAL"
    )
    assert missing.pilot_ready is False


def test_pilot_readiness_http_contract_is_no_store_and_identifier_free() -> None:
    application = FastAPI()
    application.include_router(router)
    principal = _admin()
    application.dependency_overrides[provide_current_principal] = lambda: principal
    unused: Any = object()
    application.state.operations_services = OperationsServiceContainer(
        get_overview=unused,
        get_failures=unused,
        get_pilot_readiness=_pilot_readiness_service(verified_at=NOW - timedelta(hours=1)),
    )

    response = TestClient(application).get("/api/v1/operations/pilot-readiness")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["pilot_ready"] is True
    serialized = response.text
    assert principal.tenant_id not in serialized
    assert principal.user_id not in serialized
