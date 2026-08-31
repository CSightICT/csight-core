"""Collect privacy-safe RTX 4090 host evidence and compare it with the frozen matrix."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
import platform
import re
import socket
import stat
import struct
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.platform.qwen4090_host import (
    HostPreflightStatus,
    Qwen4090HostEvidence,
    RTX4090GpuHostEvidence,
    assess_qwen4090_host,
)
from scripts.verify_qwen4090_candidates import DEFAULT_MATRIX, load_matrix

MAX_ENV_BYTES = 64 * 1024
MAX_LOCK_BYTES = 32 * 1024 * 1024
MAX_SBOM_BYTES = 128 * 1024 * 1024
MAX_COMMAND_OUTPUT = 2 * 1024 * 1024
TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


class HostPreflightError(RuntimeError):
    """Live host evidence could not be collected safely or completely."""


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest_text(value: str) -> str:
    return _digest_bytes(value.encode("utf-8"))


def _regular_bytes(path: Path, *, maximum_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise HostPreflightError("required evidence input is missing or is not a regular file")
    size = path.stat().st_size
    if size <= 0 or size > maximum_bytes:
        raise HostPreflightError("required evidence input has an invalid size")
    return path.read_bytes()


def _file_digest(path: Path, *, maximum_bytes: int) -> str:
    return _digest_bytes(_regular_bytes(path, maximum_bytes=maximum_bytes))


def parse_private_env(path: Path) -> tuple[dict[str, str], bool]:
    content = _regular_bytes(path, maximum_bytes=MAX_ENV_BYTES).decode("utf-8")
    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise HostPreflightError("runtime env contains a malformed line")
        name, value = line.split("=", 1)
        if not _ENV_NAME.fullmatch(name) or name in values:
            raise HostPreflightError("runtime env contains an invalid or duplicate key")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    metadata = path.stat()
    private = metadata.st_uid == os.getuid() and stat.S_IMODE(metadata.st_mode) & 0o077 == 0
    return values, private


def api_key_valid(value: str) -> bool:
    lowered = value.lower()
    placeholders = ("replace", "redacted", "change-me", "changeme", "example", "password")
    return (
        len(value) >= 32
        and not any(token in lowered for token in placeholders)
        and not any(character.isspace() for character in value)
        and len(set(value)) >= 10
    )


def _run(arguments: list[str], *, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise HostPreflightError(f"required host probe failed: {arguments[0]}") from error
    output = result.stdout.strip()
    if len(output.encode("utf-8")) > MAX_COMMAND_OUTPUT:
        raise HostPreflightError("host probe output exceeded the safety limit")
    return output


def _gpu_evidence() -> tuple[tuple[RTX4090GpuHostEvidence, ...], int]:
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total,memory.free,compute_cap,uuid",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus: list[RTX4090GpuHostEvidence] = []
    for line in output.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 6:
            raise HostPreflightError("nvidia-smi returned an unexpected GPU record")
        name, driver, total, free, capability, uuid = fields
        try:
            gpus.append(
                RTX4090GpuHostEvidence(
                    name=name,
                    driver_version=driver,
                    compute_capability=capability,
                    total_vram_mib=int(total),
                    free_vram_mib=int(free),
                    uuid_sha256=_digest_text(uuid),
                )
            )
        except (ValueError, ValidationError) as error:
            raise HostPreflightError("nvidia-smi returned invalid GPU evidence") from error
    processes = _run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid",
            "--format=csv,noheader,nounits",
        ]
    )
    process_ids = {line.strip() for line in processes.splitlines() if line.strip()}
    return tuple(gpus), len(process_ids)


def _docker_evidence(expected_image: str, expected_digest: str) -> tuple[str, str, str, bool, str]:
    raw_info = _run(
        [
            "docker",
            "info",
            "--format",
            "{{json .OSType}}|{{json .Architecture}}|{{json .ServerVersion}}|{{json .Runtimes}}",
        ]
    )
    sections = raw_info.split("|", 3)
    if len(sections) != 4:
        raise HostPreflightError("docker info returned an unexpected record")
    try:
        server_os = json.loads(sections[0])
        server_arch = json.loads(sections[1])
        server_version = json.loads(sections[2])
        runtimes = json.loads(sections[3])
    except json.JSONDecodeError as error:
        raise HostPreflightError("docker info returned invalid JSON") from error
    if not all(isinstance(item, str) for item in (server_os, server_arch, server_version)):
        raise HostPreflightError("docker server identity is invalid")
    if not isinstance(runtimes, dict):
        raise HostPreflightError("docker runtime inventory is invalid")

    reference = f"{expected_image}@{expected_digest}"
    raw_digests = _run(
        ["docker", "image", "inspect", reference, "--format", "{{json .RepoDigests}}"]
    )
    try:
        repo_digests = json.loads(raw_digests)
    except json.JSONDecodeError as error:
        raise HostPreflightError("docker image inspect returned invalid JSON") from error
    if not isinstance(repo_digests, list) or not all(
        isinstance(item, str) for item in repo_digests
    ):
        raise HostPreflightError("docker image has no valid repository digests")
    matching = {item.rsplit("@", 1)[-1] for item in repo_digests if "@" in item}
    observed_digest = expected_digest if expected_digest in matching else "sha256:" + "0" * 64
    return server_os, server_arch, server_version, "nvidia" in runtimes, observed_digest


def _local_ipv4_addresses() -> set[str]:
    try:
        raw = _run(["ip", "-j", "-4", "address", "show"])
    except HostPreflightError:
        return _local_ipv4_addresses_from_ioctl()
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HostPreflightError("ip address inventory returned invalid JSON") from error
    if not isinstance(records, list):
        raise HostPreflightError("ip address inventory is invalid")
    addresses: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        for address in record.get("addr_info", []):
            if isinstance(address, dict) and isinstance(address.get("local"), str):
                addresses.add(address["local"])
    return addresses


def _local_ipv4_addresses_from_ioctl() -> set[str]:
    """Read Linux interface addresses without requiring iproute2 in the runner image."""

    addresses: set[str] = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        for _index, interface_name in socket.if_nameindex():
            encoded_name = interface_name.encode("utf-8")
            if not encoded_name or len(encoded_name) > 15:
                continue
            request = struct.pack("256s", encoded_name)
            try:
                response = fcntl.ioctl(probe.fileno(), 0x8915, request)
            except OSError:
                continue
            addresses.add(socket.inet_ntoa(response[20:24]))
    if not addresses:
        raise HostPreflightError("local IPv4 inventory is empty")
    return addresses


def _safe_snapshot_file(path: Path, *, cache_root: Path) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(cache_root)
    except ValueError as error:
        raise HostPreflightError(
            "snapshot file resolves outside the configured model cache"
        ) from error
    if not resolved.is_file():
        raise HostPreflightError("snapshot contains a non-file entry")
    return resolved


def _stream_digest(path: Path) -> tuple[str, int]:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise HostPreflightError("snapshot file changed while it was being hashed")
    return "sha256:" + digest.hexdigest(), before.st_size


def artifact_evidence(
    snapshot_dir: Path,
    *,
    cache_dir: Path,
    artifact: str,
    revision: str,
) -> tuple[str, int, int]:
    if cache_dir.is_symlink() or not cache_dir.is_dir():
        raise HostPreflightError("model cache is missing or unsafe")
    cache_root = cache_dir.resolve(strict=True)
    if snapshot_dir.is_symlink() or not snapshot_dir.is_dir():
        raise HostPreflightError("model snapshot is missing or unsafe")
    snapshot_root = snapshot_dir.resolve(strict=True)
    try:
        relative_snapshot = snapshot_root.relative_to(cache_root)
    except ValueError as error:
        raise HostPreflightError("model snapshot is outside the configured model cache") from error
    expected_repo_dir = "models--" + artifact.replace("/", "--")
    parts = relative_snapshot.parts
    if expected_repo_dir not in parts or "snapshots" not in parts or snapshot_root.name != revision:
        raise HostPreflightError("model snapshot path does not match artifact revision")

    manifest_digest = hashlib.sha256()
    file_count = 0
    weight_bytes = 0
    for root, directories, files in os.walk(snapshot_root, followlinks=False):
        root_path = Path(root)
        directories.sort()
        if any((root_path / name).is_symlink() for name in directories):
            raise HostPreflightError("snapshot contains a directory symlink")
        for filename in sorted(files):
            entry = root_path / filename
            target = _safe_snapshot_file(entry, cache_root=cache_root)
            relative_name = entry.relative_to(snapshot_root).as_posix()
            content_digest, size = _stream_digest(target)
            manifest_digest.update(relative_name.encode("utf-8"))
            manifest_digest.update(b"\0")
            manifest_digest.update(str(size).encode("ascii"))
            manifest_digest.update(b"\0")
            manifest_digest.update(content_digest.encode("ascii"))
            manifest_digest.update(b"\n")
            file_count += 1
            if entry.suffix == ".safetensors":
                weight_bytes += size
    if file_count == 0 or weight_bytes == 0:
        raise HostPreflightError("model snapshot has no safetensors weights")
    return "sha256:" + manifest_digest.hexdigest(), file_count, weight_bytes


def sbom_digest(path: Path, *, runtime_image_digest: str) -> str:
    content = _regular_bytes(path, maximum_bytes=MAX_SBOM_BYTES)
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise HostPreflightError("SBOM is not valid JSON") from error
    if not isinstance(document, dict) or not (
        document.get("bomFormat") == "CycloneDX" or isinstance(document.get("spdxVersion"), str)
    ):
        raise HostPreflightError("SBOM is not CycloneDX or SPDX JSON")
    if runtime_image_digest.encode("ascii") not in content:
        raise HostPreflightError("SBOM does not identify the exact runtime image digest")
    return _digest_bytes(content)


def canonical_dependency_lock_digest(content: str) -> str:
    lines = tuple(line.strip() for line in content.splitlines() if line.strip())
    if not lines or any(len(line) > 2048 or line.startswith("#") for line in lines):
        raise HostPreflightError("dependency lock is empty or not canonical pip freeze output")
    canonical = "\n".join(sorted(set(lines))) + "\n"
    return _digest_text(canonical)


def _runtime_dependency_lock_digest(runtime_image: str, runtime_image_digest: str) -> str:
    reference = f"{runtime_image}@{runtime_image_digest}"
    output = _run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--entrypoint=python3",
            reference,
            "-m",
            "pip",
            "freeze",
            "--all",
            "--local",
        ],
        timeout=120,
    )
    return canonical_dependency_lock_digest(output)


def dependency_lock_digest(
    path: Path,
    *,
    runtime_image: str,
    runtime_image_digest: str,
) -> str:
    try:
        content = _regular_bytes(path, maximum_bytes=MAX_LOCK_BYTES).decode("utf-8")
    except UnicodeDecodeError as error:
        raise HostPreflightError("dependency lock is not UTF-8") from error
    supplied = canonical_dependency_lock_digest(content)
    observed = _runtime_dependency_lock_digest(runtime_image, runtime_image_digest)
    if supplied != observed:
        raise HostPreflightError("dependency lock does not match the exact runtime image")
    return observed


def _artifact_json(path: Path, *, artifact: str, revision: str, label: str) -> dict[str, Any]:
    content = _regular_bytes(path, maximum_bytes=MAX_LOCK_BYTES)
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise HostPreflightError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict):
        raise HostPreflightError(f"{label} root must be an object")
    if document.get("artifact") != artifact or document.get("artifact_revision") != revision:
        raise HostPreflightError(f"{label} does not identify the exact artifact revision")
    return document


def quantization_recipe_digest(path: Path | None, *, artifact: str, revision: str) -> str | None:
    if path is None:
        return None
    _artifact_json(path, artifact=artifact, revision=revision, label="quantization recipe")
    return _file_digest(path, maximum_bytes=MAX_LOCK_BYTES)


def calibration_dataset_digest(path: Path | None, *, artifact: str, revision: str) -> str | None:
    if path is None:
        return None
    document = _artifact_json(
        path,
        artifact=artifact,
        revision=revision,
        label="calibration manifest",
    )
    digest = document.get("dataset_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise HostPreflightError("calibration manifest has no valid dataset digest")
    return digest


def _env_path(values: dict[str, str], name: str, explicit: Path | None) -> Path | None:
    path = explicit
    if path is None and values.get(name):
        path = Path(values[name])
    if path is not None and not path.is_absolute():
        raise HostPreflightError(f"{name} must be an absolute host path")
    return path


def _private_output_path(
    values: dict[str, str],
    *,
    candidate_id: str,
    explicit: Path | None,
) -> Path:
    if explicit is not None:
        if not explicit.is_absolute():
            raise HostPreflightError("preflight output must be an absolute host path")
        return explicit
    raw_directory = values.get("QWEN4090_PREFLIGHT_OUTPUT_DIR", "")
    if not raw_directory:
        raise HostPreflightError("QWEN4090_PREFLIGHT_OUTPUT_DIR must be configured")
    directory = Path(raw_directory)
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise HostPreflightError("preflight output directory is missing or unsafe")
    metadata = directory.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise HostPreflightError("preflight output directory must be owner-only")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return directory / f"{candidate_id}-{timestamp}-{os.getpid()}.json"


def collect_live_evidence(
    *,
    candidate: Any,
    runtime_env: Path,
    snapshot_dir: Path,
    dependency_lock: Path,
    sbom: Path,
    quantization_recipe: Path | None,
    calibration_manifest: Path | None,
) -> Qwen4090HostEvidence:
    environment, private_env = parse_private_env(runtime_env)
    bind_value = environment.get("LLM_BIND_ADDRESS", "")
    api_key = environment.get("LLM_API_KEY", "")
    model_cache = environment.get("LLM_MODEL_CACHE_DIR", "")
    if not model_cache or not Path(model_cache).is_absolute():
        raise HostPreflightError("LLM_MODEL_CACHE_DIR must be an absolute host path")
    try:
        bind_address = ipaddress.ip_address(bind_value)
    except ValueError as error:
        raise HostPreflightError("LLM_BIND_ADDRESS is not a valid IP address") from error
    if bind_address.version != 4:
        raise HostPreflightError("LLM_BIND_ADDRESS must be IPv4")

    gpus, process_count = _gpu_evidence()
    docker_os, docker_arch, docker_version, nvidia_runtime, image_digest = _docker_evidence(
        candidate.serving.runtime_image,
        candidate.serving.runtime_image_digest,
    )
    artifact_digest, artifact_files, weight_bytes = artifact_evidence(
        snapshot_dir,
        cache_dir=Path(model_cache),
        artifact=candidate.artifact.artifact,
        revision=candidate.artifact.artifact_revision,
    )
    local_addresses = _local_ipv4_addresses()
    return Qwen4090HostEvidence(
        schema_version="qwen4090_host_evidence/1.0.0",
        collected_at=datetime.now(UTC),
        os_name=platform.system(),
        machine=platform.machine(),
        kernel_release=platform.release(),
        gpus=gpus,
        active_compute_process_count=process_count,
        docker_server_os=docker_os,
        docker_server_arch=docker_arch,
        docker_server_version=docker_version,
        nvidia_runtime_available=nvidia_runtime,
        runtime_image_digest=image_digest,
        runtime_env_private=private_env,
        api_key_valid=api_key_valid(api_key),
        hf_hub_offline=environment.get("LLM_HF_HUB_OFFLINE") == "1",
        transformers_offline=environment.get("LLM_TRANSFORMERS_OFFLINE") == "1",
        bind_address_is_tailscale=bind_address in TAILSCALE_CGNAT,
        bind_address_is_local=str(bind_address) in local_addresses,
        bind_address_sha256=_digest_text(str(bind_address)),
        artifact=candidate.artifact.artifact,
        artifact_revision=candidate.artifact.artifact_revision,
        artifact_content_digest=artifact_digest,
        artifact_file_count=artifact_files,
        weight_bytes=weight_bytes,
        dependency_lock_digest=dependency_lock_digest(
            dependency_lock,
            runtime_image=candidate.serving.runtime_image,
            runtime_image_digest=candidate.serving.runtime_image_digest,
        ),
        sbom_digest=sbom_digest(
            sbom,
            runtime_image_digest=candidate.serving.runtime_image_digest,
        ),
        quantization_recipe_digest=quantization_recipe_digest(
            quantization_recipe,
            artifact=candidate.artifact.artifact,
            revision=candidate.artifact.artifact_revision,
        ),
        calibration_dataset_digest=calibration_dataset_digest(
            calibration_manifest,
            artifact=candidate.artifact.artifact,
            revision=candidate.artifact.artifact_revision,
        ),
    )


def _write_once(path: Path, content: str) -> None:
    if path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink():
        raise HostPreflightError("preflight output parent is missing or unsafe")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise HostPreflightError(
            "preflight output already exists; evidence is immutable"
        ) from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.write("\n")


def _matrix_candidate(matrix: Any, candidate_id: str) -> Any:
    candidates = tuple(item for item in matrix.candidates if item.candidate_id == candidate_id)
    if len(candidates) != 1:
        raise HostPreflightError("candidate is not present exactly once in the frozen matrix")
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--runtime-env", type=Path)
    parser.add_argument("--snapshot-dir", type=Path)
    parser.add_argument("--dependency-lock", type=Path)
    parser.add_argument("--sbom", type=Path)
    parser.add_argument("--quantization-recipe", type=Path)
    parser.add_argument("--calibration-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--collect-unpinned", action="store_true")
    parser.add_argument("--allow-shadow-provenance-incomplete", action="store_true")
    arguments = parser.parse_args()

    try:
        matrix = load_matrix(arguments.matrix)
        candidate = _matrix_candidate(matrix, arguments.candidate_id)
        if arguments.probe is not None:
            evidence = Qwen4090HostEvidence.model_validate_json(
                _regular_bytes(arguments.probe, maximum_bytes=2 * 1024 * 1024)
            )
            output_path = arguments.output
        else:
            if arguments.runtime_env is None:
                raise HostPreflightError("missing live evidence input: --runtime-env")
            runtime_values, _private = parse_private_env(arguments.runtime_env)
            snapshot_dir = _env_path(
                runtime_values,
                "QWEN4090_SNAPSHOT_DIR",
                arguments.snapshot_dir,
            )
            dependency_lock = _env_path(
                runtime_values,
                "QWEN4090_DEPENDENCY_LOCK_FILE",
                arguments.dependency_lock,
            )
            sbom = _env_path(runtime_values, "QWEN4090_SBOM_FILE", arguments.sbom)
            quantization_recipe = _env_path(
                runtime_values,
                "QWEN4090_QUANTIZATION_RECIPE_FILE",
                arguments.quantization_recipe,
            )
            calibration_manifest = _env_path(
                runtime_values,
                "QWEN4090_CALIBRATION_MANIFEST_FILE",
                arguments.calibration_manifest,
            )
            required = {
                "QWEN4090_SNAPSHOT_DIR": snapshot_dir,
                "QWEN4090_DEPENDENCY_LOCK_FILE": dependency_lock,
                "QWEN4090_SBOM_FILE": sbom,
            }
            missing = tuple(name for name, value in required.items() if value is None)
            if missing:
                raise HostPreflightError("missing live evidence inputs: " + ", ".join(missing))
            if snapshot_dir is None or dependency_lock is None or sbom is None:
                raise HostPreflightError("required live evidence inputs were not resolved")
            output_path = _private_output_path(
                runtime_values,
                candidate_id=arguments.candidate_id,
                explicit=arguments.output,
            )
            evidence = collect_live_evidence(
                candidate=candidate,
                runtime_env=arguments.runtime_env,
                snapshot_dir=snapshot_dir,
                dependency_lock=dependency_lock,
                sbom=sbom,
                quantization_recipe=quantization_recipe,
                calibration_manifest=calibration_manifest,
            )
        report = assess_qwen4090_host(
            matrix,
            candidate_id=arguments.candidate_id,
            evidence=evidence,
        )
        output = json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        if output_path is not None:
            _write_once(output_path, output)
        print(output)
    except (HostPreflightError, OSError, ValueError, ValidationError) as error:
        print(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        return 2

    if report.status is HostPreflightStatus.PASS:
        return 0
    if (
        arguments.allow_shadow_provenance_incomplete
        and report.status is HostPreflightStatus.SHADOW_READY_PROVENANCE_INCOMPLETE
    ):
        return 0
    if (
        arguments.collect_unpinned
        and report.status is HostPreflightStatus.EVIDENCE_COLLECTED_NOT_PINNED
    ):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
