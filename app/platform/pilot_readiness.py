"""PII-free readiness contract joining configuration and operational evidence."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.platform.onboarding_readiness import OnboardingReadiness
from app.platform.pilot_qualification import PilotQualificationEvidence


class PilotReadinessGateKind(StrEnum):
    CONFIGURATION = "CONFIGURATION"
    OPERATIONAL = "OPERATIONAL"


class PilotReadinessGateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PilotQualificationEvidenceArtifact(_Contract):
    evidence: PilotQualificationEvidence
    verified_at: datetime
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PilotReadinessGate(_Contract):
    kind: PilotReadinessGateKind
    code: str = Field(min_length=1, max_length=128)
    status: PilotReadinessGateStatus
    verified_at: datetime | None = None
    expires_at: datetime | None = None
    evidence_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    description: str = Field(min_length=1, max_length=1000)


class PilotReadiness(_Contract):
    configuration_ready: bool
    operationally_qualified: bool
    pilot_ready: bool
    gates: tuple[PilotReadinessGate, ...]


class PilotReadinessInputs(_Contract):
    onboarding: OnboardingReadiness
    evidence_artifact: PilotQualificationEvidenceArtifact | None


__all__ = [
    "PilotQualificationEvidenceArtifact",
    "PilotReadiness",
    "PilotReadinessGate",
    "PilotReadinessGateKind",
    "PilotReadinessGateStatus",
    "PilotReadinessInputs",
]
