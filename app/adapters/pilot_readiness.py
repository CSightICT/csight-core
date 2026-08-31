"""Read-only file adapter for a PII-free pilot qualification manifest."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.platform.pilot_qualification import PilotQualificationEvidence
from app.platform.pilot_readiness import PilotQualificationEvidenceArtifact


class JsonPilotQualificationEvidenceRepository:
    def __init__(self, path: Path | None) -> None:
        self._path = path

    def load(self) -> PilotQualificationEvidenceArtifact | None:
        path = self._path
        if path is None or not path.is_file():
            return None
        payload_bytes = path.read_bytes()
        payload = json.loads(payload_bytes)
        evidence = PilotQualificationEvidence.model_validate(payload)
        verified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        return PilotQualificationEvidenceArtifact(
            evidence=evidence,
            verified_at=verified_at,
            evidence_digest=hashlib.sha256(payload_bytes).hexdigest(),
        )


__all__ = ["JsonPilotQualificationEvidenceRepository"]
