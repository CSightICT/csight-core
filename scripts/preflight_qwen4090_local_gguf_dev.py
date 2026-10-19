"""Fail-closed preflight for one unpublished local GGUF canary/Dev runtime.

This path intentionally cannot create or consume a release identity.  It binds
an unpublished candidate by bytes, quantization evidence, matrix digest, and
the local llama.cpp runtime while keeping ``artifact_revision`` null.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import socket
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.platform.model_activation import RuntimeLLMIdentityV1_1
from app.platform.qwen4090_gguf import (
    CandidateReleaseStatusV2,
    GGUFQuantizationVariant,
    LocalUnpublishedGGUFDevIdentity,
    Qwen4090CandidateMatrixV2,
    Qwen4090GGUFCandidate,
    assess_gguf_candidate,
)
from scripts.preflight_qwen4090_gguf_host import (
    LLAMA_CPP_CONTAINER_PORT,
    GGUFHostPreflightError,
    LlamaCppBuildManifest,
    LlamaCppLaunchContract,
    LlamaCppRuntimeInputs,
    build_launch_contract,
    validate_build_manifest,
    validate_gguf_file,
    validate_live_host,
    validate_sbom,
)
from scripts.preflight_qwen4090_host import HostPreflightError, parse_private_env
from scripts.verify_qwen4090_gguf_candidates import DEFAULT_MATRIX, load_gguf_matrix

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_EXPECTED_ASSESSMENT_REASONS = (
    "ARTIFACT_REVISION_UNPINNED",
    "ORG_OWNED_ARTIFACT_MIRROR_REQUIRED",
)
_PROJECT_NAME = "csight-qwen38-local-dev"
_SERVICE_NAME = "qwen38-llama-cpp"
_NETWORK_NAME = "csight-qwen38-local-dev-inbound"
_MAX_JSON_BYTES = 128 * 1024 * 1024
_MAX_RUNTIME_ENV_BYTES = 64 * 1024
_MAX_COMPOSE_BYTES = 2 * 1024 * 1024
_MAX_INSPECT_BYTES = 4 * 1024 * 1024
_MAX_HTTP_BYTES = 1024 * 1024
_MINIMUM_VRAM_HEADROOM_MIB = 2048
_ALLOWED_CANDIDATES = {
    "qwen38-27b-csight-q4-k-m-llama-cpp": GGUFQuantizationVariant.MIXED_Q4_Q6,
    "qwen38-27b-csight-q5-k-s-llama-cpp": GGUFQuantizationVariant.IMATRIX_Q5_K_S,
}
_LOCAL_DEV_LABELS = {
    "org.csight.automatic-fallback": "false",
    "org.csight.core-routing": "false",
    "org.csight.execution-scope": "CANARY_DEV_ONLY",
    "org.csight.primary-allowed": "false",
    "org.csight.publication-state": "LOCAL_UNPUBLISHED",
    "org.csight.release-eligible": "false",
}


class LocalGGUFDevPreflightError(RuntimeError):
    """The unpublished local candidate is unsafe or not exactly pinned."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class QuantizationCommandEvidence(_StrictModel):
    order: int = Field(ge=1)
    operation: str = Field(min_length=1, max_length=128)
    recipe_name: str = Field(min_length=1, max_length=255)
    recipe_digest: str = Field(pattern=_DIGEST_PATTERN)
    output_name: str = Field(min_length=1, max_length=255)
    output_digest: str = Field(pattern=_DIGEST_PATTERN)
    output_bytes: int = Field(gt=0)
    execution: Literal["EXECUTED", "REUSED_VERIFIED"]


class FinalQuantizationEvidence(_StrictModel):
    schema_version: Literal["llama_cpp_quantization_run_evidence/1.1.0"]
    status: Literal["PASS"]
    execution_mode: Literal["DOCKER_OFFLINE"]
    phase: Literal["FINAL_CANDIDATES"]
    plan_digest: str = Field(pattern=_DIGEST_PATTERN)
    llama_cpp_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    tool_image_id: str = Field(pattern=_DIGEST_PATTERN)
    quantize_binary_path: Literal["/app/llama-quantize"]
    quantize_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    docker_limits: dict[str, object]
    commands: tuple[QuantizationCommandEvidence, ...] = Field(min_length=1)
    all_host_inputs_reverified_after_execution: Literal[True]
    final_candidates_from_bf16: Literal[True]
    q8_helper_used_as_final_source: Literal[False]
    sealed_test_data_used: Literal[False]
    shell_interpolation_used: Literal[False]


