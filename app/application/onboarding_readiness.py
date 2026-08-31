"""Admin-only evaluation of immutable onboarding readiness facts."""

from pydantic import BaseModel, ConfigDict, Field

from app.platform.errors import ForbiddenError
from app.platform.onboarding_readiness import (
    OnboardingGateCode,
    OnboardingGateStatus,
    OnboardingReadiness,
    OnboardingReadinessGate,
)
from app.platform.tenant import Principal, Role
from app.ports.onboarding_readiness import OnboardingReadinessRepository
from app.ports.runtime import Clock


class OnboardingReadinessConfiguration(BaseModel):
    """Deployment facts kept separate from tenant-owned database state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signed_actor_ids_by_tenant: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    retention_policy_explicit: bool = False
    retention_automation_tenant_id: str | None = None
    oidc_tenant_slugs: frozenset[str] = Field(default_factory=frozenset)
    model_route_runtime_complete: bool = False

    def signed_actor_ids_for(self, tenant_id: str) -> tuple[str, ...]:
        return self.signed_actor_ids_by_tenant.get(tenant_id, ())


class GetOnboardingReadiness:
    def __init__(
        self,
        *,
        repository: OnboardingReadinessRepository,
        configuration: OnboardingReadinessConfiguration,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._configuration = configuration
        self._clock = clock

    def execute(self, *, principal: Principal) -> OnboardingReadiness:
        if Role.ADMIN not in principal.roles:
            raise ForbiddenError()

        configured_actor_ids = tuple(
            dict.fromkeys(self._configuration.signed_actor_ids_for(principal.tenant_id))
        )
        facts = self._repository.get_facts(
            tenant_id=principal.tenant_id,
            configured_signed_actor_ids=configured_actor_ids,
            as_of_date=self._clock.now().date(),
        )
        tenant_failure = (
            "Activate this tenant before evaluating its pilot onboarding requirements."
            if not facts.tenant_is_active
            else None
        )
        staffing_ready = (
            facts.tenant_is_active
            and facts.active_admin_count >= 1
            and facts.active_reviewer_count >= 1
        )
        signed_intake_ready = (
            facts.tenant_is_active
            and bool(configured_actor_ids)
            and facts.configured_no_role_actor_count == len(configured_actor_ids)
        )
        retention_ready = (
            facts.tenant_is_active
            and self._configuration.retention_policy_explicit
            and self._configuration.retention_automation_tenant_id == principal.tenant_id
        )
        oidc_ready = (
            facts.tenant_is_active and facts.tenant_slug in self._configuration.oidc_tenant_slugs
        )
        policy_ready = (
            facts.tenant_is_active
            and facts.active_policy_index_count >= 1
            and facts.active_rule_set_count >= 1
        )
        model_routes_ready = facts.tenant_is_active and facts.active_primary_model_route_count == 3
        model_runtime_ready = (
            model_routes_ready and self._configuration.model_route_runtime_complete
        )
        model_route_failure = (
            "Activate current PRIMARY routes for extraction, query building, and grounding."
            if facts.active_primary_model_route_count != 3
            else ("Connect and verify runtime enforcement for all three PRIMARY model routes.")
        )
        gates = (
            _gate(
                OnboardingGateCode.ACTIVE_OPERATOR_STAFFING,
                staffing_ready,
                passed="Active administrator and reviewer accounts are available.",
                failed=tenant_failure
                or "Add at least one active administrator and one active reviewer account.",
            ),
            _gate(
                OnboardingGateCode.SIGNED_INTAKE_SOURCE,
                signed_intake_ready,
                passed=(
                    "Every configured tenant intake source uses an active no-role service actor."
                ),
                failed=tenant_failure
                or (
                    "Configure a tenant intake source with an active service actor "
                    "that has no roles."
                ),
            ),
            _gate(
                OnboardingGateCode.RETENTION_AUTOMATION,
                retention_ready,
                passed="Explicit retention and tenant-bound lifecycle automation are enabled.",
                failed=tenant_failure
                or (
                    "Set the approved retention policy and enable lifecycle automation "
                    "for this tenant."
                ),
            ),
            _gate(
                OnboardingGateCode.OIDC_TENANT_MAPPING,
                oidc_ready,
                passed="Enterprise sign-in has an active mapping for this tenant.",
                failed=tenant_failure
                or (
                    "Configure enterprise sign-in and map an identity-provider group "
                    "to this tenant."
                ),
            ),
            _gate(
                OnboardingGateCode.ACTIVE_POLICY_RUNTIME,
                policy_ready,
                passed="A complete policy index and a current rule set are active.",
                failed=tenant_failure
                or ("Activate a complete policy index and a currently effective policy rule set."),
            ),
            _gate(
                OnboardingGateCode.PRIMARY_MODEL_ROUTES,
                model_runtime_ready,
                passed=(
                    "All three required PRIMARY model routes are active, current, and enforced."
                ),
                failed=tenant_failure or model_route_failure,
            ),
        )
        return OnboardingReadiness(
            pilot_ready=all(gate.status is OnboardingGateStatus.PASS for gate in gates),
            gates=gates,
        )


def _gate(
    code: OnboardingGateCode,
    is_pass: bool,
    *,
    passed: str,
    failed: str,
) -> OnboardingReadinessGate:
    return OnboardingReadinessGate(
        code=code,
        status=OnboardingGateStatus.PASS if is_pass else OnboardingGateStatus.FAIL,
        description=passed if is_pass else failed,
    )


__all__ = [
    "GetOnboardingReadiness",
    "OnboardingReadinessConfiguration",
]
