"""Static and fail-closed contracts for the isolated restore qualification."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.restore_manifest import ARTIFACT_ROLES, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]


def test_restore_manifest_v2_binds_actual_minio_version_backup() -> None:
    assert SCHEMA_VERSION == "csight.restore_manifest/2.0.0"
    assert ARTIFACT_ROLES == (
        "postgresql_base_backup",
        "postgresql_wal_archive",
        "minio_version_inventory",
        "minio_version_backup",
        "runtime_version_manifest",
    )


def test_restore_qualification_is_internal_digest_pinned_and_has_no_host_ports() -> None:
    compose = yaml.safe_load(
        (ROOT / "infra/restore/compose.restore-qualification.yml").read_text(encoding="utf-8")
    )
    assert compose["networks"]["restore-qualification"]["internal"] is True
    for service in compose["services"].values():
        assert "ports" not in service
    for name in (
        "source-postgres",
        "source-minio",
        "restored-postgres",
        "restored-minio",
    ):
        assert "@sha256:" in compose["services"][name]["image"]


def test_restore_services_do_not_start_without_explicit_profile() -> None:
    compose = yaml.safe_load(
        (ROOT / "infra/restore/compose.restore-qualification.yml").read_text(encoding="utf-8")
    )
    assert compose["services"]["restored-postgres"]["profiles"] == ["restore"]
    assert compose["services"]["restored-minio"]["profiles"] == ["restore"]
    assert compose["services"]["utility"]["profiles"] == ["tools"]
