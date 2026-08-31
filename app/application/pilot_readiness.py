"""Admin-only composition of onboarding and time-bounded operational gates."""

from datetime import timedelta

from app.application.onboarding_readiness import GetOnboardingReadiness
from app.platform.errors import ForbiddenError
from app.platform.onboarding_readiness import OnboardingGateStatus
from app.platform.pilot_qualification import GateStatus, assess_limited_pilot
from app.platform.pilot_readiness import (
    PilotReadiness,
    PilotReadinessGate,
    PilotReadinessGateKind,
    PilotReadinessGateStatus,
)
from app.platform.tenant import Principal, Role
from app.ports.pilot_readiness import PilotQualificationEvidenceRepository
from app.ports.runtime import Clock


class GetPilotReadiness:
    def __init__(
        self,
        *,
        onboarding: GetOnboardingReadiness,
        evidence_repository: PilotQualificationEvidenceRepository,
        clock: Clock,
        evidence_max_age: timedelta,
    ) -> None:
        if evidence_max_age.total_seconds() <= 0:
            raise ValueError("evidence_max_age must be positive")
        self._onboarding = onboarding
        self._evidence_repository = evidence_repository
        self._clock = clock
        self._evidence_max_age = evidence_max_age

    def execute(self, *, principal: Principal) -> PilotReadiness:
        if Role.ADMIN not in principal.roles:
            raise ForbiddenError()
        now = self._clock.now()
        onboarding = self._onboarding.execute(principal=principal)
        configuration_gates = tuple(
            PilotReadinessGate(
                kind=PilotReadinessGateKind.CONFIGURATION,
                code=gate.code.value,
                status=(
                    PilotReadinessGateStatus.PASS
                    if gate.status is OnboardingGateStatus.PASS
                    else PilotReadinessGateStatus.FAIL
                ),
                verified_at=now,
                description=gate.description,
            )
            for gate in onboarding.gates
        )

        artifact = self._evidence_repository.load()
        if artifact is None:
            operational_gates = (
                PilotReadinessGate(
                    kind=PilotReadinessGateKind.OPERATIONAL,
                    code="qualification_evidence_available",
                    status=PilotReadinessGateStatus.FAIL,
                    description=("No PII-free limited-pilot qualification evidence is available."),
                ),
            )
            operationally_qualified = False
        else:
            expires_at = artifact.verified_at + self._evidence_max_age
            fresh = now <= expires_at
            qualification = assess_limited_pilot(artifact.evidence)
            operational_gates = tuple(
                PilotReadinessGate(
                    kind=PilotReadinessGateKind.OPERATIONAL,
                    code=check.name,
                    status=(
                        PilotReadinessGateStatus.PASS
                        if fresh and check.status is GateStatus.PASS
                        else PilotReadinessGateStatus.FAIL
                    ),
                    verified_at=artifact.verified_at,
                    expires_at=expires_at,
                    evidence_digest=artifact.evidence_digest,
                    description=(
                        f"Observed {check.actual}; required {check.limit}."
                        if fresh
                        else "Qualification evidence expired and must be reproduced."
                    ),
                )
                for check in qualification.checks
            )
            operationally_qualified = fresh and qualification.eligible

        configuration_ready = onboarding.pilot_ready
        return PilotReadiness(
            configuration_ready=configuration_ready,
            operationally_qualified=operationally_qualified,
            pilot_ready=configuration_ready and operationally_qualified,
            gates=(*configuration_gates, *operational_gates),
        )


__all__ = ["GetPilotReadiness"]
