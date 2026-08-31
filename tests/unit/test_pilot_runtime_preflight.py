"""Fail-closed pilot admission checks without Docker, network, backup, or restore mutation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.preflight_pilot_runtime as pilot_preflight
from scripts.preflight_pilot_runtime import (
    MINIMUM_FREE_BYTES,
    PilotPreflightError,
    ensure_minimum_disk_space,
    load_private_env,
    validate_pilot_environment,
    validate_pilot_qualification,
    validate_restore_set,
)
from scripts.restore_manifest import ARTIFACT_ROLES, build_manifest

pytestmark = pytest.mark.unit


def _private_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path


def _valid_environment(tmp_path: Path) -> dict[str, str]:
    secret_files: list[Path] = []
    for name in ("api", "worker", "dispatcher"):
        secret_files.append(_private_file(tmp_path / f"{name}.password", f"{name}-" + "x" * 32))
    public_key = _private_file(tmp_path / "release.pub", "ed25519-public-key-fixture")
    intake_public_key = _private_file(
        tmp_path / "signed-intake.pub",
        """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAERERERERERERERERERERERERERERERERERERERERERE=
-----END PUBLIC KEY-----
""",
    )
    wal_archive = tmp_path / "wal-archive"
    wal_archive.mkdir(exist_ok=True)
    digest = "sha256:" + "a" * 64
    return {
        "ENVIRONMENT": "pilot",
        "CSIGHT_IMAGE_TAG": "pilot-20260831-001",
        "PILOT_RELEASE_COMMIT": "b" * 40,
        "POSTGRES_PASSWORD": "postgres-" + "p" * 32,
        "RABBITMQ_DEFAULT_PASS": "rabbit-" + "r" * 32,
        "MINIO_ACCESS_KEY": "pilot-minio-access",
        "MINIO_SECRET_KEY": "minio-" + "m" * 40,
        "JWT_SECRET_KEY": "jwt-" + "j" * 40,
        "DATABASE_RLS_REQUIRED": "true",
        "LEGACY_PASSWORD_AUTH_ENABLED": "false",
        "OIDC_ENABLED": "true",
        "OIDC_TLS_VERIFY": "true",
        "OIDC_ALLOW_INSECURE_HTTP": "false",
        "OIDC_COOKIE_SECURE": "true",
        "OIDC_ISSUER": "https://idp.pilot.internal/realms/csight",
        "OIDC_CLIENT_ID": "csight-pilot",
        "OIDC_AUTHORIZATION_ENDPOINT": (
            "https://idp.pilot.internal/realms/csight/protocol/openid-connect/auth"
        ),
        "OIDC_TOKEN_ENDPOINT": (
            "https://idp.pilot.internal/realms/csight/protocol/openid-connect/token"
        ),
        "OIDC_JWKS_URI": ("https://idp.pilot.internal/realms/csight/protocol/openid-connect/certs"),
        "OIDC_REDIRECT_URI": "https://pilot.internal/auth/oidc/callback",
        "OIDC_GROUP_MAPPINGS": json.dumps(
            {"/csight/reviewers": {"tenant_slug": "pilot", "allowed_roles": ["REVIEWER"]}}
        ),
        "OTEL_ENABLED": "true",
        "OTEL_EXPORTER": "otlp_http",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector.internal:4318",
        "SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION": "pilot-approved/90d-v1",
        "SENSITIVE_PAYLOAD_RETENTION_DAYS": "90",
        "PRIVACY_LIFECYCLE_AUTOMATION_ENABLED": "true",
        "PRIVACY_LIFECYCLE_TENANT_ID": "11111111-1111-4111-8111-111111111111",
        "SIGNED_INTAKE_ENABLED": "true",
        "SIGNED_INTAKE_SOURCES": json.dumps(
            {
                "pilot-customer-key-v1": {
                    "source_id": "pilot-customer-intake",
                    "tenant_id": "11111111-1111-4111-8111-111111111111",
                    "actor_user_id": "22222222-2222-4222-8222-222222222222",
                    "provenance": "pilot.customer.integration",
                    "public_key_file": "/run/config/signed_intake_public_key.pem",
                }
            }
        ),
        "SIGNED_INTAKE_PUBLIC_KEY_HOST_FILE": os.fspath(intake_public_key),
        "SIGNED_INTAKE_MAX_BODY_BYTES": "131072",
        "SIGNED_INTAKE_CLOCK_SKEW_SECONDS": "300",
        "MODEL_RELEASE_ENFORCEMENT": "true",
        "MODEL_ROUTE_ENFORCEMENT": "true",
        "MODEL_ROUTE_DEPLOYMENT_ID": "onprem-4090-primary",
        "LLM_PROVIDER": "vllm",
        "LLM_BASE_URL": "http://100.64.0.20:18000",
        "LLM_API_KEY": "llm-" + "l" * 40,
        "LLM_MODEL_ID": "qualified-llm",
        "LLM_MODEL_VERSION": "1.0.0",
        "LLM_MODEL_REVISION": "c" * 40,
        "MODEL_RELEASE_SIGNING_KEY_ID": "pilot-release-key-v1",
        "LLM_ARTIFACT_CONTENT_DIGEST": digest,
        "LLM_RUNTIME_IMAGE_DIGEST": digest,
        "LLM_DEPENDENCY_LOCK_DIGEST": digest,
        "LLM_SBOM_DIGEST": digest,
        "VISION_PROVIDER": "remote",
        "VISION_BASE_URL": "http://100.64.0.21:18001",
        "VISION_API_KEY": "vision-" + "v" * 40,
        "VISION_MODEL_ID": "qualified-vision",
        "VISION_MODEL_VERSION": "1.0.0",
        "VISION_MODEL_REVISION": "vision-release-20260831",
        "EMBEDDING_BASE_URL": "http://100.64.0.22:18002",
        "MINIO_PRESIGNED_ENDPOINT": "evidence.pilot.internal",
        "MINIO_PRESIGNED_SECURE": "true",
        "API_DATABASE_PASSWORD_HOST_FILE": os.fspath(secret_files[0]),
        "WORKER_DATABASE_PASSWORD_HOST_FILE": os.fspath(secret_files[1]),
        "DISPATCHER_DATABASE_PASSWORD_HOST_FILE": os.fspath(secret_files[2]),
        "MODEL_RELEASE_SIGNING_PUBLIC_KEY_HOST_FILE": os.fspath(public_key),
        "POSTGRES_WAL_ARCHIVE_PATH": os.fspath(wal_archive),
    }


def _eligible_qualification() -> dict[str, object]:
    return {
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


def _restore_fixture(tmp_path: Path) -> tuple[dict[str, str], Path]:
    artifacts: dict[str, Path] = {}
    for index, role in enumerate(ARTIFACT_ROLES):
        artifact = tmp_path / role
        artifact.mkdir()
        (artifact / "part.bin").write_bytes(f"artifact-{index}".encode())
        artifacts[role] = artifact
    manifest = build_manifest(
        backup_id="pilot-backup-20260831",
        postgresql_version="16.4",
        minio_version="RELEASE.2026-08-01T00-00-00Z",
        encryption_key_id="kms://pilot/off-host-v1",
        artifacts=artifacts,
    )
    manifest_path = tmp_path / "restore-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = {
        "schema_version": "csight.restore_drill_qualification/1.0.0",
        "status": "PASS",
        "scope": "encrypted-immutable-off-host-pilot-hardware",
        "accepted_at": "2026-08-31T01:02:03+00:00",
        "rpo_minutes": 60,
        "rto_minutes": 240,
        "rpo_passed": True,
        "rto_passed": True,
        "encrypted_off_host_copy_qualified": True,
        "immutable_off_host_copy_qualified": True,
        "independent_key_resolution_qualified": True,
        "scheduled_backup_qualified": True,
        "target_host_repeat_required": False,
        "pilot_hardware_repeat_count": 2,
        "external_business_side_effects": 0,
        "manifest": {
            "status": "PASS",
            "binding_sha256": manifest["binding_sha256"],
        },
    }
    report_path = tmp_path / "restore-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    values = {
        "PILOT_RESTORE_MANIFEST": os.fspath(manifest_path),
        "PILOT_POSTGRES_BASE_BACKUP": os.fspath(artifacts["postgresql_base_backup"]),
        "PILOT_POSTGRES_WAL_ARCHIVE": os.fspath(artifacts["postgresql_wal_archive"]),
        "PILOT_MINIO_VERSION_INVENTORY": os.fspath(artifacts["minio_version_inventory"]),
        "PILOT_MINIO_VERSION_BACKUP": os.fspath(artifacts["minio_version_backup"]),
        "PILOT_RUNTIME_VERSION_MANIFEST": os.fspath(artifacts["runtime_version_manifest"]),
        "PILOT_RESTORE_QUALIFICATION_REPORT": os.fspath(report_path),
    }
    return values, artifacts["minio_version_backup"] / "part.bin"


def test_private_env_rejects_group_or_other_access(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.pilot"
    env_file.write_text("ENVIRONMENT=pilot\n", encoding="utf-8")
    env_file.chmod(0o644)

    with pytest.raises(PilotPreflightError, match="owner-owned"):
        load_private_env(env_file)


def test_private_env_rejects_symlink_even_when_target_is_private(tmp_path: Path) -> None:
    target = _private_file(tmp_path / "real.env", "ENVIRONMENT=pilot\n")
    env_link = tmp_path / ".env.pilot"
    env_link.symlink_to(target)

    with pytest.raises(PilotPreflightError, match="non-symlink"):
        pilot_preflight.run_preflight(repo_root=tmp_path, env_file=env_link)


def test_pilot_environment_requires_real_release_security_and_private_files(
    tmp_path: Path,
) -> None:
    values = _valid_environment(tmp_path)
    validate_pilot_environment(values)

    values["CSIGHT_IMAGE_TAG"] = "dev"
    with pytest.raises(PilotPreflightError, match="non-development"):
        validate_pilot_environment(values)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ({"SIGNED_INTAKE_ENABLED": "false"}, "SIGNED_INTAKE_ENABLED must be true"),
        ({"SIGNED_INTAKE_MAX_BODY_BYTES": "131073"}, "must be 131072"),
        ({"SIGNED_INTAKE_CLOCK_SKEW_SECONDS": "301"}, "must be 300"),
    ),
)
def test_pilot_environment_freezes_signed_intake_limits(
    tmp_path: Path,
    mutation: dict[str, str],
    message: str,
) -> None:
    values = _valid_environment(tmp_path)
    values.update(mutation)

    with pytest.raises(PilotPreflightError, match=message):
        validate_pilot_environment(values)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    (
        ("MODEL_ROUTE_ENFORCEMENT", "false", "MODEL_ROUTE_ENFORCEMENT must be true"),
        ("MODEL_ROUTE_DEPLOYMENT_ID", "4090 PRIMARY", "invalid format"),
    ),
)
def test_pilot_environment_requires_route_enforcement_and_deployment_identity(
    tmp_path: Path,
    name: str,
    value: str,
    message: str,
) -> None:
    values = _valid_environment(tmp_path)
    values[name] = value

    with pytest.raises(PilotPreflightError, match=message):
        validate_pilot_environment(values)


def test_pilot_environment_rejects_multiple_or_cross_tenant_intake_sources(
    tmp_path: Path,
) -> None:
    values = _valid_environment(tmp_path)
    sources = json.loads(values["SIGNED_INTAKE_SOURCES"])
    sources["second-pilot-key"] = {**next(iter(sources.values())), "source_id": "other-source"}
    values["SIGNED_INTAKE_SOURCES"] = json.dumps(sources)
    with pytest.raises(PilotPreflightError, match="exactly one"):
        validate_pilot_environment(values)

    values = _valid_environment(tmp_path)
    source = next(iter(json.loads(values["SIGNED_INTAKE_SOURCES"]).values()))
    source["tenant_id"] = "33333333-3333-4333-8333-333333333333"
    values["SIGNED_INTAKE_SOURCES"] = json.dumps({"pilot-customer-key-v1": source})
    with pytest.raises(PilotPreflightError, match="must match"):
        validate_pilot_environment(values)


def test_pilot_environment_requires_fixed_path_and_valid_separate_intake_key(
    tmp_path: Path,
) -> None:
    values = _valid_environment(tmp_path)
    source = next(iter(json.loads(values["SIGNED_INTAKE_SOURCES"]).values()))
    source["public_key_file"] = "/tmp/intake.pem"
    values["SIGNED_INTAKE_SOURCES"] = json.dumps({"pilot-customer-key-v1": source})
    with pytest.raises(PilotPreflightError, match="frozen path"):
        validate_pilot_environment(values)

    values = _valid_environment(tmp_path)
    values["SIGNED_INTAKE_PUBLIC_KEY_HOST_FILE"] = values[
        "MODEL_RELEASE_SIGNING_PUBLIC_KEY_HOST_FILE"
    ]
    with pytest.raises(PilotPreflightError, match="must be separate"):
        validate_pilot_environment(values)

    values = _valid_environment(tmp_path)
    invalid_key = _private_file(tmp_path / "invalid-intake.pub", "not-an-ed25519-public-key")
    values["SIGNED_INTAKE_PUBLIC_KEY_HOST_FILE"] = os.fspath(invalid_key)
    with pytest.raises(PilotPreflightError, match="not admissible"):
        validate_pilot_environment(values)


def test_disk_capacity_fails_closed_without_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def low_capacity(_path: object) -> SimpleNamespace:
        return SimpleNamespace(
            total=MINIMUM_FREE_BYTES,
            used=1,
            free=MINIMUM_FREE_BYTES - 1,
        )

    monkeypatch.setattr(
        pilot_preflight.shutil,
        "disk_usage",
        low_capacity,
    )

    with pytest.raises(PilotPreflightError, match="no cleanup was run"):
        ensure_minimum_disk_space(tmp_path)


def test_only_read_only_host_commands_are_admitted() -> None:
    pilot_preflight.assert_read_only_command(
        ["docker", "compose", "--file", "compose.yml", "config", "--format", "json"]
    )
    pilot_preflight.assert_read_only_command(["docker", "system", "df"])

    for command in (
        ["docker", "system", "prune"],
        ["docker", "compose", "down", "--volumes"],
        ["rm", "-rf", "backup"],
        ["python", "scripts/qualify_restore_drill.py"],
    ):
        with pytest.raises(PilotPreflightError, match="non-read-only"):
            pilot_preflight.assert_read_only_command(command)


def test_release_qualification_is_validated_without_external_calls(tmp_path: Path) -> None:
    evidence = tmp_path / "qualification.json"
    evidence.write_text(json.dumps(_eligible_qualification()), encoding="utf-8")

    assert validate_pilot_qualification(evidence) == 25

    payload = _eligible_qualification()
    payload["candidate"]["stuck_cases"] = 1  # type: ignore[index]
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PilotPreflightError, match="no_loss_duplicate_or_stall"):
        validate_pilot_qualification(evidence)


def test_restore_preflight_verifies_off_host_contract_and_current_bytes(tmp_path: Path) -> None:
    values, minio_backup = _restore_fixture(tmp_path)

    binding = validate_restore_set(values)
    assert len(binding) == 64

    minio_backup.write_bytes(b"tampered")
    with pytest.raises(PilotPreflightError, match="five-artifact verification failed"):
        validate_restore_set(values)


def test_local_only_restore_report_cannot_admit_pilot(tmp_path: Path) -> None:
    values, _ = _restore_fixture(tmp_path)
    report_path = Path(values["PILOT_RESTORE_QUALIFICATION_REPORT"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["scope"] = "isolated-local-synthetic-no-external-side-effects"
    report["encrypted_off_host_copy_qualified"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(PilotPreflightError, match="did not pass on pilot hardware"):
        validate_restore_set(values)
