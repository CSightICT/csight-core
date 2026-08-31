"""Build and verify PII-free CSight recovery manifests.

The manifest intentionally retains only fixed artifact roles, aggregate sizes,
file counts, and SHA-256 tree digests. Source paths and filenames are used to
calculate a tree digest but are never serialized.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

SCHEMA_VERSION: Final = "csight.restore_manifest/2.0.0"
TREE_HASH_VERSION: Final = b"csight.restore_tree_sha256/1\0"
MAX_MANIFEST_BYTES: Final = 1024 * 1024
ARTIFACT_ROLES: Final = (
    "postgresql_base_backup",
    "postgresql_wal_archive",
    "minio_version_inventory",
    "minio_version_backup",
    "runtime_version_manifest",
)
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+=,-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RestoreManifestError(ValueError):
    """Raised when recovery evidence is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class ArtifactDigest:
    """PII-free aggregate for one restore artifact tree."""

    role: str
    tree_sha256: str
    file_count: int
    total_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "tree_sha256": self.tree_sha256,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
        }


def _safe_identifier(value: str, field: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise RestoreManifestError(f"{field} must be a non-empty, non-secret identifier")
    return value


def _file_digest(path: Path, role: str) -> tuple[bytes, int]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RestoreManifestError(f"{role} contains an unreadable or unsafe artifact") from exc

    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RestoreManifestError(f"{role} contains a non-regular artifact")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise RestoreManifestError(f"{role} changed while it was being read")
        return digest.digest(), before.st_size
    finally:
        os.close(descriptor)


def _walk_regular_files(root: Path, role: str) -> list[tuple[str, Path]]:
    try:
        root_stat = root.lstat()
    except FileNotFoundError as exc:
        raise RestoreManifestError(f"{role} is missing") from exc
    except OSError as exc:
        raise RestoreManifestError(f"{role} cannot be inspected") from exc

    if stat.S_ISLNK(root_stat.st_mode):
        raise RestoreManifestError(f"{role} must not be a symlink")
    if stat.S_ISREG(root_stat.st_mode):
        return [("artifact", root)]
    if not stat.S_ISDIR(root_stat.st_mode):
        raise RestoreManifestError(f"{role} must be a regular file or directory")

    files: list[tuple[str, Path]] = []

    def visit(directory: Path, relative_directory: Path) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            raise RestoreManifestError(f"{role} cannot be inspected") from exc
        for entry in entries:
            entry_path = Path(entry.path)
            relative_path = relative_directory / entry.name
            try:
                if entry.is_symlink():
                    raise RestoreManifestError(f"{role} contains a symlink")
                if entry.is_dir(follow_symlinks=False):
                    visit(entry_path, relative_path)
                elif entry.is_file(follow_symlinks=False):
                    files.append((relative_path.as_posix(), entry_path))
                else:
                    raise RestoreManifestError(f"{role} contains a non-regular artifact")
            except OSError as exc:
                raise RestoreManifestError(f"{role} cannot be inspected") from exc

    visit(root, Path())
    if not files:
        raise RestoreManifestError(f"{role} is empty")
    return files


def digest_artifact(role: str, path: Path) -> ArtifactDigest:
    """Calculate a stable aggregate without disclosing path or filename metadata."""

    if role not in ARTIFACT_ROLES:
        raise RestoreManifestError("unknown restore artifact role")
    tree_digest = hashlib.sha256(TREE_HASH_VERSION)
    file_count = 0
    total_bytes = 0
    for relative_path, file_path in _walk_regular_files(path, role):
        content_digest, size = _file_digest(file_path, role)
        relative_path_bytes = relative_path.encode("utf-8")
        tree_digest.update(len(relative_path_bytes).to_bytes(8, "big"))
        tree_digest.update(relative_path_bytes)
        tree_digest.update(size.to_bytes(16, "big"))
        tree_digest.update(content_digest)
        file_count += 1
        total_bytes += size
    if total_bytes == 0:
        raise RestoreManifestError(f"{role} is empty")
    return ArtifactDigest(
        role=role,
        tree_sha256=tree_digest.hexdigest(),
        file_count=file_count,
        total_bytes=total_bytes,
    )


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _binding_sha256(manifest_without_binding: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(manifest_without_binding)).hexdigest()


def build_manifest(
    *,
    backup_id: str,
    postgresql_version: str,
    minio_version: str,
    encryption_key_id: str,
    artifacts: Mapping[str, Path],
    created_at: datetime | None = None,
) -> dict[str, object]:
    """Build a strict manifest for all required recovery artifacts."""

    if set(artifacts) != set(ARTIFACT_ROLES):
        raise RestoreManifestError("all required artifact roles must be supplied exactly once")
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise RestoreManifestError("created_at must be timezone-aware UTC")

    aggregates = [digest_artifact(role, artifacts[role]).to_dict() for role in ARTIFACT_ROLES]
    body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "backup_id": _safe_identifier(backup_id, "backup_id"),
        "created_at": timestamp.isoformat().replace("+00:00", "Z"),
        "encryption_key_id": _safe_identifier(encryption_key_id, "encryption_key_id"),
        "postgresql": {"version": _safe_identifier(postgresql_version, "postgresql_version")},
        "minio": {"version": _safe_identifier(minio_version, "minio_version")},
        "artifacts": aggregates,
    }
    body["binding_sha256"] = _binding_sha256(body)
    return body


