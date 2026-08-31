"""PII-free product onboarding readiness contracts."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OnboardingGateCode(StrEnum):
    ACTIVE_OPERATOR_STAFFING = "ACTIVE_OPERATOR_STAFFING"
    SIGNED_INTAKE_SOURCE = "SIGNED_INTAKE_SOURCE"
    RETENTION_AUTOMATION = "RETENTION_AUTOMATION"
    OIDC_TENANT_MAPPING = "OIDC_TENANT_MAPPING"
    ACTIVE_POLICY_RUNTIME = "ACTIVE_POLICY_RUNTIME"
    PRIMARY_MODEL_ROUTES = "PRIMARY_MODEL_ROUTES"


class OnboardingGateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class OnboardingReadinessFacts(_Contract):
    """Internal low-cardinality facts from one tenant-scoped database read."""

    tenant_slug: str = Field(min_length=1, max_length=63)
    tenant_is_active: bool
    active_admin_count: int = Field(ge=0)
    active_reviewer_count: int = Field(ge=0)
    configured_no_role_actor_count: int = Field(ge=0)
    active_policy_index_count: int = Field(ge=0)
    active_rule_set_count: int = Field(ge=0)
    active_primary_model_route_count: int = Field(ge=0, le=3)


class OnboardingReadinessGate(_Contract):
    code: OnboardingGateCode
    status: OnboardingGateStatus
    description: str = Field(min_length=1, max_length=300)


class OnboardingReadiness(_Contract):
    pilot_ready: bool
    gates: tuple[OnboardingReadinessGate, ...] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def require_complete_gate_set_and_derived_result(self) -> Self:
        expected = set(OnboardingGateCode)
        actual = {gate.code for gate in self.gates}
        if actual != expected or len(actual) != len(self.gates):
            raise ValueError("onboarding readiness must contain every gate exactly once")
        all_pass = all(gate.status is OnboardingGateStatus.PASS for gate in self.gates)
        if self.pilot_ready is not all_pass:
            raise ValueError("pilot_ready must be derived from all required gates")
        return self


__all__ = [
    "OnboardingGateCode",
    "OnboardingGateStatus",
    "OnboardingReadiness",
    "OnboardingReadinessFacts",
    "OnboardingReadinessGate",
]
