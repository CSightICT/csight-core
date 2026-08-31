"""Frozen limited-pilot qualification thresholds."""

import pytest

from app.bootstrap.settings import Settings
from app.platform.pilot_qualification import (
    GateStatus,
    PilotQualificationEvidence,
    assess_limited_pilot,
)
from scripts.validate_limited_pilot_release import apply_runtime_configuration_gates

pytestmark = pytest.mark.unit


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