def _expect_exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise RestoreManifestError(f"{label} has missing or unknown fields")


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RestoreManifestError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise RestoreManifestError(f"{label} must be a string")
    return value


def _require_integer(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise RestoreManifestError(f"{label} must be a positive integer")
    return value


def validate_manifest_structure(manifest: Mapping[str, object]) -> None:
    """Reject malformed, extended, or internally inconsistent manifests."""

    top_level_keys = {
        "schema_version",
        "backup_id",
        "created_at",
        "encryption_key_id",
        "postgresql",
        "minio",
        "artifacts",
        "binding_sha256",
    }
    _expect_exact_keys(manifest, top_level_keys, "restore manifest")
    if _require_string(manifest["schema_version"], "schema_version") != SCHEMA_VERSION:
        raise RestoreManifestError("unsupported restore manifest schema")
    _safe_identifier(_require_string(manifest["backup_id"], "backup_id"), "backup_id")
    _safe_identifier(
        _require_string(manifest["encryption_key_id"], "encryption_key_id"),
        "encryption_key_id",
    )

    created_at = _require_string(manifest["created_at"], "created_at")
    try:
        parsed_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RestoreManifestError("created_at must be an ISO-8601 timestamp") from exc
    if parsed_time.tzinfo is None or parsed_time.utcoffset() != UTC.utcoffset(parsed_time):
        raise RestoreManifestError("created_at must be UTC")

    for component in ("postgresql", "minio"):
        component_data = _require_mapping(manifest[component], component)
        _expect_exact_keys(component_data, {"version"}, component)
        _safe_identifier(
            _require_string(component_data["version"], f"{component}.version"),
            f"{component}.version",
        )

    raw_artifacts = manifest["artifacts"]
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(ARTIFACT_ROLES):
        raise RestoreManifestError("artifacts must contain every required role exactly once")
    observed_roles: list[str] = []
    for index, raw_artifact in enumerate(raw_artifacts):
        artifact = _require_mapping(raw_artifact, f"artifacts[{index}]")
        _expect_exact_keys(
            artifact,
            {"role", "tree_sha256", "file_count", "total_bytes"},
            f"artifacts[{index}]",
        )
        role = _require_string(artifact["role"], f"artifacts[{index}].role")
        observed_roles.append(role)
        digest = _require_string(artifact["tree_sha256"], f"artifacts[{index}].tree_sha256")
        if not _SHA256.fullmatch(digest):
            raise RestoreManifestError("artifact tree_sha256 must be lowercase SHA-256")
        _require_integer(artifact["file_count"], f"artifacts[{index}].file_count")
        _require_integer(artifact["total_bytes"], f"artifacts[{index}].total_bytes")
    if tuple(observed_roles) != ARTIFACT_ROLES:
        raise RestoreManifestError("artifact roles or order do not match the schema")

    binding = _require_string(manifest["binding_sha256"], "binding_sha256")
    if not _SHA256.fullmatch(binding):
        raise RestoreManifestError("binding_sha256 must be lowercase SHA-256")
    body = dict(manifest)
    del body["binding_sha256"]
    if not hmac.compare_digest(binding, _binding_sha256(body)):
        raise RestoreManifestError("restore manifest binding digest mismatch")


def verify_manifest(
    manifest: Mapping[str, object], *, artifacts: Mapping[str, Path]
) -> dict[str, object]:
    """Verify schema, binding, and every current artifact tree fail closed."""

    validate_manifest_structure(manifest)
    if set(artifacts) != set(ARTIFACT_ROLES):
        raise RestoreManifestError("all required artifact roles must be supplied exactly once")
    raw_artifacts = cast(list[object], manifest["artifacts"])
    for expected_raw in raw_artifacts:
        expected = _require_mapping(expected_raw, "artifact")
        role = _require_string(expected["role"], "artifact.role")
        actual = digest_artifact(role, artifacts[role]).to_dict()
        if actual != expected:
            raise RestoreManifestError(f"{role} digest, count, or byte size mismatch")
    return {
        "backup_id": manifest["backup_id"],
        "binding_sha256": manifest["binding_sha256"],
        "status": "PASS",
        "verified_artifact_count": len(ARTIFACT_ROLES),
    }


def load_manifest(path: Path) -> Mapping[str, object]:
    """Load a bounded regular manifest file without following a final symlink."""

    digest = _walk_regular_files(path, "restore_manifest")
    if len(digest) != 1 or digest[0][0] != "artifact":
        raise RestoreManifestError("restore_manifest must be one regular file")
    try:
        size = path.stat(follow_symlinks=False).st_size
        if size > MAX_MANIFEST_BYTES:
            raise RestoreManifestError("restore_manifest exceeds the size limit")
        raw = path.read_bytes()
        parsed = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RestoreManifestError("restore_manifest is not valid UTF-8 JSON") from exc
    return _require_mapping(parsed, "restore_manifest")


def write_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    """Create a new owner-readable manifest without overwriting an existing path."""

    if path.exists() or path.is_symlink():
        raise RestoreManifestError("output manifest already exists")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise RestoreManifestError("output directory must be an existing regular directory")
    payload = json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise RestoreManifestError("output manifest could not be created") from exc


def _add_artifact_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--postgresql-base-backup", required=True, type=Path)
    parser.add_argument("--postgresql-wal-archive", required=True, type=Path)
    parser.add_argument("--minio-version-inventory", required=True, type=Path)
    parser.add_argument("--minio-version-backup", required=True, type=Path)
    parser.add_argument("--runtime-version-manifest", required=True, type=Path)


def _artifact_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "postgresql_base_backup": cast(Path, args.postgresql_base_backup),
        "postgresql_wal_archive": cast(Path, args.postgresql_wal_archive),
        "minio_version_inventory": cast(Path, args.minio_version_inventory),
        "minio_version_backup": cast(Path, args.minio_version_backup),
        "runtime_version_manifest": cast(Path, args.runtime_version_manifest),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="build a new restore manifest")
    build_parser.add_argument("--backup-id", required=True)
    build_parser.add_argument("--postgresql-version", required=True)
    build_parser.add_argument("--minio-version", required=True)
    build_parser.add_argument("--encryption-key-id", required=True)
    build_parser.add_argument("--output", required=True, type=Path)
    _add_artifact_arguments(build_parser)

    verify_parser = subparsers.add_parser("verify", help="verify a restore manifest")
    verify_parser.add_argument("--manifest", required=True, type=Path)
    _add_artifact_arguments(verify_parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        artifacts = _artifact_paths(args)
        if args.command == "build":
            manifest = build_manifest(
                backup_id=cast(str, args.backup_id),
                postgresql_version=cast(str, args.postgresql_version),
                minio_version=cast(str, args.minio_version),
                encryption_key_id=cast(str, args.encryption_key_id),
                artifacts=artifacts,
            )
            write_manifest(cast(Path, args.output), manifest)
            result: Mapping[str, object] = {
                "backup_id": manifest["backup_id"],
                "binding_sha256": manifest["binding_sha256"],
                "status": "BUILT",
            }
        else:
            result = verify_manifest(load_manifest(cast(Path, args.manifest)), artifacts=artifacts)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except RestoreManifestError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
