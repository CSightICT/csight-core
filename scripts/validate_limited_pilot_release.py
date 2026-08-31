"""Validate one PII-free limited-pilot evidence manifest against frozen release gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.bootstrap.settings import Settings
from app.platform.pilot_qualification import (
    GateCheck,
    GateStatus,
    PilotQualificationEvidence,
    PilotQualificationResult,
    assess_limited_pilot,
)


def apply_runtime_configuration_gates(
    result: PilotQualificationResult,
    *,
    settings: Settings,
) -> PilotQualificationResult:
    """Require production auth, telemetry, and automatic retention configuration."""

    if settings.environment in {"local", "test"}:
        return result
    oidc_check = GateCheck(
        name="oidc_configuration",
        status=GateStatus.PASS if settings.oidc_is_configured else GateStatus.FAIL,
        actual="configured" if settings.oidc_is_configured else "unavailable",
        limit="configured production OIDC",
    )
    telemetry_check = GateCheck(
        name="telemetry_configuration",
        status=GateStatus.PASS if settings.otel_is_configured else GateStatus.FAIL,
        actual="configured" if settings.otel_is_configured else "unavailable",
        limit="enabled OTLP/HTTP traces and metrics endpoint",
    )
    retention_check = GateCheck(
        name="retention_automation_configuration",
        status=(
            GateStatus.PASS if settings.privacy_lifecycle_automation_enabled else GateStatus.FAIL
        ),
        actual=("configured" if settings.privacy_lifecycle_automation_enabled else "disabled"),
        limit="explicit tenant-scoped automatic retention enabled",
    )
    return result.model_copy(
        update={
            "eligible": (
                result.eligible
                and settings.oidc_is_configured
                and settings.otel_is_configured
                and settings.privacy_lifecycle_automation_enabled
            ),
            "checks": (*result.checks, oidc_check, telemetry_check, retention_check),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    arguments = parser.parse_args()
    payload = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    evidence = PilotQualificationEvidence.model_validate(payload)
    result = apply_runtime_configuration_gates(
        assess_limited_pilot(evidence),
        settings=Settings(),
    )
    print(result.model_dump_json(indent=2))
    return 0 if result.eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
