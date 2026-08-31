#!/usr/bin/env python3
"""Run an isolated PostgreSQL WAL and MinIO version restore qualification."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.restore_manifest import (
    ARTIFACT_ROLES,
    RestoreManifestError,
    build_manifest,
    verify_manifest,
    write_manifest,
)

PROJECT_NAME = "csight-restore-qualification"
POSTGRES_IMAGE_DIGEST = "sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b"
MINIO_IMAGE_DIGEST = "sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    check: bool = True,
    timeout: float = 240,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _compose(repo_root: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        PROJECT_NAME,
        "--file",
        str(repo_root / "infra/restore/compose.restore-qualification.yml"),
    ]


def _compose_run(
    compose: list[str],
    repo_root: Path,
    env: dict[str, str],
    service: str,
    *arguments: str,
    timeout: float = 240,
) -> str:
    result = _run(
        [
            *compose,
            "--profile",
            "tools",
            "run",
            "--rm",
            "--no-deps",
            service,
            *arguments,
        ],
        cwd=repo_root,
        env=env,
        timeout=timeout,
    )
    return result.stdout.strip()


def _psql(
    compose: list[str],
    repo_root: Path,
    env: dict[str, str],
    service: str,
    sql: str,
) -> str:
    result = _run(
        [
            *compose,
            "exec",
            "--no-TTY",
            service,
            "psql",
            "--username",
            "csight",
            "--dbname",
            "csight",
            "--tuples-only",
            "--no-align",
            "--set",
            "ON_ERROR_STOP=1",
            "--command",
            sql,
        ],
        cwd=repo_root,
        env=env,
    )
    return result.stdout.strip()


def _wait_for_archive(
    compose: list[str], repo_root: Path, env: dict[str, str], baseline: int
) -> int:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        value = int(
            _psql(
                compose,
                repo_root,
                env,
                "source-postgres",
                "SELECT archived_count FROM pg_stat_archiver;",
            )
        )
        if value > baseline:
            return value
        time.sleep(0.5)
    raise RuntimeError("PostgreSQL WAL archive did not advance")


def _runtime_manifest(repo_root: Path, evidence: Path) -> dict[str, object]:
    image_id = _run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", "csight-core:dev"],
        cwd=repo_root,
        env=os.environ.copy(),
    ).stdout.strip()
    migration_head = _run(
        ["uv", "run", "alembic", "heads"],
        cwd=repo_root,
        env=os.environ.copy(),
    ).stdout.split()[0]
    manifest = {
        "schema_version": "csight.runtime_restore_identity/1.0.0",
        "application_image_id": image_id,
        "migration_head": migration_head,
        "policy_document_version": "qualification-synthetic/1.0.0",
        "policy_rule_version": "qualification-synthetic/1.0.0",
        "retrieval_index_version": "qualification-synthetic/1.0.0",
        "model_revision": "mock-restore-qualification/1.0.0",
        "prompt_schema_version": "analysis-output/2.0.0",
        "threshold_version": "qualification-synthetic/1.0.0",
        "settings_profile_sha256": hashlib.sha256(
            b"restore-qualification:no-external-side-effects"
        ).hexdigest(),
        "external_business_actions_enabled": False,
    }
    path = evidence / "runtime-version-manifest" / "runtime.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _artifact_paths(evidence: Path) -> dict[str, Path]:
    return {
        "postgresql_base_backup": evidence / "postgresql-base-backup",
        "postgresql_wal_archive": evidence / "postgresql-wal-archive",
        "minio_version_inventory": evidence / "minio-version-inventory",
        "minio_version_backup": evidence / "minio-version-backup",
        "runtime_version_manifest": evidence / "runtime-version-manifest",
    }


def _tamper_gate(manifest: dict[str, object], artifacts: dict[str, Path], evidence: Path) -> bool:
    original = artifacts["minio_version_backup"] / "minio-data.tar.gz"
    tampered_root = evidence / "tamper-probe"
    tampered_root.mkdir()
    tampered = tampered_root / "minio-data.tar.gz"
    shutil.copyfile(original, tampered)
    with tampered.open("ab") as stream:
        stream.write(b"tampered")
    probe_artifacts = dict(artifacts)
    probe_artifacts["minio_version_backup"] = tampered_root
    try:
        verify_manifest(manifest, artifacts=probe_artifacts)
    except RestoreManifestError:
        return True
    raise RuntimeError("tampered MinIO version backup was accepted")


def _prepare_evidence(evidence: Path) -> None:
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True, mode=0o777)
    evidence.chmod(0o777)
    for name in (
        "postgresql-wal-archive",
        "minio-version-inventory",
        "minio-version-backup",
        "runtime-version-manifest",
    ):
        (evidence / name).mkdir(mode=0o777)


def run(output_dir: Path) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    evidence = output_dir.resolve()
    _prepare_evidence(evidence)
    env = os.environ.copy()
    env["RESTORE_EVIDENCE_DIR"] = os.fspath(evidence)
    compose = _compose(repo_root)
    started_at = datetime.now(UTC)
    incident_at: datetime | None = None
    report: dict[str, Any]
    try:
        _run(
            [*compose, "up", "--detach", "--wait", "source-postgres", "source-minio"],
            cwd=repo_root,
            env=env,
        )
        _compose_run(
            compose,
            repo_root,
            env,
            "utility",
            "alembic",
            "upgrade",
            "head",
        )
        _psql(
            compose,
            repo_root,
            env,
            "source-postgres",
            (
                "CREATE TABLE restore_drill_probe (sequence integer PRIMARY KEY, "
                "created_at timestamptz NOT NULL DEFAULT clock_timestamp());"
                "INSERT INTO restore_drill_probe(sequence) VALUES (1);"
            ),
        )
        seed = json.loads(
            _compose_run(
                compose,
                repo_root,
                env,
                "utility",
                "python",
                "/qualification/restore_drill_probe.py",
                "seed-minio",
            ).splitlines()[-1]
        )
        _run([*compose, "stop", "source-minio"], cwd=repo_root, env=env)
        minio_snapshot = json.loads(
            _compose_run(
                compose,
                repo_root,
                env,
                "utility",
                "python",
                "/qualification/restore_drill_probe.py",
                "snapshot-minio",
            ).splitlines()[-1]
        )
        _run([*compose, "start", "source-minio"], cwd=repo_root, env=env)

        base_path = evidence / "postgresql-base-backup"
        _run(
            [
                *compose,
                "exec",
                "--no-TTY",
                "--user",
                "postgres",
                "source-postgres",
                "pg_basebackup",
                "--host=/var/run/postgresql",
                "--username=csight",
                f"--pgdata=/evidence/{base_path.name}",
                "--format=plain",
                "--wal-method=stream",
                "--checkpoint=fast",
                "--no-password",
            ],
            cwd=repo_root,
            env=env,
        )
        _run(
            [
                *compose,
                "exec",
                "--no-TTY",
                "source-postgres",
                "pg_verifybackup",
                f"/evidence/{base_path.name}",
            ],
            cwd=repo_root,
            env=env,
        )
        archived_before = int(
            _psql(
                compose,
                repo_root,
                env,
                "source-postgres",
                "SELECT archived_count FROM pg_stat_archiver;",
            )
        )
        recovery_point_raw = _psql(
            compose,
            repo_root,
            env,
            "source-postgres",
            (
                "INSERT INTO restore_drill_probe(sequence) VALUES (2);"
                "SELECT pg_switch_wal();"
                "SELECT max(created_at) AT TIME ZONE 'UTC' FROM restore_drill_probe;"
            ),
        ).splitlines()[-1]
        archived_after = _wait_for_archive(compose, repo_root, env, archived_before)
        recovery_point = datetime.fromisoformat(recovery_point_raw).replace(tzinfo=UTC)

        runtime_identity = _runtime_manifest(repo_root, evidence)
        artifacts = _artifact_paths(evidence)
        manifest = build_manifest(
            backup_id=f"restore-qualification-{started_at.strftime('%Y%m%dT%H%M%SZ')}",
            postgresql_version="16",
            minio_version="RELEASE.2025-09-07T16-13-09Z",
            encryption_key_id="local-qualification-unencrypted",
            artifacts=artifacts,
        )
        manifest_path = evidence / "restore-manifest.json"
        write_manifest(manifest_path, manifest)
        manifest_verification = verify_manifest(manifest, artifacts=artifacts)
        tamper_rejected = _tamper_gate(manifest, artifacts, evidence)
        shutil.rmtree(evidence / "tamper-probe")

        incident_at = datetime.now(UTC)
        _run([*compose, "stop", "source-postgres", "source-minio"], cwd=repo_root, env=env)
        pg_init = json.loads(
            _compose_run(
                compose,
                repo_root,
                env,
                "utility",
                "python",
                "/qualification/restore_drill_probe.py",
                "restore-postgres",
            ).splitlines()[-1]
        )
        minio_init = json.loads(
            _compose_run(
                compose,
                repo_root,
                env,
                "utility",
                "python",
                "/qualification/restore_drill_probe.py",
                "restore-minio",
            ).splitlines()[-1]
        )
        _run(
            [
                *compose,
                "--profile",
                "restore",
                "up",
                "--detach",
                "--wait",
                "restored-postgres",
                "restored-minio",
            ],
            cwd=repo_root,
            env=env,
        )
        probe_count = int(
            _psql(
                compose,
                repo_root,
                env,
                "restored-postgres",
                "SELECT count(*) FROM restore_drill_probe;",
            )
        )
        if probe_count != 2:
            raise RuntimeError("PostgreSQL WAL replay did not restore the post-base-backup row")
        restored_head = _psql(
            compose,
            repo_root,
            env,
            "restored-postgres",
            "SELECT version_num FROM alembic_version;",
        )
        if restored_head != runtime_identity["migration_head"]:
            raise RuntimeError("restored migration head does not match runtime manifest")
        minio_result = json.loads(
            _compose_run(
                compose,
                repo_root,
                env,
                "utility",
                "python",
                "/qualification/restore_drill_probe.py",
                "verify-minio",
                "--endpoint",
                "restored-minio:9000",
            ).splitlines()[-1]
        )
        accepted_at = datetime.now(UTC)
        rpo_minutes = max(0.0, (incident_at - recovery_point).total_seconds() / 60)
        rto_minutes = (accepted_at - incident_at).total_seconds() / 60
        report = {
            "schema_version": "csight.restore_drill_qualification/1.0.0",
            "status": "PASS",
            "scope": "isolated-local-synthetic-no-external-side-effects",
            "started_at": started_at.isoformat(),
            "incident_at": incident_at.isoformat(),
            "accepted_at": accepted_at.isoformat(),
            "rpo_minutes": round(rpo_minutes, 4),
            "rpo_target_minutes": 60,
            "rpo_passed": rpo_minutes <= 60,
            "rto_minutes": round(rto_minutes, 4),
            "rto_target_minutes": 240,
            "rto_passed": rto_minutes <= 240,
            "manifest": manifest_verification,
            "manifest_role_count": len(ARTIFACT_ROLES),
            "minio_backup_bound_to_manifest": True,
            "tampered_minio_backup_rejected": tamper_rejected,
            "postgresql": {
                "image_digest": POSTGRES_IMAGE_DIGEST,
                "archived_wal_segments_advanced": archived_after > archived_before,
                "pg_verifybackup_passed": True,
                "post_base_backup_row_replayed": True,
                "probe_row_count": probe_count,
                "migration_head_matched": True,
                "restore_init": pg_init,
            },
            "minio": {
                "image_digest": MINIO_IMAGE_DIGEST,
                "source_inventory": seed,
                "snapshot": minio_snapshot,
                "restored_inventory": minio_result,
                "versions_and_delete_markers_matched": True,
                "restore_init": minio_init,
            },
            "runtime_identity_matched": True,
            "external_business_side_effects": 0,
            "encrypted_off_host_copy_qualified": False,
            "target_host_repeat_required": True,
            "error": None,
        }
    except (
        OSError,
        ValueError,
        RuntimeError,
        RestoreManifestError,
        subprocess.SubprocessError,
    ) as error:
        report = {
            "schema_version": "csight.restore_drill_qualification/1.0.0",
            "status": "FAIL",
            "scope": "isolated-local-synthetic-no-external-side-effects",
            "started_at": started_at.isoformat(),
            "incident_at": incident_at.isoformat() if incident_at is not None else None,
            "finished_at": datetime.now(UTC).isoformat(),
            "external_business_side_effects": 0,
            "encrypted_off_host_copy_qualified": False,
            "target_host_repeat_required": True,
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        _run(
            [*compose, "--profile", "restore", "down", "--volumes", "--remove-orphans"],
            cwd=repo_root,
            env=env,
            check=False,
        )
    report_path = evidence / "qualification-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence.chmod(0o700)
    return report


def main() -> int:
    output = Path("local-data/restore-qualification/latest")
    report = run(output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
