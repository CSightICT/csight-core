#!/usr/bin/env python3
"""Inside-container helpers for the isolated restore qualification drill."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import tarfile
from pathlib import Path

from minio import Minio
from minio.versioningconfig import ENABLED, VersioningConfig

BUCKET = "restore-qualification"
MINIO_BACKUP = Path("/evidence/minio-version-backup/minio-data.tar.gz")
MINIO_INVENTORY = Path("/evidence/minio-version-inventory/inventory.json")
SOURCE_MINIO_DATA = Path("/source-minio-data")
RESTORED_MINIO_DATA = Path("/restored-minio-data")
RESTORED_POSTGRES_DATA = Path("/restored-postgres-data")
POSTGRES_BASE_BACKUP = Path("/evidence/postgresql-base-backup")


def _client(endpoint: str) -> Minio:
    return Minio(
        endpoint,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )


def _read_version(client: Minio, object_name: str, version_id: str) -> bytes:
    response = client.get_object(BUCKET, object_name, version_id=version_id)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _inventory(client: Minio) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for item in client.list_objects(BUCKET, recursive=True, include_version=True):
        object_name = str(item.object_name)
        version_id = str(item.version_id)
        is_delete_marker = bool(item.is_delete_marker)
        content_sha256 = None
        if not is_delete_marker:
            content_sha256 = hashlib.sha256(
                _read_version(client, object_name, version_id)
            ).hexdigest()
        records.append(
            {
                "object_name": object_name,
                "version_id": version_id,
                "is_delete_marker": is_delete_marker,
                "size": int(item.size or 0),
                "content_sha256": content_sha256,
            }
        )
    records.sort(
        key=lambda record: (
            str(record["object_name"]),
            str(record["version_id"]),
            bool(record["is_delete_marker"]),
        )
    )
    canonical = json.dumps(records, separators=(",", ":"), sort_keys=True).encode()
    return {
        "schema_version": "csight.minio_version_inventory/1.0.0",
        "bucket_versioning": "ENABLED",
        "version_count": len(records),
        "delete_marker_count": sum(bool(record["is_delete_marker"]) for record in records),
        "content_version_count": sum(not bool(record["is_delete_marker"]) for record in records),
        "inventory_sha256": hashlib.sha256(canonical).hexdigest(),
        "records": records,
    }


def seed_minio(endpoint: str) -> dict[str, object]:
    client = _client(endpoint)
    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)
    client.set_bucket_versioning(BUCKET, VersioningConfig(ENABLED))
    objects = {
        "synthetic/evidence-a.bin": (b"restore-a-v1", b"restore-a-v2"),
        "synthetic/evidence-b.bin": (b"restore-b-v1", b"restore-b-v2"),
    }
    for object_name, versions in objects.items():
        for payload in versions:
            client.put_object(
                BUCKET,
                object_name,
                io.BytesIO(payload),
                len(payload),
                content_type="application/octet-stream",
            )
    client.remove_object(BUCKET, "synthetic/evidence-a.bin")
    inventory = _inventory(client)
    MINIO_INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    MINIO_INVENTORY.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return _aggregate_inventory(inventory)


def _aggregate_inventory(inventory: dict[str, object]) -> dict[str, object]:
    return {
        key: inventory[key]
        for key in (
            "schema_version",
            "bucket_versioning",
            "version_count",
            "delete_marker_count",
            "content_version_count",
            "inventory_sha256",
        )
    }


def verify_minio(endpoint: str) -> dict[str, object]:
    expected = json.loads(MINIO_INVENTORY.read_text(encoding="utf-8"))
    actual = _inventory(_client(endpoint))
    if actual != expected:
        raise RuntimeError("restored MinIO version inventory does not match source")
    return {"status": "PASS", **_aggregate_inventory(actual)}


def snapshot_minio() -> dict[str, object]:
    if not SOURCE_MINIO_DATA.is_dir() or not any(SOURCE_MINIO_DATA.iterdir()):
        raise RuntimeError("source MinIO data volume is empty")
    MINIO_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if MINIO_BACKUP.exists():
        raise RuntimeError("MinIO version backup already exists")
    with tarfile.open(MINIO_BACKUP, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(SOURCE_MINIO_DATA.rglob("*")):
            archive.add(path, arcname=path.relative_to(SOURCE_MINIO_DATA), recursive=False)
    return {
        "status": "PASS",
        "backup_bytes": MINIO_BACKUP.stat().st_size,
        "backup_sha256": _sha256(MINIO_BACKUP),
    }


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = Path(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise RuntimeError("MinIO backup contains an unsafe member")
    return members


def restore_minio() -> dict[str, object]:
    if not MINIO_BACKUP.is_file():
        raise RuntimeError("MinIO version backup is missing")
    _require_empty_directory(RESTORED_MINIO_DATA, "restored MinIO volume")
    with tarfile.open(MINIO_BACKUP, mode="r:gz") as archive:
        archive.extractall(RESTORED_MINIO_DATA, members=_safe_members(archive))
    return {"status": "PASS", "restored_entry_count": _entry_count(RESTORED_MINIO_DATA)}


def restore_postgres() -> dict[str, object]:
    if not (POSTGRES_BASE_BACKUP / "PG_VERSION").is_file():
        raise RuntimeError("PostgreSQL base backup is incomplete")
    _require_empty_directory(RESTORED_POSTGRES_DATA, "restored PostgreSQL volume")
    shutil.copytree(
        POSTGRES_BASE_BACKUP,
        RESTORED_POSTGRES_DATA,
        dirs_exist_ok=True,
        symlinks=True,
    )
    (RESTORED_POSTGRES_DATA / "recovery.signal").touch(mode=0o600)
    auto_conf = RESTORED_POSTGRES_DATA / "postgresql.auto.conf"
    with auto_conf.open("a", encoding="utf-8") as stream:
        stream.write("restore_command = 'cp /wal-archive/%f %p'\n")
        stream.write("recovery_target_timeline = 'latest'\n")
    for path in [RESTORED_POSTGRES_DATA, *RESTORED_POSTGRES_DATA.rglob("*")]:
        os.chown(path, 999, 999, follow_symlinks=False)
    return {"status": "PASS", "restored_entry_count": _entry_count(RESTORED_POSTGRES_DATA)}


def _require_empty_directory(path: Path, label: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise RuntimeError(f"{label} must be empty")


def _entry_count(path: Path) -> int:
    return sum(1 for _ in path.rglob("*"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "seed-minio",
            "verify-minio",
            "snapshot-minio",
            "restore-minio",
            "restore-postgres",
        ),
    )
    parser.add_argument("--endpoint", default="source-minio:9000")
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    operations = {
        "seed-minio": lambda: seed_minio(arguments.endpoint),
        "verify-minio": lambda: verify_minio(arguments.endpoint),
        "snapshot-minio": snapshot_minio,
        "restore-minio": restore_minio,
        "restore-postgres": restore_postgres,
    }
    result = operations[arguments.command]()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
