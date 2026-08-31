"""Technology-neutral release gates for the limited on-premises pilot."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class _Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PilotBaseline(_Evidence):
    workflow_p95_ms: float = Field(gt=0)
    tokens_per_case: float = Field(ge=0)
    peak_memory_mib: float = Field(gt=0)


class PilotCandidate(_Evidence):
    concurrent_sessions: int = Field(ge=0)
    requested_cases: int = Field(ge=1)
    terminal_cases: int = Field(ge=0)
    lost_cases: int = Field(ge=0)
    duplicate_cases: int = Field(ge=0)
    stuck_cases: int = Field(ge=0)
    queue_remaining: int = Field(ge=0)
    restart_count: int = Field(ge=0)
    oom_count: int = Field(ge=0)
    version_metadata_records: int = Field(ge=0)
    workflow_p95_ms: float = Field(gt=0)
    tokens_per_case: float = Field(ge=0)
    peak_memory_mib: float = Field(gt=0)
    non_model_read_p95_ms: float = Field(gt=0)
    non_model_mutation_p95_ms: float = Field(gt=0)
    review_queue_wait_p95_ms: float = Field(ge=0)
    backup_rpo_minutes: float = Field(ge=0)
    restore_rto_minutes: float = Field(ge=0)
    accessibility_serious_or_critical_violations: int = Field(ge=0)
    responsive_overflow_viewports: int = Field(ge=0)
    rls_cross_tenant_rows: int = Field(ge=0)
    migration_scenarios_passed: int = Field(ge=0)
    shadow_comparison_cases: int = Field(ge=0)
    shadow_forbidden_downstream_events: int = Field(ge=0)
    external_gpu_calls: int = Field(ge=0)
    real_business_side_effects: int = Field(ge=0)
    default_suite_external_network_calls: int = Field(ge=0)
    security_e2e_scenarios_passed: int = Field(ge=0)
    restore_drill_passed: bool
    operations_alert_delivery_passed: bool
    rollback_profile_switch_passed: bool
    dlq_recovery_drill_passed: bool
    strict_database_roles_active: bool
    sensitive_payload_contract_complete: bool
    storage_reconciliation_passed: bool
    retention_automation_drill_passed: bool = False
    otel_signal_delivery_passed: bool

    @model_validator(mode="after")
    def validate_counts(self) -> PilotCandidate:
        if self.terminal_cases > self.requested_cases:
            raise ValueError("terminal_cases must not exceed requested_cases")
        if self.version_metadata_records > self.requested_cases:
            raise ValueError("version metadata count must not exceed requested_cases")
        return self


class PilotQualificationEvidence(_Evidence):
    schema_version: str = Field(pattern=r"^limited_pilot_qualification/1\.0\.0$")
    baseline: PilotBaseline
    candidate: PilotCandidate


class GateCheck(_Evidence):
    name: str
    status: GateStatus
    actual: str
    limit: str


class PilotQualificationResult(_Evidence):
    schema_version: str = "limited_pilot_qualification_result/1.0.0"
    eligible: bool
    checks: tuple[GateCheck, ...]


def assess_limited_pilot(evidence: PilotQualificationEvidence) -> PilotQualificationResult:
    """Apply frozen safety, recovery, latency, and resource release thresholds."""

    baseline = evidence.baseline
    candidate = evidence.candidate
    checks = (
        _check(
            "twenty_terminal",
            candidate.requested_cases == 20 and candidate.terminal_cases == 20,
            f"{candidate.terminal_cases}/{candidate.requested_cases}",
            "20/20",
        ),
        _check(
            "no_loss_duplicate_or_stall",
            candidate.lost_cases == candidate.duplicate_cases == candidate.stuck_cases == 0,
            f"lost={candidate.lost_cases},duplicate={candidate.duplicate_cases},stuck={candidate.stuck_cases}",
            "all zero",
        ),
        _check(
            "queue_drained",
            candidate.queue_remaining == 0,
            str(candidate.queue_remaining),
            "0",
        ),
        _check(
            "no_restart_or_oom",
            candidate.restart_count == candidate.oom_count == 0,
            f"restart={candidate.restart_count},oom={candidate.oom_count}",
            "both zero",
        ),
        _check(
            "version_metadata_complete",
            candidate.version_metadata_records == candidate.requested_cases,
            f"{candidate.version_metadata_records}/{candidate.requested_cases}",
            "100%",
        ),
        _ratio_check(
            "workflow_p95_regression",
            candidate.workflow_p95_ms,
            baseline.workflow_p95_ms,
            1.20,
        ),
        _ratio_check(
            "tokens_per_case_regression",
            candidate.tokens_per_case,
            baseline.tokens_per_case,
            1.10,
        ),
        _ratio_check(
            "peak_memory_regression",
            candidate.peak_memory_mib,
            baseline.peak_memory_mib,
            1.10,
        ),
        _upper_bound("non_model_read_p95", candidate.non_model_read_p95_ms, 500.0, "ms"),
        _upper_bound(
            "non_model_mutation_p95",
            candidate.non_model_mutation_p95_ms,
            1000.0,
            "ms",
        ),
        _upper_bound(
            "review_queue_wait_p95",
            candidate.review_queue_wait_p95_ms,
            2000.0,
            "ms",
        ),
        _upper_bound("backup_rpo", candidate.backup_rpo_minutes, 60.0, "minutes"),
        _upper_bound("restore_rto", candidate.restore_rto_minutes, 240.0, "minutes"),
        _check(
            "twenty_concurrent_sessions",
            candidate.concurrent_sessions == 20,
            str(candidate.concurrent_sessions),
            "20",
        ),
        _check(
            "accessibility_and_responsive_layout",
            candidate.accessibility_serious_or_critical_violations == 0
            and candidate.responsive_overflow_viewports == 0,
            (
                f"a11y={candidate.accessibility_serious_or_critical_violations},"
                f"overflow={candidate.responsive_overflow_viewports}"
            ),
            "both zero",
        ),
        _check(
            "rls_default_deny",
            candidate.rls_cross_tenant_rows == 0,
            str(candidate.rls_cross_tenant_rows),
            "0 cross-tenant rows",
        ),
        _check(
            "migration_matrix",
            candidate.migration_scenarios_passed >= 5,
            str(candidate.migration_scenarios_passed),
            ">= 5 scenarios",
        ),
        _check(
            "shadow_observation_only",
            candidate.shadow_comparison_cases >= 100
            and candidate.shadow_forbidden_downstream_events == 0,
            (
                f"cases={candidate.shadow_comparison_cases},"
                f"forbidden_events={candidate.shadow_forbidden_downstream_events}"
            ),
            ">=100 cases and 0 forbidden events",
        ),
        _check(
            "no_external_execution",
            candidate.external_gpu_calls == 0 and candidate.real_business_side_effects == 0,
            (
                f"gpu={candidate.external_gpu_calls},"
                f"business_side_effects={candidate.real_business_side_effects}"
            ),
            "both zero",
        ),
        _check(
            "operational_drills",
            candidate.restore_drill_passed
            and candidate.operations_alert_delivery_passed
            and candidate.rollback_profile_switch_passed,
            (
                f"restore={candidate.restore_drill_passed},"
                f"alerts={candidate.operations_alert_delivery_passed},"
                f"rollback={candidate.rollback_profile_switch_passed}"
            ),
            "all true",
        ),
        _check(
            "queue_failure_recovery",
            candidate.dlq_recovery_drill_passed,
            str(candidate.dlq_recovery_drill_passed),
            "DLQ replay/cancel drill passed",
        ),
        _check(
            "strict_database_roles",
            candidate.strict_database_roles_active,
            str(candidate.strict_database_roles_active),
            "API/Worker/Dispatcher least-privilege roles active",
        ),
        _check(
            "privacy_lifecycle",
            candidate.sensitive_payload_contract_complete
            and candidate.storage_reconciliation_passed
            and candidate.retention_automation_drill_passed,
            (
                f"contract={candidate.sensitive_payload_contract_complete},"
                f"reconciliation={candidate.storage_reconciliation_passed},"
                f"automation={candidate.retention_automation_drill_passed}"
            ),
            "contract, storage reconciliation, and automatic retention drill passed",
        ),
        _check(
            "otel_signal_delivery",
            candidate.otel_signal_delivery_passed,
            str(candidate.otel_signal_delivery_passed),
            "OpenTelemetry traces and metrics delivered",
        ),
        _check(
            "network_free_security_e2e",
            candidate.default_suite_external_network_calls == 0
            and candidate.security_e2e_scenarios_passed >= 5,
            (
                f"external_calls={candidate.default_suite_external_network_calls},"
                f"security_scenarios={candidate.security_e2e_scenarios_passed}"
            ),
            "0 external calls and >=5 scenarios",
        ),
    )
    return PilotQualificationResult(
        eligible=all(check.status is GateStatus.PASS for check in checks),
        checks=checks,
    )


def _check(name: str, passed: bool, actual: str, limit: str) -> GateCheck:
    return GateCheck(
        name=name,
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        actual=actual,
        limit=limit,
    )


def _ratio_check(name: str, actual: float, baseline: float, multiplier: float) -> GateCheck:
    limit = baseline * multiplier
    return _check(name, actual <= limit, f"{actual:.4f}", f"<= {limit:.4f}")


def _upper_bound(name: str, actual: float, limit: float, unit: str) -> GateCheck:
    return _check(name, actual <= limit, f"{actual:.4f} {unit}", f"<= {limit:.4f} {unit}")


__all__ = [
    "GateCheck",
    "GateStatus",
    "PilotBaseline",
    "PilotCandidate",
    "PilotQualificationEvidence",
    "PilotQualificationResult",
    "assess_limited_pilot",
]
