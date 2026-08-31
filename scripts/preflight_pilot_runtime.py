#!/usr/bin/env python3
"""Fail-closed, read-only admission checks for the separate pilot runtime."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import ValidationError

from app.adapters.security.signed_intake_signatures import (
    SignedIntakeKeyConfigurationError,
    load_ed25519_public_key_file,
)
from app.platform.pilot_qualification import (
    PilotQualificationEvidence,
    assess_limited_pilot,
)
from scripts.restore_manifest import (
    ARTIFACT_ROLES,
    RestoreManifestError,
    load_manifest,
    verify_manifest,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE: Final = REPO_ROOT / "infra/pilot/.env.pilot"
COMPOSE_FILES: Final = (
    REPO_ROOT / "infra/compose.core.yml",
    REPO_ROOT / "infra/compose.rls.yml",
    REPO_ROOT / "infra/evidence/compose.evidence-security.yml",
    REPO_ROOT / "infra/pilot/compose.pilot.yml",
)
MINIMUM_FREE_BYTES: Final = 30 * 1024**3
MAX_ENV_BYTES: Final = 128 * 1024
MAX_JSON_BYTES: Final = 4 * 1024 * 1024
MAX_COMMAND_OUTPUT_BYTES: Final = 8 * 1024 * 1024
_ENV_NAME: Final = re.compile(r"^[A-Z][A-Z0-9_]{1,95}$")
_SHA256: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT: Final = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_TAG: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_MODEL_ROUTE_DEPLOYMENT_ID: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_SIGNED_INTAKE_IDENTIFIER: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_SIGNED_INTAKE_PROVENANCE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,191}$")
SIGNED_INTAKE_PUBLIC_KEY_CONTAINER_PATH: Final = "/run/config/signed_intake_public_key.pem"
SIGNED_INTAKE_MAX_BODY_BYTES: Final = 128 * 1024
SIGNED_INTAKE_CLOCK_SKEW_SECONDS: Final = 300
SIGNED_INTAKE_CONFIGURATION_FIELDS: Final = frozenset(
    {"source_id", "tenant_id", "actor_user_id", "provenance", "public_key_file"}
)
_PLACEHOLDER_PARTS: Final = (
    "change-me",
    "changeme",
    "replace-me",
    "placeholder",
    "/absolute/path/to/",
    "<required>",
)


class PilotPreflightError(RuntimeError):
    """One bounded admission check failed without exposing its input value."""

    def __init__(self, check: str, message: str) -> None:
        super().__init__(message)
        self.check = check


def _fail(check: str, message: str) -> PilotPreflightError:
    return PilotPreflightError(check, message)


def load_private_env(path: Path) -> dict[str, str]:
    """Read an owner-only dotenv file without expanding variables or printing values."""

    try:
        metadata = path.lstat()
    except OSError as error:
        raise _fail("pilot_env", "pilot env file is missing") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise _fail("pilot_env", "pilot env must be a regular non-symlink file")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise _fail("pilot_env", "pilot env must be owner-owned with no group/other access")
    if metadata.st_size <= 0 or metadata.st_size > MAX_ENV_BYTES:
        raise _fail("pilot_env", "pilot env has an invalid size")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise _fail("pilot_env", "pilot env is not readable UTF-8") from error

    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or "=" not in line:
            raise _fail("pilot_env", "pilot env contains a malformed assignment")
        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not _ENV_NAME.fullmatch(name) or name in values:
            raise _fail("pilot_env", "pilot env contains an invalid or duplicate key")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    return values


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    lowered = value.casefold()
    if not value or any(part in lowered for part in _PLACEHOLDER_PARTS):
        raise _fail("pilot_env", f"{name} is missing or still a placeholder")
    return value


def _require_exact(values: Mapping[str, str], name: str, expected: str) -> None:
    if values.get(name, "").strip().casefold() != expected.casefold():
        raise _fail("pilot_env", f"{name} must be {expected}")


def _require_secret(values: Mapping[str, str], name: str, *, minimum_bytes: int) -> None:
    value = _required(values, name)
    if len(value.encode("utf-8")) < minimum_bytes or any(
        character.isspace() for character in value
    ):
        raise _fail("pilot_env", f"{name} does not meet the pilot secret contract")


def _require_url(
    values: Mapping[str, str],
    name: str,
    *,
    https_only: bool,
    callback_path: str | None = None,
) -> None:
    parsed = urlsplit(_required(values, name))
    allowed_schemes = {"https"} if https_only else {"http", "https"}
    if (
        parsed.scheme not in allowed_schemes
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise _fail("pilot_env", f"{name} must be an approved URL without embedded credentials")
    if callback_path is not None and (
        parsed.path != callback_path or parsed.query or parsed.fragment
    ):
        raise _fail("pilot_env", f"{name} must target {callback_path} exactly")


def _absolute_path(values: Mapping[str, str], name: str) -> Path:
    path = Path(_required(values, name))
    if not path.is_absolute():
        raise _fail("pilot_env", f"{name} must be an absolute path")
    return path


def _validate_regular_file(path: Path, *, check: str, maximum_bytes: int) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise _fail(check, "required file is missing") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise _fail(check, "required file must be regular and non-symlink")
    if metadata.st_size <= 0 or metadata.st_size > maximum_bytes:
        raise _fail(check, "required file has an invalid size")


def _validate_secret_file(path: Path) -> None:
    _validate_regular_file(path, check="database_secret_files", maximum_bytes=4096)
    metadata = path.stat(follow_symlinks=False)
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise _fail(
            "database_secret_files",
            "database password files must be owner-owned with no group/other access",
        )
    try:
        value = path.read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeDecodeError) as error:
        raise _fail("database_secret_files", "database password file is unreadable") from error
    if "\n" in value or "\r" in value or len(value.encode("utf-8")) < 24:
        raise _fail(
            "database_secret_files",
            "database password files must contain one sufficiently long line",
        )


def _parse_signed_intake_sources(
    raw_sources: str,
    *,
    check: str,
    expected_tenant_id: str,
) -> Mapping[str, object]:
    if len(raw_sources.encode("utf-8")) > 16 * 1024:
        raise _fail(check, "SIGNED_INTAKE_SOURCES exceeds the pilot size limit")
    try:
        sources = json.loads(raw_sources)
    except json.JSONDecodeError as error:
        raise _fail(check, "SIGNED_INTAKE_SOURCES must be valid JSON") from error
    if not isinstance(sources, dict) or len(sources) != 1:
        raise _fail(check, "pilot requires exactly one signed intake source")

    key_id, source = next(iter(sources.items()))
    if not isinstance(key_id, str) or _SIGNED_INTAKE_IDENTIFIER.fullmatch(key_id) is None:
        raise _fail(check, "signed intake key identifier is invalid")
    if not isinstance(source, dict) or {str(name) for name in source} != set(
        SIGNED_INTAKE_CONFIGURATION_FIELDS
    ):
        raise _fail(check, "signed intake source fields do not match the frozen pilot contract")

    source_id = source.get("source_id")
    provenance = source.get("provenance")
    public_key_file = source.get("public_key_file")
    if not isinstance(source_id, str) or _SIGNED_INTAKE_IDENTIFIER.fullmatch(source_id) is None:
        raise _fail(check, "signed intake source identifier is invalid")
    if not isinstance(provenance, str) or _SIGNED_INTAKE_PROVENANCE.fullmatch(provenance) is None:
        raise _fail(check, "signed intake provenance is invalid")
    if public_key_file != SIGNED_INTAKE_PUBLIC_KEY_CONTAINER_PATH:
        raise _fail(check, "signed intake public key container path is not the frozen path")

    try:
        tenant_id = UUID(str(source.get("tenant_id")))
        actor_user_id = UUID(str(source.get("actor_user_id")))
        expected_tenant = UUID(expected_tenant_id)
    except ValueError as error:
        raise _fail(check, "signed intake tenant or service actor UUID is invalid") from error
    if tenant_id.int == 0 or actor_user_id.int == 0 or tenant_id == actor_user_id:
        raise _fail(check, "signed intake tenant and service actor identities are invalid")
    if tenant_id != expected_tenant:
        raise _fail(check, "signed intake tenant must match the one pilot retention tenant")
    return cast(Mapping[str, object], sources)


def _require_frozen_integer(
    values: Mapping[str, str], name: str, *, expected: int, check: str = "pilot_env"
) -> None:
    try:
        actual = int(values.get(name, "").strip())
    except ValueError as error:
        raise _fail(check, f"{name} must be the frozen pilot integer") from error
    if actual != expected:
        raise _fail(check, f"{name} must be {expected}")


def validate_pilot_environment(values: Mapping[str, str]) -> None:
    """Validate only deployment metadata; secret values are never returned or logged."""

    for name, expected in (
        ("ENVIRONMENT", "pilot"),
        ("DATABASE_RLS_REQUIRED", "true"),
        ("LEGACY_PASSWORD_AUTH_ENABLED", "false"),
        ("OIDC_ENABLED", "true"),
        ("OIDC_TLS_VERIFY", "true"),
        ("OIDC_ALLOW_INSECURE_HTTP", "false"),
        ("OIDC_COOKIE_SECURE", "true"),
        ("OTEL_ENABLED", "true"),
        ("OTEL_EXPORTER", "otlp_http"),
        ("PRIVACY_LIFECYCLE_AUTOMATION_ENABLED", "true"),
        ("SIGNED_INTAKE_ENABLED", "true"),
        ("MODEL_RELEASE_ENFORCEMENT", "true"),
        ("MODEL_ROUTE_ENFORCEMENT", "true"),
        ("MINIO_PRESIGNED_SECURE", "true"),
    ):
        _require_exact(values, name, expected)

    image_tag = _required(values, "CSIGHT_IMAGE_TAG")
    if not _IMAGE_TAG.fullmatch(image_tag) or image_tag.casefold() in {"dev", "latest"}:
        raise _fail("pilot_env", "CSIGHT_IMAGE_TAG must be an immutable non-development tag")
    if not _COMMIT.fullmatch(_required(values, "PILOT_RELEASE_COMMIT")):
        raise _fail("pilot_env", "PILOT_RELEASE_COMMIT must be an exact lowercase commit SHA")

    _require_secret(values, "POSTGRES_PASSWORD", minimum_bytes=24)
    _require_secret(values, "RABBITMQ_DEFAULT_PASS", minimum_bytes=24)
    _required(values, "MINIO_ACCESS_KEY")
    _require_secret(values, "MINIO_SECRET_KEY", minimum_bytes=32)
    _require_secret(values, "JWT_SECRET_KEY", minimum_bytes=32)

    for name in (
        "OIDC_ISSUER",
        "OIDC_AUTHORIZATION_ENDPOINT",
        "OIDC_TOKEN_ENDPOINT",
        "OIDC_JWKS_URI",
    ):
        _require_url(values, name, https_only=True)
    _require_url(
        values,
        "OIDC_REDIRECT_URI",
        https_only=True,
        callback_path="/auth/oidc/callback",
    )
    _required(values, "OIDC_CLIENT_ID")
    raw_mappings = _required(values, "OIDC_GROUP_MAPPINGS")
    try:
        mappings = json.loads(raw_mappings)
    except json.JSONDecodeError as error:
        raise _fail("pilot_env", "OIDC_GROUP_MAPPINGS must be valid JSON") from error
    if not isinstance(mappings, dict) or not mappings:
        raise _fail("pilot_env", "OIDC_GROUP_MAPPINGS must map at least one IdP group")

    _require_url(values, "OTEL_EXPORTER_OTLP_ENDPOINT", https_only=False)
    policy_version = _required(values, "SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION")
    if policy_version == "development/30d":
        raise _fail("pilot_env", "the development retention policy is not admitted for pilot")
    try:
        retention_days = int(_required(values, "SENSITIVE_PAYLOAD_RETENTION_DAYS"))
    except ValueError as error:
        raise _fail("pilot_env", "retention days must be an integer") from error
    if not 1 <= retention_days <= 3650:
        raise _fail("pilot_env", "retention days are outside the supported pilot range")
    try:
        retention_tenant_id = str(UUID(_required(values, "PRIVACY_LIFECYCLE_TENANT_ID")))
    except ValueError as error:
        raise _fail("pilot_env", "retention automation requires one exact tenant UUID") from error

    _parse_signed_intake_sources(
        _required(values, "SIGNED_INTAKE_SOURCES"),
        check="pilot_env",
        expected_tenant_id=retention_tenant_id,
    )
    _require_frozen_integer(
        values,
        "SIGNED_INTAKE_MAX_BODY_BYTES",
        expected=SIGNED_INTAKE_MAX_BODY_BYTES,
    )
    _require_frozen_integer(
        values,
        "SIGNED_INTAKE_CLOCK_SKEW_SECONDS",
        expected=SIGNED_INTAKE_CLOCK_SKEW_SECONDS,
    )

    if _required(values, "LLM_PROVIDER") != "vllm":
        raise _fail("pilot_env", "pilot LLM_PROVIDER must be the signed vLLM release path")
    if _required(values, "VISION_PROVIDER") != "remote":
        raise _fail("pilot_env", "pilot VISION_PROVIDER must be a qualified remote provider")
    for name in ("LLM_BASE_URL", "VISION_BASE_URL", "EMBEDDING_BASE_URL"):
        _require_url(values, name, https_only=False)
    _require_secret(values, "LLM_API_KEY", minimum_bytes=24)
    _require_secret(values, "VISION_API_KEY", minimum_bytes=24)
    for name in (
        "LLM_MODEL_ID",
        "LLM_MODEL_VERSION",
        "VISION_MODEL_ID",
        "VISION_MODEL_VERSION",
        "VISION_MODEL_REVISION",
        "MODEL_RELEASE_SIGNING_KEY_ID",
    ):
        _required(values, name)
    if _MODEL_ROUTE_DEPLOYMENT_ID.fullmatch(_required(values, "MODEL_ROUTE_DEPLOYMENT_ID")) is None:
        raise _fail("pilot_env", "MODEL_ROUTE_DEPLOYMENT_ID has an invalid format")
    if not _COMMIT.fullmatch(_required(values, "LLM_MODEL_REVISION")):
        raise _fail("pilot_env", "LLM_MODEL_REVISION must be an exact commit hash")
    for name in (
        "LLM_ARTIFACT_CONTENT_DIGEST",
        "LLM_RUNTIME_IMAGE_DIGEST",
        "LLM_DEPENDENCY_LOCK_DIGEST",
        "LLM_SBOM_DIGEST",
    ):
        if not _SHA256.fullmatch(_required(values, name)):
            raise _fail("pilot_env", f"{name} must be an exact SHA-256 digest")

    presigned_endpoint = _required(values, "MINIO_PRESIGNED_ENDPOINT")
    if "://" in presigned_endpoint or "/" in presigned_endpoint:
        raise _fail(
            "pilot_env",
            "MINIO_PRESIGNED_ENDPOINT must be an approved host[:port] without a scheme or path",
        )

    for name in (
        "API_DATABASE_PASSWORD_HOST_FILE",
        "WORKER_DATABASE_PASSWORD_HOST_FILE",
        "DISPATCHER_DATABASE_PASSWORD_HOST_FILE",
    ):
        _validate_secret_file(_absolute_path(values, name))
    public_key = _absolute_path(values, "MODEL_RELEASE_SIGNING_PUBLIC_KEY_HOST_FILE")
    _validate_regular_file(public_key, check="model_release_key", maximum_bytes=64 * 1024)
    intake_public_key = _absolute_path(values, "SIGNED_INTAKE_PUBLIC_KEY_HOST_FILE")
    if intake_public_key == public_key:
        raise _fail("signed_intake_key", "signed intake and model release keys must be separate")
    try:
        load_ed25519_public_key_file(intake_public_key)
    except SignedIntakeKeyConfigurationError as error:
        raise _fail("signed_intake_key", "signed intake public key is not admissible") from error

    wal_directory = _absolute_path(values, "POSTGRES_WAL_ARCHIVE_PATH")
    try:
        wal_metadata = wal_directory.lstat()
    except OSError as error:
        raise _fail("wal_archive", "WAL archive directory is missing") from error
    if stat.S_ISLNK(wal_metadata.st_mode) or not stat.S_ISDIR(wal_metadata.st_mode):
        raise _fail("wal_archive", "WAL archive must be an existing non-symlink directory")
    if not os.access(wal_directory, os.R_OK | os.W_OK | os.X_OK):
        raise _fail("wal_archive", "WAL archive directory is not accessible to the operator")


def ensure_minimum_disk_space(path: Path) -> float:
    """Check capacity only; never prune, remove, truncate, or write."""

    try:
        free_bytes = shutil.disk_usage(path).free
    except OSError as error:
        raise _fail("disk_capacity", "disk capacity could not be read") from error
    if free_bytes < MINIMUM_FREE_BYTES:
        raise _fail("disk_capacity", "less than the required 30 GiB is free; no cleanup was run")
    return round(free_bytes / 1024**3, 2)


def _safe_subprocess_environment() -> dict[str, str]:
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    for name in ("HOME", "DOCKER_CONFIG", "DOCKER_HOST", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR"):
        if value := os.environ.get(name):
            environment[name] = value
    return environment


def assert_read_only_command(arguments: Sequence[str]) -> None:
    if not arguments:
        raise _fail("internal_command", "an empty host command was rejected")
    executable = Path(arguments[0]).name
    tail = tuple(arguments[1:])
    allowed = False
    if executable == "git":
        allowed = tail in {
            ("status", "--porcelain=v1", "--untracked-files=all"),
            ("rev-parse", "HEAD"),
        }
    elif executable == "docker":
        allowed = (
            tail[:2] == ("system", "df")
            or tail[:1] == ("info",)
            or tail[:2] == ("image", "inspect")
            or (tail[:1] == ("compose",) and "config" in tail and "up" not in tail)
        )
    if not allowed:
        raise _fail("internal_command", "preflight rejected a non-read-only host command")


def _run_read_only(
    arguments: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int = 60,
) -> str:
    assert_read_only_command(arguments)
    try:
        completed = subprocess.run(
            list(arguments),
            cwd=cwd,
            env=_safe_subprocess_environment(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise _fail("host_probe", f"read-only {Path(arguments[0]).name} probe failed") from error
    if len(completed.stdout.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES:
        raise _fail("host_probe", "read-only host probe output exceeded the safety limit")
    return completed.stdout.strip()


def validate_clean_release(values: Mapping[str, str], *, repo_root: Path) -> str:
    status = _run_read_only(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=repo_root
    )
    if status:
        raise _fail("release_tree", "pilot start requires a clean tracked and untracked worktree")
    commit = _run_read_only(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if commit != _required(values, "PILOT_RELEASE_COMMIT"):
        raise _fail("release_tree", "current HEAD does not match PILOT_RELEASE_COMMIT")
    return commit


def _load_json(path: Path, *, check: str) -> Mapping[str, object]:
    _validate_regular_file(path, check=check, maximum_bytes=MAX_JSON_BYTES)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail(check, "required evidence is not valid bounded UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise _fail(check, "required evidence must be a JSON object")
    return cast(Mapping[str, object], payload)


def validate_pilot_qualification(path: Path) -> int:
    payload = _load_json(path, check="pilot_qualification")
    try:
        evidence = PilotQualificationEvidence.model_validate(payload)
    except ValidationError as error:
        raise _fail("pilot_qualification", "limited-pilot evidence schema is invalid") from error
    result = assess_limited_pilot(evidence)
    failing = tuple(check.name for check in result.checks if check.status.value != "PASS")
    if not result.eligible or failing:
        names = ",".join(failing) if failing else "unknown"
        raise _fail("pilot_qualification", f"limited-pilot release gates failed: {names}")
    return len(result.checks)


def _number(payload: Mapping[str, object], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail("restore_evidence", f"restore report field {name} is invalid")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise _fail("restore_evidence", f"restore report field {name} is invalid")
    return normalized


def validate_restore_set(values: Mapping[str, str]) -> str:
    manifest_path = _absolute_path(values, "PILOT_RESTORE_MANIFEST")
    artifacts = {
        "postgresql_base_backup": _absolute_path(values, "PILOT_POSTGRES_BASE_BACKUP"),
        "postgresql_wal_archive": _absolute_path(values, "PILOT_POSTGRES_WAL_ARCHIVE"),
        "minio_version_inventory": _absolute_path(values, "PILOT_MINIO_VERSION_INVENTORY"),
        "minio_version_backup": _absolute_path(values, "PILOT_MINIO_VERSION_BACKUP"),
        "runtime_version_manifest": _absolute_path(values, "PILOT_RUNTIME_VERSION_MANIFEST"),
    }
    if set(artifacts) != set(ARTIFACT_ROLES):
        raise _fail("restore_evidence", "the five-artifact restore set is incomplete")
    try:
        manifest = load_manifest(manifest_path)
        verification = verify_manifest(manifest, artifacts=artifacts)
    except RestoreManifestError as error:
        raise _fail("restore_evidence", f"five-artifact verification failed: {error}") from error

    binding = verification.get("binding_sha256")
    if not isinstance(binding, str) or not _SHA256.fullmatch(f"sha256:{binding}"):
        raise _fail("restore_evidence", "restore manifest binding is invalid")

    report = _load_json(
        _absolute_path(values, "PILOT_RESTORE_QUALIFICATION_REPORT"),
        check="restore_evidence",
    )
    required_true = (
        "rpo_passed",
        "rto_passed",
        "encrypted_off_host_copy_qualified",
        "immutable_off_host_copy_qualified",
        "independent_key_resolution_qualified",
        "scheduled_backup_qualified",
    )
    if report.get("schema_version") != "csight.restore_drill_qualification/1.0.0":
        raise _fail("restore_evidence", "restore qualification schema is not admitted")
    if report.get("status") != "PASS" or report.get("scope") != (
        "encrypted-immutable-off-host-pilot-hardware"
    ):
        raise _fail("restore_evidence", "restore qualification did not pass on pilot hardware")
    if any(report.get(name) is not True for name in required_true):
        raise _fail("restore_evidence", "off-host backup qualification is incomplete")
    if report.get("target_host_repeat_required") is not False:
        raise _fail("restore_evidence", "target-host restore repetitions remain required")
    repeats = report.get("pilot_hardware_repeat_count")
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 2:
        raise _fail("restore_evidence", "two target-host restore drills are required")
    if _number(report, "rpo_minutes") > 60 or _number(report, "rto_minutes") > 240:
        raise _fail("restore_evidence", "restore evidence exceeds the RPO or RTO objective")
    if report.get("external_business_side_effects") != 0:
        raise _fail("restore_evidence", "restore drill recorded an external business side effect")
    accepted_at = report.get("accepted_at")
    if not isinstance(accepted_at, str):
        raise _fail("restore_evidence", "restore acceptance timestamp is missing")
    try:
        accepted = datetime.fromisoformat(accepted_at)
    except ValueError as error:
        raise _fail("restore_evidence", "restore acceptance timestamp is invalid") from error
    if accepted.tzinfo is None:
        raise _fail("restore_evidence", "restore acceptance timestamp must include a timezone")
    report_manifest = report.get("manifest")
    if (
        not isinstance(report_manifest, dict)
        or report_manifest.get("status") != "PASS"
        or report_manifest.get("binding_sha256") != binding
    ):
        raise _fail("restore_evidence", "restore report is not bound to the verified recovery set")
    return binding


def _compose_command(env_file: Path) -> list[str]:
    docker = shutil.which("docker") or "docker"
    command = [docker, "compose", "--env-file", os.fspath(env_file)]
    for compose_file in COMPOSE_FILES:
        command.extend(("--file", os.fspath(compose_file)))
    command.extend(("--profile", "pilot-maintenance", "config", "--format", "json"))
    return command


def _service_environment(config: Mapping[str, object], service_name: str) -> Mapping[str, object]:
    services = config.get("services")
    if not isinstance(services, dict) or not isinstance(services.get(service_name), dict):
        raise _fail("compose_config", f"required service {service_name} is missing")
    service = cast(dict[str, object], services[service_name])
    environment = service.get("environment")
    if not isinstance(environment, dict):
        raise _fail("compose_config", f"required service {service_name} has no environment")
    return cast(Mapping[str, object], environment)


def _service_configs(
    config: Mapping[str, object], service_name: str
) -> tuple[Mapping[str, object], ...]:
    services = config.get("services")
    if not isinstance(services, dict) or not isinstance(services.get(service_name), dict):
        raise _fail("compose_config", f"required service {service_name} is missing")
    service = cast(dict[str, object], services[service_name])
    configured = service.get("configs", [])
    if not isinstance(configured, list) or any(not isinstance(item, dict) for item in configured):
        raise _fail("compose_config", f"service {service_name} has invalid config mounts")
    return tuple(cast(Mapping[str, object], item) for item in configured)


def _expect_environment(
    config: Mapping[str, object], service_name: str, expected: Mapping[str, str]
) -> None:
    environment = _service_environment(config, service_name)
    for name, value in expected.items():
        if str(environment.get(name, "")).casefold() != value.casefold():
            raise _fail("compose_config", f"{service_name} does not enforce {name}={value}")


def validate_compose_config(config: Mapping[str, object], *, image_tag: str) -> None:
    if config.get("name") != "csight-pilot":
        raise _fail("compose_config", "pilot overlay did not select the isolated project name")
    runtime_services = (
        "api",
        "worker-model",
        "worker-retrieval",
        "worker-decision",
        "dispatcher",
        "privacy-lifecycle",
    )
    for service_name in runtime_services:
        _expect_environment(
            config,
            service_name,
            {
                "ENVIRONMENT": "pilot",
                "OTEL_ENABLED": "true",
                "OTEL_EXPORTER": "otlp_http",
            },
        )
    for service_name in (
        "api",
        "worker-model",
        "worker-retrieval",
        "worker-decision",
        "dispatcher",
        "privacy-lifecycle",
    ):
        _expect_environment(config, service_name, {"DATABASE_RLS_REQUIRED": "true"})
    _expect_environment(
        config,
        "api",
        {
            "LEGACY_PASSWORD_AUTH_ENABLED": "false",
            "OIDC_ENABLED": "true",
            "OIDC_TLS_VERIFY": "true",
            "OIDC_ALLOW_INSECURE_HTTP": "false",
            "OIDC_COOKIE_SECURE": "true",
            "EVIDENCE_IMAGE_SANITIZATION_ENABLED": "true",
            "EVIDENCE_MALWARE_SCANNER": "clamav",
            "CLAMAV_HOST": "clamav",
            "OPERATIONS_FAILURE_RECOVERY_MUTATIONS_ENABLED": "false",
            "SIGNED_INTAKE_ENABLED": "true",
            "SIGNED_INTAKE_MAX_BODY_BYTES": str(SIGNED_INTAKE_MAX_BODY_BYTES),
            "SIGNED_INTAKE_CLOCK_SKEW_SECONDS": str(SIGNED_INTAKE_CLOCK_SKEW_SECONDS),
            "MODEL_ROUTE_ENFORCEMENT": "true",
        },
    )
    _expect_environment(
        config,
        "worker-model",
        {"MODEL_ROUTE_ENFORCEMENT": "true"},
    )
    _expect_environment(
        config,
        "privacy-lifecycle",
        {"PRIVACY_LIFECYCLE_AUTOMATION_ENABLED": "true"},
    )

    for service_name in ("api", "worker-model", "worker-retrieval"):
        _expect_environment(
            config,
            service_name,
            {"LLM_PROVIDER": "vllm", "MODEL_RELEASE_ENFORCEMENT": "true"},
        )
    _expect_environment(config, "api", {"VISION_PROVIDER": "remote"})
    _expect_environment(config, "worker-model", {"VISION_PROVIDER": "remote"})
    for service_name in ("worker-decision", "dispatcher", "privacy-lifecycle"):
        _expect_environment(
            config,
            service_name,
            {
                "LLM_PROVIDER": "mock",
                "VISION_PROVIDER": "mock",
                "MODEL_RELEASE_ENFORCEMENT": "false",
                "MODEL_ROUTE_ENFORCEMENT": "false",
            },
        )
    environments = {
        name: _service_environment(config, name)
        for name in (
            "api",
            "worker-model",
            "worker-retrieval",
            "worker-decision",
            "dispatcher",
            "privacy-lifecycle",
        )
    }
    deployment_id = str(environments["worker-model"].get("MODEL_ROUTE_DEPLOYMENT_ID", ""))
    if _MODEL_ROUTE_DEPLOYMENT_ID.fullmatch(deployment_id) is None:
        raise _fail("compose_config", "model Worker route deployment identity is invalid")
    route_forbidden_services = (
        "worker-retrieval",
        "worker-decision",
        "dispatcher",
        "privacy-lifecycle",
    )
    _expect_environment(
        config,
        "worker-retrieval",
        {"MODEL_ROUTE_ENFORCEMENT": "false"},
    )
    if "MODEL_ROUTE_DEPLOYMENT_ID" in environments["api"]:
        raise _fail("compose_config", "API must not receive a model route deployment identity")
    for service_name in route_forbidden_services:
        if "MODEL_ROUTE_DEPLOYMENT_ID" in environments[service_name]:
            raise _fail(
                "compose_config",
                f"{service_name} must not receive a model route deployment identity",
            )
    privacy_tenant = str(environments["privacy-lifecycle"].get("PRIVACY_LIFECYCLE_TENANT_ID", ""))
    _parse_signed_intake_sources(
        str(environments["api"].get("SIGNED_INTAKE_SOURCES", "")),
        check="compose_config",
        expected_tenant_id=privacy_tenant,
    )
    api_intake_mounts = tuple(
        item
        for item in _service_configs(config, "api")
        if item.get("source") == "signed-intake-public-key"
        or item.get("target") == SIGNED_INTAKE_PUBLIC_KEY_CONTAINER_PATH
    )
    if len(api_intake_mounts) != 1 or api_intake_mounts[0].get("target") != (
        SIGNED_INTAKE_PUBLIC_KEY_CONTAINER_PATH
    ):
        raise _fail("compose_config", "API must mount exactly one signed intake public key")
    signed_intake_names = {
        "SIGNED_INTAKE_ENABLED",
        "SIGNED_INTAKE_SOURCES",
        "SIGNED_INTAKE_MAX_BODY_BYTES",
        "SIGNED_INTAKE_CLOCK_SKEW_SECONDS",
    }
    for service_name in (
        "worker-model",
        "worker-retrieval",
        "worker-decision",
        "dispatcher",
        "privacy-lifecycle",
    ):
        if signed_intake_names & environments[service_name].keys():
            raise _fail("compose_config", f"{service_name} must not receive signed intake settings")
        if any(
            item.get("source") == "signed-intake-public-key"
            or item.get("target") == SIGNED_INTAKE_PUBLIC_KEY_CONTAINER_PATH
            for item in _service_configs(config, service_name)
        ):
            raise _fail("compose_config", f"{service_name} must not mount the signed intake key")
    if environments["api"].get("LLM_API_KEY") or environments["api"].get("VISION_API_KEY"):
        raise _fail("compose_config", "API must not receive model provider credentials")
    if not environments["worker-model"].get("LLM_API_KEY") or not environments["worker-model"].get(
        "VISION_API_KEY"
    ):
        raise _fail("compose_config", "model Worker requires only its two provider credentials")
    if not environments["worker-retrieval"].get("LLM_API_KEY") or environments[
        "worker-retrieval"
    ].get("VISION_API_KEY"):
        raise _fail("compose_config", "retrieval Worker credential scope is invalid")
    for service_name in ("worker-decision", "dispatcher", "privacy-lifecycle"):
        if environments[service_name].get("LLM_API_KEY") or environments[service_name].get(
            "VISION_API_KEY"
        ):
            raise _fail(
                "compose_config", f"{service_name} must not receive model provider credentials"
            )

    services = cast(dict[str, object], config.get("services"))
    clamav = services.get("clamav")
    if not isinstance(clamav, dict):
        raise _fail("compose_config", "internal ClamAV service is missing")
    image = clamav.get("image")
    if not isinstance(image, str) or "@sha256:" not in image or clamav.get("ports"):
        raise _fail("compose_config", "ClamAV must be digest-pinned and internal-only")
    for service_name, expected_image in (
        ("api", f"csight-core:{image_tag}"),
        ("web", f"csight-web:{image_tag}"),
    ):
        service = services.get(service_name)
        if not isinstance(service, dict) or service.get("image") != expected_image:
            raise _fail("compose_config", f"{service_name} image tag is not release-bound")


def validate_docker_runtime(
    values: Mapping[str, str], *, env_file: Path, repo_root: Path
) -> Mapping[str, object]:
    _run_read_only(
        [shutil.which("docker") or "docker", "info", "--format", "{{.ServerVersion}}"],
        cwd=repo_root,
    )
    _run_read_only(
        [shutil.which("docker") or "docker", "system", "df", "--format", "{{json .}}"],
        cwd=repo_root,
    )
    raw_config = _run_read_only(_compose_command(env_file), cwd=repo_root, timeout_seconds=120)
    try:
        config = json.loads(raw_config)
    except json.JSONDecodeError as error:
        raise _fail(
            "compose_config", "Docker Compose returned invalid configuration JSON"
        ) from error
    if not isinstance(config, dict):
        raise _fail("compose_config", "Docker Compose configuration is not an object")
    typed_config = cast(Mapping[str, object], config)
    image_tag = _required(values, "CSIGHT_IMAGE_TAG")
    validate_compose_config(typed_config, image_tag=image_tag)
    docker = shutil.which("docker") or "docker"
    for image_name in (f"csight-core:{image_tag}", f"csight-web:{image_tag}"):
        image_id = _run_read_only(
            [docker, "image", "inspect", "--format", "{{.Id}}", image_name],
            cwd=repo_root,
        )
        if not _SHA256.fullmatch(image_id):
            raise _fail("release_images", "a release-tagged pilot image is missing or invalid")
    return typed_config


def run_preflight(*, repo_root: Path, env_file: Path) -> dict[str, object]:
    absolute_env_file = env_file if env_file.is_absolute() else repo_root / env_file
    values = load_private_env(absolute_env_file)
    validate_pilot_environment(values)
    free_gib = ensure_minimum_disk_space(repo_root)
    release_commit = validate_clean_release(values, repo_root=repo_root)
    qualification_checks = validate_pilot_qualification(
        _absolute_path(values, "PILOT_QUALIFICATION_EVIDENCE")
    )
    restore_binding = validate_restore_set(values)
    config = validate_docker_runtime(values, env_file=absolute_env_file, repo_root=repo_root)
    return {
        "schema_version": "csight.pilot_preflight/1.0.0",
        "status": "PASS",
        "compose_project": config.get("name"),
        "release_commit": release_commit,
        "free_disk_gib": free_gib,
        "minimum_free_disk_gib": MINIMUM_FREE_BYTES // 1024**3,
        "qualification_check_count": qualification_checks,
        "restore_binding_sha256": restore_binding,
        "read_only_preflight": True,
        "mutations_performed": 0,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    try:
        result = run_preflight(repo_root=REPO_ROOT, env_file=cast(Path, arguments.env_file))
    except PilotPreflightError as error:
        result = {
            "schema_version": "csight.pilot_preflight/1.0.0",
            "status": "FAIL",
            "check": error.check,
            "error": str(error),
            "read_only_preflight": True,
            "mutations_performed": 0,
        }
        print(json.dumps(result, ensure_ascii=True, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
