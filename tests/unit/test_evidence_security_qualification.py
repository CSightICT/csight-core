"""Static safety contract for the opt-in ClamAV qualification stack."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

COMPOSE_PATH = Path("infra/evidence/compose.evidence-security.yml")
RUNNER_PATH = Path("scripts/qualify_evidence_security.sh")
QUALIFIER_PATH = Path("scripts/qualify_evidence_security.py")


def test_evidence_security_overlay_is_internal_pinned_and_fail_closed() -> None:
    document = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = document["services"]
    api = services["api"]
    clamav = services["clamav"]

    assert api["environment"] == {
        "EVIDENCE_IMAGE_SANITIZATION_ENABLED": "true",
        "EVIDENCE_MALWARE_SCANNER": "clamav",
        "CLAMAV_HOST": "clamav",
        "CLAMAV_PORT": "3310",
        "CLAMAV_TIMEOUT_SECONDS": "${CLAMAV_TIMEOUT_SECONDS:-10}",
    }
    assert api["depends_on"]["clamav"]["condition"] == "service_healthy"
    assert clamav["image"] == (
        "clamav/clamav:1.5.4@"
        "sha256:0e85467cb0d6e7d860a45035707741cd5ffc032ffefc6002a3510c75b6d07027"
    )
    assert clamav["platform"] == "linux/amd64"
    assert "ports" not in clamav
    assert clamav["expose"] == ["3310"]
    assert clamav["healthcheck"]["test"] == ["CMD-SHELL", "clamdcheck.sh"]


def test_evidence_qualification_runner_is_isolated_and_always_removes_volumes() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert 'PROJECT_NAME="csight-evidence-qualification"' in source
    assert "trap cleanup EXIT INT TERM" in source
    assert "compose down --volumes --remove-orphans" in source
    assert "compose build api migrator" in source
    assert "compose run --rm migrator" in source
    assert "-e DEVELOPMENT_SEED_ENABLED" in source
    assert "-e DEVELOPMENT_SEED_ADMIN_PASSWORD" in source
    assert "compose stop clamav" in source
    assert "--phase healthy" in source
    assert "--phase outage" in source
    assert "local-data/evidence-security-qualification/latest" in source
    assert 'chmod 600 "$HEALTHY_REPORT"' in source
    assert 'chmod 600 "$OUTAGE_REPORT"' in source
    assert 'chmod 700 "$OUTPUT_DIR"' in source


def test_live_qualifier_covers_required_security_gates_without_logging_secrets() -> None:
    source = QUALIFIER_PATH.read_text(encoding="utf-8")

    for gate in (
        "clean_image_stored",
        "original_bytes_reencoded",
        "exif_removed_and_orientation_applied",
        "eicar_rejected_before_image_decode",
        "malformed_image_rejected",
        "oversized_request_rejected",
        "scanner_outage_fails_closed",
    ):
        assert gate in source
    assert 'access_token": token' not in source
    assert "print(password" not in source
