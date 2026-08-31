"""Unit tests for the offline recovery-manifest boundary."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from scripts.restore_manifest import (
    ARTIFACT_ROLES,
    RestoreManifestError,
    build_manifest,
    load_manifest,
    main,
    verify_manifest,
    write_manifest,
)

pytestmark = pytest.mark.unit


def _artifact_fixture(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for index, role in enumerate(ARTIFACT_ROLES, start=1):
        artifact = root / role
        artifact.mkdir()
        (artifact / "part-0001.bin").write_bytes(f"fixture-{index}".encode())
        paths[role] = artifact
    return paths


def _build(artifacts: dict[str, Path]) -> dict[str, object]:
    return build_manifest(
        backup_id="backup-20260829T010203Z",
        postgresql_version="16.4",
        minio_version="RELEASE.2026-08-01T00-00-00Z",
        encryption_key_id="kms://csight/restore-key-v2",
        artifacts=artifacts,
        created_at=datetime(2026, 8, 29, 1, 2, 3, tzinfo=UTC),
    )


def test_build_and_verify_manifest_without_disclosing_paths_or_filenames(tmp_path: Path) -> None:
    artifacts = _artifact_fixture(tmp_path)
    manifest = _build(artifacts)

    result = verify_manifest(manifest, artifacts=artifacts)
    serialized = json.dumps(manifest, sort_keys=True)

    assert result["status"] == "PASS"
    assert result["verified_artifact_count"] == 5
    assert manifest["backup_id"] == "backup-20260829T010203Z"
    assert manifest["postgresql"] == {"version": "16.4"}
    assert manifest["minio"] == {"version": "RELEASE.2026-08-01T00-00-00Z"}
    assert manifest["encryption_key_id"] == "kms://csight/restore-key-v2"
    assert str(tmp_path) not in serialized
    assert "part-0001.bin" not in serialized
    assert [item["role"] for item in cast(list[dict[str, object]], manifest["artifacts"])] == list(
        ARTIFACT_ROLES
    )
    for item in cast(list[dict[str, object]], manifest["artifacts"]):
        assert item["file_count"] == 1
        assert isinstance(item["total_bytes"], int)
        assert item["total_bytes"] > 0


def test_verifier_rejects_artifact_digest_mismatch(tmp_path: Path) -> None:
    artifacts = _artifact_fixture(tmp_path)
    manifest = _build(artifacts)
    (artifacts["postgresql_wal_archive"] / "part-0001.bin").write_bytes(b"tampered")

    with pytest.raises(RestoreManifestError, match="digest, count, or byte size mismatch"):
        verify_manifest(manifest, artifacts=artifacts)


def test_verifier_binds_actual_minio_version_backup_bytes(tmp_path: Path) -> None:
    artifacts = _artifact_fixture(tmp_path)
    manifest = _build(artifacts)
    (artifacts["minio_version_backup"] / "part-0001.bin").write_bytes(b"tampered-backup")

    with pytest.raises(RestoreManifestError, match="minio_version_backup digest"):
        verify_manifest(manifest, artifacts=artifacts)


def test_verifier_rejects_manifest_binding_mismatch(tmp_path: Path) -> None:
    artifacts = _artifact_fixture(tmp_path)
    manifest = _build(artifacts)
    manifest["backup_id"] = "backup-tampered"

    with pytest.raises(RestoreManifestError, match="binding digest mismatch"):
        verify_manifest(manifest, artifacts=artifacts)


@pytest.mark.parametrize("unsafe_kind", ["missing", "empty_file", "empty_directory"])
def test_builder_rejects_missing_or_empty_artifacts(tmp_path: Path, unsafe_kind: str) -> None:
    artifacts = _artifact_fixture(tmp_path)
    target = artifacts["minio_version_inventory"]
    for child in target.iterdir():
        child.unlink()
    if unsafe_kind == "missing":
        target.rmdir()
    elif unsafe_kind == "empty_file":
        (target / "empty.json").touch()

    with pytest.raises(RestoreManifestError, match=r"missing|empty"):
        _build(artifacts)


def test_builder_rejects_root_and_nested_symlinks(tmp_path: Path) -> None:
    artifacts = _artifact_fixture(tmp_path)
    external = tmp_path / "external.bin"
    external.write_bytes(b"external")
    nested_link = artifacts["postgresql_base_backup"] / "link.bin"
    nested_link.symlink_to(external)

    with pytest.raises(RestoreManifestError, match="symlink"):
        _build(artifacts)

    nested_link.unlink()
    real_wal = artifacts["postgresql_wal_archive"]
    root_link = tmp_path / "wal-link"
    root_link.symlink_to(real_wal, target_is_directory=True)
    artifacts["postgresql_wal_archive"] = root_link
    with pytest.raises(RestoreManifestError, match="symlink"):
        _build(artifacts)


def test_builder_accepts_zero_byte_file_inside_non_empty_physical_backup(tmp_path: Path) -> None:
    artifacts = _artifact_fixture(tmp_path)
    (artifacts["postgresql_base_backup"] / "postgresql.auto.conf").touch()

    manifest = _build(artifacts)
    result = verify_manifest(manifest, artifacts=artifacts)

    assert result["status"] == "PASS"


def test_builder_rejects_unsafe_metadata_and_missing_role(tmp_path: Path) -> None:
    artifacts = _artifact_fixture(tmp_path)
    del artifacts["runtime_version_manifest"]
    with pytest.raises(RestoreManifestError, match="all required"):
        _build(artifacts)

    complete = _artifact_fixture(tmp_path / "second")
    with pytest.raises(RestoreManifestError, match="non-secret identifier"):
        build_manifest(
            backup_id="contains whitespace",
            postgresql_version="16.4",
            minio_version="RELEASE.2026",
            encryption_key_id="kms://csight/key",
            artifacts=complete,
        )


def test_load_manifest_rejects_symlink(tmp_path: Path) -> None:
    artifacts = _artifact_fixture(tmp_path / "artifacts")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, _build(artifacts))
    manifest_link = tmp_path / "manifest-link.json"
    manifest_link.symlink_to(manifest_path)

    with pytest.raises(RestoreManifestError, match="symlink"):
        load_manifest(manifest_link)


def test_cli_build_then_verify_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifacts = _artifact_fixture(tmp_path / "artifacts")
    manifest_path = tmp_path / "restore-manifest.json"
    artifact_arguments = [
        "--postgresql-base-backup",
        os.fspath(artifacts["postgresql_base_backup"]),
        "--postgresql-wal-archive",
        os.fspath(artifacts["postgresql_wal_archive"]),
        "--minio-version-inventory",
        os.fspath(artifacts["minio_version_inventory"]),
        "--minio-version-backup",
        os.fspath(artifacts["minio_version_backup"]),
        "--runtime-version-manifest",
        os.fspath(artifacts["runtime_version_manifest"]),
    ]

    assert (
        main(
            [
                "build",
                "--backup-id",
                "backup-cli-roundtrip",
                "--postgresql-version",
                "16.4",
                "--minio-version",
                "RELEASE.2026-08-01T00-00-00Z",
                "--encryption-key-id",
                "kms://csight/restore-key-v2",
                "--output",
                os.fspath(manifest_path),
                *artifact_arguments,
            ]
        )
        == 0
    )
    build_output = json.loads(capsys.readouterr().out)
    assert build_output["status"] == "BUILT"

    assert main(["verify", "--manifest", os.fspath(manifest_path), *artifact_arguments]) == 0
    verify_output = json.loads(capsys.readouterr().out)
    assert verify_output["status"] == "PASS"


def test_cli_returns_failure_without_partial_output(tmp_path: Path) -> None:
    artifacts = _artifact_fixture(tmp_path / "artifacts")
    output = tmp_path / "restore-manifest.json"
    (artifacts["runtime_version_manifest"] / "part-0001.bin").write_bytes(b"")

    return_code = main(
        [
            "build",
            "--backup-id",
            "backup-cli-failure",
            "--postgresql-version",
            "16.4",
            "--minio-version",
            "RELEASE.2026",
            "--encryption-key-id",
            "kms://csight/key",
            "--output",
            os.fspath(output),
            "--postgresql-base-backup",
            os.fspath(artifacts["postgresql_base_backup"]),
            "--postgresql-wal-archive",
            os.fspath(artifacts["postgresql_wal_archive"]),
            "--minio-version-inventory",
            os.fspath(artifacts["minio_version_inventory"]),
            "--minio-version-backup",
            os.fspath(artifacts["minio_version_backup"]),
            "--runtime-version-manifest",
            os.fspath(artifacts["runtime_version_manifest"]),
        ]
    )

    assert return_code == 2
    assert not output.exists()
