"""Port for loading one sanitized limited-pilot qualification artifact."""

from typing import Protocol

from app.platform.pilot_readiness import PilotQualificationEvidenceArtifact


class PilotQualificationEvidenceRepository(Protocol):
    def load(self) -> PilotQualificationEvidenceArtifact | None: ...


__all__ = ["PilotQualificationEvidenceRepository"]