@dataclass(frozen=True)
class LocalDevRuntimeInputs:
    runtime_env: Path
    gguf_root: Path
    build_manifest: Path
    sbom: Path
    quantization_evidence: Path
    values: dict[str, str]


def _regular_bytes(path: Path, *, maximum_bytes: int = _MAX_JSON_BYTES) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise LocalGGUFDevPreflightError("required input must be a regular non-symlink file")
    before = path.stat()
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise LocalGGUFDevPreflightError("required input has an invalid size")
    content = path.read_bytes()
    after = path.stat()
    if (
        before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise LocalGGUFDevPreflightError("required input changed while it was read")
    return content


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _json_object(path: Path, *, maximum_bytes: int) -> tuple[bytes, dict[str, Any]]:
    content = _regular_bytes(path, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LocalGGUFDevPreflightError("evidence input is not valid JSON") from error
    if not isinstance(value, dict):
        raise LocalGGUFDevPreflightError("evidence JSON root must be an object")
    return content, value


def _absolute_path(values: dict[str, str], name: str, *, directory: bool) -> Path:
    raw = values.get(name, "")
    path = Path(raw)
    if not raw or not path.is_absolute() or path.is_symlink():
        raise LocalGGUFDevPreflightError(f"{name} must be an absolute non-symlink path")
    if directory:
        if not path.is_dir():
            raise LocalGGUFDevPreflightError(f"{name} must identify an existing directory")
    elif not path.is_file():
        raise LocalGGUFDevPreflightError(f"{name} must identify an existing regular file")
    return path.resolve(strict=True)


def load_local_dev_runtime_inputs(path: Path) -> LocalDevRuntimeInputs:
    if path.is_symlink() or not path.is_file():
        raise LocalGGUFDevPreflightError("runtime env must be a regular non-symlink file")
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise LocalGGUFDevPreflightError("runtime env must be owned by the caller with mode 600")
    if metadata.st_size <= 0 or metadata.st_size > _MAX_RUNTIME_ENV_BYTES:
        raise LocalGGUFDevPreflightError("runtime env has an invalid size")
    try:
        values, private = parse_private_env(path)
    except (HostPreflightError, UnicodeDecodeError) as error:
        raise LocalGGUFDevPreflightError("runtime env failed strict parsing") from error
    if not private:
        raise LocalGGUFDevPreflightError("runtime env is not private")
    forbidden = {
        "LLM_MODEL_REVISION",
        "LLM_GGUF_RUNTIME_IDENTITY",
        "LLM_GGUF_RUNTIME_IDENTITIES",
        "MODEL_RELEASE_ENFORCEMENT",
        "MODEL_ROUTE_ENFORCEMENT",
    }
    present = tuple(sorted(forbidden & set(values)))
    if present:
        raise LocalGGUFDevPreflightError(
            "release or routing fields are forbidden in DEV_LOCAL env: " + ", ".join(present)
        )
    canonical_env = path.resolve(strict=True)
    declared = values.get("LLM_RUNTIME_ENV_FILE")
    if declared is not None and Path(declared).resolve(strict=False) != canonical_env:
        raise LocalGGUFDevPreflightError(
            "LLM_RUNTIME_ENV_FILE must identify the positional runtime env when present"
        )
    return LocalDevRuntimeInputs(
        runtime_env=canonical_env,
        gguf_root=_absolute_path(values, "LLAMA_CPP_GGUF_ROOT", directory=True),
        build_manifest=_absolute_path(values, "LLAMA_CPP_BUILD_MANIFEST", directory=False),
        sbom=_absolute_path(values, "LLAMA_CPP_SBOM", directory=False),
        quantization_evidence=_absolute_path(
            values,
            "QWEN4090_QUANTIZATION_EVIDENCE",
            directory=False,
        ),
        values=values,
    )


def select_local_dev_candidate(
    matrix: Qwen4090CandidateMatrixV2,
    candidate_id: str,
) -> Qwen4090GGUFCandidate:
    expected_variant = _ALLOWED_CANDIDATES.get(candidate_id)
    if expected_variant is None:
        raise LocalGGUFDevPreflightError("candidate is not allowlisted for DEV_LOCAL")
    matches = tuple(item for item in matrix.candidates if item.candidate_id == candidate_id)
    if len(matches) != 1:
        raise LocalGGUFDevPreflightError("candidate is not present exactly once in matrix v2")
    candidate = matches[0]
    if candidate.artifact.quantization_variant is not expected_variant:
        raise LocalGGUFDevPreflightError(
            "candidate quantization variant is not the audited variant"
        )
    assessment = assess_gguf_candidate(candidate, matrix=matrix)
    if (
        assessment.status is not CandidateReleaseStatusV2.PENDING_QUALIFICATION
        or assessment.reason_codes != _EXPECTED_ASSESSMENT_REASONS
    ):
        raise LocalGGUFDevPreflightError(
            "DEV_LOCAL requires only the unpublished-revision and organization-mirror blockers"
        )
    return candidate


def build_local_dev_identity(
    *,
    matrix: Qwen4090CandidateMatrixV2,
    candidate: Qwen4090GGUFCandidate,
    inputs: LocalDevRuntimeInputs,
) -> LocalUnpublishedGGUFDevIdentity:
    expected_matrix_digest = inputs.values.get("QWEN4090_CANDIDATE_MATRIX_DIGEST", "")
    expected_evidence_digest = inputs.values.get("QWEN4090_QUANTIZATION_EVIDENCE_DIGEST", "")
    if expected_matrix_digest != matrix.matrix_digest:
        raise LocalGGUFDevPreflightError("candidate matrix digest is not explicitly pinned")
    evidence_content = _regular_bytes(inputs.quantization_evidence)
    if expected_evidence_digest != _digest(evidence_content):
        raise LocalGGUFDevPreflightError("quantization evidence digest is not explicitly pinned")
    try:
        return LocalUnpublishedGGUFDevIdentity.from_candidate(
            candidate,
            candidate_matrix_digest=matrix.matrix_digest,
            quantization_run_evidence_digest=expected_evidence_digest,
        )
    except ValueError as error:
        raise LocalGGUFDevPreflightError(str(error)) from error


def _load_build_manifest(path: Path) -> LlamaCppBuildManifest:
    try:
        return LlamaCppBuildManifest.model_validate_json(
            _regular_bytes(path, maximum_bytes=1024 * 1024)
        )
    except ValidationError as error:
        raise LocalGGUFDevPreflightError(
            "llama.cpp build manifest failed its strict schema"
        ) from error


def validate_quantization_evidence(
    path: Path,
    *,
    identity: LocalUnpublishedGGUFDevIdentity,
    build_manifest: LlamaCppBuildManifest,
) -> str:
    content = _regular_bytes(path)
    if _digest(content) != identity.quantization_run_evidence_digest:
        raise LocalGGUFDevPreflightError("quantization evidence digest drifted")
    try:
        evidence = FinalQuantizationEvidence.model_validate_json(content)
    except ValidationError as error:
        raise LocalGGUFDevPreflightError(
            "final quantization evidence failed its strict schema"
        ) from error
    limits = evidence.docker_limits
    expected_limits = {
        "network": "NONE",
        "root_filesystem": "READ_ONLY",
        "gpu_devices": "NONE",
        "pull": "NEVER",
    }
    if any(limits.get(name) != value for name, value in expected_limits.items()):
        raise LocalGGUFDevPreflightError("quantization did not use the admitted offline limits")
    if (
        evidence.llama_cpp_revision != identity.llama_cpp_revision
        or evidence.tool_image_id != build_manifest.tool_image_digest
        or evidence.quantize_binary_digest != identity.quantizer_binary_digest
    ):
        raise LocalGGUFDevPreflightError("quantization tool identity differs from the candidate")
    matching = tuple(
        command for command in evidence.commands if command.output_name == identity.gguf_filename
    )
    if len(matching) != 1:
        raise LocalGGUFDevPreflightError(
            "final quantization evidence does not identify the candidate exactly once"
        )
    command = matching[0]
    if (
        command.output_digest != identity.artifact_content_digest
        or command.output_bytes != identity.artifact_weight_bytes
        or command.recipe_digest != identity.quantization_recipe_digest
    ):
        raise LocalGGUFDevPreflightError(
            "candidate output differs from final quantization evidence"
        )
    return _digest(content)


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _service(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("name") != _PROJECT_NAME:
        raise LocalGGUFDevPreflightError("rendered Compose has an unexpected project name")
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != {_SERVICE_NAME}:
        raise LocalGGUFDevPreflightError("rendered Compose must contain only the local Dev service")
    service = services[_SERVICE_NAME]
    if not isinstance(service, dict):
        raise LocalGGUFDevPreflightError("rendered local Dev service is invalid")
    return service


def validate_local_dev_compose_config(
    path: Path,
    *,
    contract: LlamaCppLaunchContract,
) -> str:
    content, document = _json_object(path, maximum_bytes=_MAX_COMPOSE_BYTES)
    service = _service(document)
    mismatches: list[str] = []
    expected_scalars = {
        "image": contract.image_ref,
        "pull_policy": "never",
        "read_only": True,
        "restart": "no",
        "pids_limit": 1024,
        "user": f"{contract.gguf_root.stat().st_uid}:{contract.gguf_root.stat().st_gid}",
    }
    for name, expected in expected_scalars.items():
        if service.get(name) != expected:
            mismatches.append(name)
    if service.get("command") != list(contract.command):
        mismatches.append("command")
    if _string_mapping(service.get("environment")) != {
        "HF_HUB_OFFLINE": "1",
        "LLAMA_API_KEY": contract.api_key,
        "TRANSFORMERS_OFFLINE": "1",
    }:
        mismatches.append("environment")
    labels = _string_mapping(service.get("labels"))
    if labels != _LOCAL_DEV_LABELS:
        mismatches.append("labels")
    if service.get("cap_drop") != ["ALL"]:
        mismatches.append("cap_drop")
    if service.get("security_opt") != ["no-new-privileges:true"]:
        mismatches.append("security_opt")
    if service.get("networks") not in ({"local-dev": None}, {"local-dev": {}}):
        mismatches.append("service_network")
    networks = document.get("networks")
    network = networks.get("local-dev") if isinstance(networks, dict) else None
    if not isinstance(network, dict) or (
        network.get("name") != _NETWORK_NAME
        or network.get("driver") != "bridge"
        or network.get("internal") not in (None, False)
        or _string_mapping(network.get("driver_opts"))
        != {"com.docker.network.bridge.enable_ip_masquerade": "false"}
    ):
        mismatches.append("inbound_only_network")
    logging = service.get("logging")
    if (
        not isinstance(logging, dict)
        or logging.get("driver") != "json-file"
        or (_string_mapping(logging.get("options")) != {"max-file": "3", "max-size": "10m"})
    ):
        mismatches.append("bounded_logging")
    deploy = service.get("deploy")
    resources = deploy.get("resources") if isinstance(deploy, dict) else None
    reservations = resources.get("reservations") if isinstance(resources, dict) else None
    devices = reservations.get("devices") if isinstance(reservations, dict) else None
    if not isinstance(devices, list) or len(devices) != 1 or not isinstance(devices[0], dict):
        mismatches.append("gpu_reservation")
    else:
        device = devices[0]
        if (
            device.get("driver") != "nvidia"
            or device.get("count") != 1
            or device.get("capabilities") != ["gpu"]
        ):
            mismatches.append("gpu_reservation")
    volumes = service.get("volumes")
    binds = (
        [item for item in volumes if isinstance(item, dict) and item.get("type") == "bind"]
        if isinstance(volumes, list)
        else []
    )
    if len(binds) != 1:
        mismatches.append("model_mount")
    else:
        mount = binds[0]
        source = mount.get("source")
        source_path = Path(source).resolve(strict=False) if isinstance(source, str) else None
        if (
            source_path != contract.gguf_root
            or mount.get("target") != "/models"
            or mount.get("read_only") is not True
        ):
            mismatches.append("model_mount")
    ports = service.get("ports")
    if not isinstance(ports, list) or len(ports) != 1 or not isinstance(ports[0], dict):
        mismatches.append("port_binding")
    else:
        port = ports[0]
        if (
            port.get("host_ip") != contract.bind_address
            or str(port.get("published")) != str(contract.published_port)
            or str(port.get("target")) != str(LLAMA_CPP_CONTAINER_PORT)
            or port.get("protocol") != "tcp"
        ):
            mismatches.append("port_binding")
    if mismatches:
        raise LocalGGUFDevPreflightError(
            "rendered DEV_LOCAL Compose differs from the pinned contract: "
            + ", ".join(sorted(set(mismatches)))
        )
    return _digest(content)


def _container_environment(value: object) -> dict[str, str]:
    if not isinstance(value, list):
        return {}
    result: dict[str, str] = {}
    for item in value:
        if isinstance(item, str) and "=" in item:
            name, content = item.split("=", 1)
            result[name] = content
    return result


def validate_local_dev_container_inspect(
    path: Path,
    *,
    contract: LlamaCppLaunchContract,
) -> str:
    content = _regular_bytes(path, maximum_bytes=_MAX_INSPECT_BYTES)
    try:
        values = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LocalGGUFDevPreflightError("container inspect is not valid JSON") from error
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise LocalGGUFDevPreflightError("container inspect must contain exactly one object")
    document = values[0]
    config = document.get("Config")
    host = document.get("HostConfig")
    state = document.get("State")
    network_settings = document.get("NetworkSettings")
    if not all(isinstance(value, dict) for value in (config, host, state, network_settings)):
        raise LocalGGUFDevPreflightError("container inspect is missing required sections")
    assert isinstance(config, dict)
    assert isinstance(host, dict)
    assert isinstance(state, dict)
    assert isinstance(network_settings, dict)
    mismatches: list[str] = []
    if document.get("Image") != contract.image_id or config.get("Image") != contract.image_ref:
        mismatches.append("image")
    expected_user = f"{contract.gguf_root.stat().st_uid}:{contract.gguf_root.stat().st_gid}"
    if config.get("User") != expected_user:
        mismatches.append("user")
    if config.get("Cmd") != list(contract.command):
        mismatches.append("command")
    environment = _container_environment(config.get("Env"))
    expected_environment = {
        "HF_HUB_OFFLINE": "1",
        "LLAMA_API_KEY": contract.api_key,
        "TRANSFORMERS_OFFLINE": "1",
    }
    if any(environment.get(name) != value for name, value in expected_environment.items()):
        mismatches.append("environment")
    labels = _string_mapping(config.get("Labels"))
    if any(labels.get(name) != value for name, value in _LOCAL_DEV_LABELS.items()) or (
        labels.get("com.docker.compose.project") != _PROJECT_NAME
        or labels.get("com.docker.compose.service") != _SERVICE_NAME
    ):
        mismatches.append("labels")
    if (
        host.get("ReadonlyRootfs") is not True
        or host.get("PidsLimit") != 1024
        or host.get("NetworkMode") != _NETWORK_NAME
    ):
        mismatches.append("host_isolation")
    if host.get("CapDrop") != ["ALL"] or host.get("SecurityOpt") != ["no-new-privileges:true"]:
        mismatches.append("host_privileges")
    device_requests = host.get("DeviceRequests")
    if (
        not isinstance(device_requests, list)
        or len(device_requests) != 1
        or not isinstance(device_requests[0], dict)
    ):
        mismatches.append("gpu_reservation")
    else:
        device = device_requests[0]
        if (
            device.get("Driver") != "nvidia"
            or device.get("Count") != 1
            or device.get("Capabilities") != [["gpu"]]
        ):
            mismatches.append("gpu_reservation")
    log_config = host.get("LogConfig")
    if (
        not isinstance(log_config, dict)
        or log_config.get("Type") != "json-file"
        or (_string_mapping(log_config.get("Config")) != {"max-file": "3", "max-size": "10m"})
    ):
        mismatches.append("bounded_logging")
    restart = host.get("RestartPolicy")
    if not isinstance(restart, dict) or restart.get("Name") not in {"", "no"}:
        mismatches.append("restart_policy")
    bindings = host.get("PortBindings")
    binding = (
        bindings.get(f"{LLAMA_CPP_CONTAINER_PORT}/tcp") if isinstance(bindings, dict) else None
    )
    if (
        not isinstance(binding, list)
        or len(binding) != 1
        or not isinstance(binding[0], dict)
        or binding[0].get("HostIp") != contract.bind_address
        or binding[0].get("HostPort") != str(contract.published_port)
    ):
        mismatches.append("port_binding")
    mounts = document.get("Mounts")
    bind_mounts = (
        [item for item in mounts if isinstance(item, dict) and item.get("Type") == "bind"]
        if isinstance(mounts, list)
        else []
    )
    if len(bind_mounts) != 1:
        mismatches.append("model_mount")
    else:
        mount = bind_mounts[0]
        source = mount.get("Source")
        source_path = Path(source).resolve(strict=False) if isinstance(source, str) else None
        if (
            source_path != contract.gguf_root
            or mount.get("Destination") != "/models"
            or mount.get("RW") is not False
        ):
            mismatches.append("model_mount")
    networks = network_settings.get("Networks")
    if not isinstance(networks, dict) or set(networks) != {_NETWORK_NAME}:
        mismatches.append("inbound_only_network")
    health = state.get("Health")
    if (
        state.get("Running") is not True
        or not isinstance(health, dict)
        or health.get("Status") != "healthy"
    ):
        mismatches.append("healthy_running_state")
    if mismatches:
        raise LocalGGUFDevPreflightError(
            "running DEV_LOCAL container differs from the pinned contract: "
            + ", ".join(sorted(set(mismatches)))
        )
    return _digest(content)


def container_instance_digest(path: Path) -> str:
    """Return a non-reversible identity for the exact inspected container instance."""

    content = _regular_bytes(path, maximum_bytes=_MAX_INSPECT_BYTES)
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LocalGGUFDevPreflightError("container inspect is not valid JSON") from error
    if not isinstance(document, list) or len(document) != 1 or not isinstance(document[0], dict):
        raise LocalGGUFDevPreflightError("container inspect must contain exactly one record")
    container_id = document[0].get("Id")
    if not isinstance(container_id, str) or re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise LocalGGUFDevPreflightError("container inspect lacks an exact container identity")
    return _digest(("csight-local-dev-container:" + container_id).encode("ascii"))


def validate_authentication_and_canary(contract: LlamaCppLaunchContract) -> None:
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "const": "ok"}},
        "required": ["status"],
        "additionalProperties": False,
    }
    request = {
        "model": contract.model_alias,
        "messages": [
            {"role": "system", "content": "Return only JSON allowed by the supplied schema."},
            {"role": "user", "content": "Synthetic authenticated canary. Return status ok."},
        ],
        "temperature": 0,
        "max_tokens": 32,
        "reasoning_effort": "none",
        "chat_template_kwargs": {"enable_thinking": False, "preserve_thinking": False},
        "json_schema": schema,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "csight_dev_local_canary", "strict": True, "schema": schema},
        },
    }
    request_body = json.dumps(request, separators=(",", ":")).encode("utf-8")
    unauthenticated = http.client.HTTPConnection(
        contract.bind_address,
        contract.published_port,
        timeout=10,
    )
    try:
        unauthenticated.request(
            "POST",
            "/v1/chat/completions",
            body=request_body,
            headers={"Content-Type": "application/json"},
        )
        response = unauthenticated.getresponse()
        response.read(_MAX_HTTP_BYTES + 1)
    except (OSError, TimeoutError, http.client.HTTPException) as error:
        raise LocalGGUFDevPreflightError("unauthenticated inference probe failed") from error
    finally:
        unauthenticated.close()
    if response.status not in {401, 403}:
        raise LocalGGUFDevPreflightError("llama.cpp accepted an unauthenticated inference request")
    authenticated = http.client.HTTPConnection(
        contract.bind_address,
        contract.published_port,
        timeout=60,
    )
    try:
        authenticated.request(
            "POST",
            "/v1/chat/completions",
            body=request_body,
            headers={
                "Authorization": f"Bearer {contract.api_key}",
                "Content-Type": "application/json",
            },
        )
        response = authenticated.getresponse()
        content = response.read(_MAX_HTTP_BYTES + 1)
    except (OSError, TimeoutError, http.client.HTTPException) as error:
        raise LocalGGUFDevPreflightError("authenticated structured canary failed") from error
    finally:
        authenticated.close()
    if response.status != 200 or len(content) > _MAX_HTTP_BYTES:
        raise LocalGGUFDevPreflightError(
            "authenticated structured canary did not return a bounded 200 response"
        )
    try:
        document = json.loads(content)
        choices = document["choices"]
        model = document["model"]
        message = choices[0]["message"]
        result = json.loads(message["content"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise LocalGGUFDevPreflightError(
            "authenticated structured canary returned an invalid envelope"
        ) from error
    if model != contract.model_alias or len(choices) != 1 or result != {"status": "ok"}:
        raise LocalGGUFDevPreflightError(
            "authenticated structured canary returned an unexpected model or payload"
        )


def validate_candidate_absent_and_port_free(contract: LlamaCppLaunchContract) -> None:
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--all",
                "--quiet",
                "--filter",
                f"label=com.docker.compose.project={_PROJECT_NAME}",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise LocalGGUFDevPreflightError("unable to verify prior DEV_LOCAL containers") from error
    if result.stdout.strip():
        raise LocalGGUFDevPreflightError("a prior DEV_LOCAL container still exists")
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((contract.bind_address, contract.published_port))
    except OSError as error:
        raise LocalGGUFDevPreflightError("DEV_LOCAL published port is unavailable") from error
    finally:
        probe.close()


def _strict_inputs(inputs: LocalDevRuntimeInputs) -> LlamaCppRuntimeInputs:
    return LlamaCppRuntimeInputs(
        runtime_env=inputs.runtime_env,
        runtime_identity=inputs.quantization_evidence,
        gguf_root=inputs.gguf_root,
        build_manifest=inputs.build_manifest,
        sbom=inputs.sbom,
        values=inputs.values,
    )


def _contract(
    inputs: LocalDevRuntimeInputs,
    identity: LocalUnpublishedGGUFDevIdentity,
) -> LlamaCppLaunchContract:
    return build_launch_contract(
        _strict_inputs(inputs),
        identity=cast(RuntimeLLMIdentityV1_1, identity),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--runtime-env", type=Path, required=True)
    parser.add_argument("--compose-config", type=Path, required=True)
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--post-start-container-inspect", type=Path)
    arguments = parser.parse_args()
    report: dict[str, object]
    try:
        if arguments.config_only and arguments.post_start_container_inspect is not None:
            raise LocalGGUFDevPreflightError(
                "config-only and post-start validation are mutually exclusive"
            )
        inputs = load_local_dev_runtime_inputs(arguments.runtime_env)
        matrix = load_gguf_matrix(arguments.matrix)
        candidate = select_local_dev_candidate(matrix, arguments.candidate_id)
        identity = build_local_dev_identity(matrix=matrix, candidate=candidate, inputs=inputs)
        contract = _contract(inputs, identity)
        compose_digest = validate_local_dev_compose_config(
            arguments.compose_config,
            contract=contract,
        )
        build_manifest = _load_build_manifest(inputs.build_manifest)
        validate_quantization_evidence(
            inputs.quantization_evidence,
            identity=identity,
            build_manifest=build_manifest,
        )
        common = {
            "candidate_id": identity.candidate_id,
            "candidate_matrix_digest": identity.candidate_matrix_digest,
            "local_dev_identity_digest": identity.identity_digest,
            "artifact_revision": None,
            "artifact_content_digest": identity.artifact_content_digest,
            "artifact_weight_bytes": identity.artifact_weight_bytes,
            "quantization_run_evidence_digest": identity.quantization_run_evidence_digest,
            "runtime_image_digest": identity.runtime_image_digest,
            "runtime_binary_digest": identity.runtime_binary_digest,
            "runtime_build_manifest_digest": identity.runtime_build_manifest_digest,
            "sbom_digest": identity.sbom_digest,
            "llama_cpp_revision": identity.llama_cpp_revision,
            "served_model_name": identity.served_model_name,
            "compose_config_digest": compose_digest,
            "release_eligible": False,
            "primary_allowed": False,
            "core_routing_allowed": False,
            "sealed_test_allowed": False,
        }
        if arguments.post_start_container_inspect is not None:
            artifact_digest, artifact_bytes = validate_gguf_file(
                inputs.gguf_root,
                identity=cast(RuntimeLLMIdentityV1_1, identity),
            )
            validate_build_manifest(
                inputs.build_manifest,
                identity=cast(RuntimeLLMIdentityV1_1, identity),
            )
            validate_sbom(
                inputs.sbom,
                identity=cast(RuntimeLLMIdentityV1_1, identity),
            )
            inspect_digest = validate_local_dev_container_inspect(
                arguments.post_start_container_inspect,
                contract=contract,
            )
            instance_digest = container_instance_digest(arguments.post_start_container_inspect)
            validate_authentication_and_canary(contract)
            report = {
                "schema_version": "qwen4090_local_gguf_dev_post_start/1.0.0",
                "status": "DEV_LOCAL_RUNNING",
                **common,
                "artifact_content_digest": artifact_digest,
                "artifact_weight_bytes": artifact_bytes,
                "container_inspect_digest": inspect_digest,
                "container_instance_digest": instance_digest,
                "authenticated_canary": True,
            }
        elif arguments.config_only:
            report = {
                "schema_version": "qwen4090_local_gguf_dev_config/1.0.0",
                "status": "DEV_LOCAL_CONFIG_VALID",
                **common,
            }
        else:
            strict_identity = cast(RuntimeLLMIdentityV1_1, identity)
            artifact_digest, artifact_bytes = validate_gguf_file(
                inputs.gguf_root,
                identity=strict_identity,
            )
            validate_build_manifest(inputs.build_manifest, identity=strict_identity)
            validate_sbom(inputs.sbom, identity=strict_identity)
            validate_candidate_absent_and_port_free(contract)
            host = validate_live_host(contract=contract)
            required_vram_mib = (artifact_bytes + (1024 * 1024 - 1)) // (
                1024 * 1024
            ) + _MINIMUM_VRAM_HEADROOM_MIB
            free_vram = host.get("gpu_free_vram_mib")
            if not isinstance(free_vram, int) or free_vram < required_vram_mib:
                raise LocalGGUFDevPreflightError(
                    "RTX 4090 free VRAM does not preserve the required 2 GiB headroom"
                )
            report = {
                "schema_version": "qwen4090_local_gguf_dev_preflight/1.0.0",
                "status": "DEV_LOCAL_READY",
                **common,
                "artifact_content_digest": artifact_digest,
                "artifact_weight_bytes": artifact_bytes,
                "host": host,
            }
    except (
        GGUFHostPreflightError,
        LocalGGUFDevPreflightError,
        OSError,
        ValidationError,
        ValueError,
    ) as error:
        report = {
            "schema_version": "qwen4090_local_gguf_dev_preflight/1.0.0",
            "status": "FAIL",
            "release_eligible": False,
            "primary_allowed": False,
            "core_routing_allowed": False,
            "sealed_test_allowed": False,
            "error": str(error),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return (
        0
        if report["status"]
        in {
            "DEV_LOCAL_CONFIG_VALID",
            "DEV_LOCAL_READY",
            "DEV_LOCAL_RUNNING",
        }
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
