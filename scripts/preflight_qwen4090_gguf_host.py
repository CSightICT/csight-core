"""Fail-closed local preflight for one pinned GGUF and llama.cpp runtime identity."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.platform.model_activation import RuntimeLLMIdentityV1_1
from app.platform.qwen4090_gguf import Qwen4090GGUFCandidate
from scripts.preflight_qwen4090_host import (
    HostPreflightError,
    api_key_valid,
    parse_private_env,
)
from scripts.verify_qwen4090_gguf_candidates import DEFAULT_MATRIX, load_gguf_matrix

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_REVISION_PATTERN = r"^[0-9a-f]{40}$"
TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")
MAX_JSON_BYTES = 128 * 1024 * 1024
MAX_MEMINFO_BYTES = 64 * 1024
MAX_RUNTIME_ENV_BYTES = 64 * 1024
MAX_COMPOSE_CONFIG_BYTES = 2 * 1024 * 1024
MAX_CONTAINER_INSPECT_BYTES = 4 * 1024 * 1024
MAX_MODELS_RESPONSE_BYTES = 1024 * 1024
MINIMUM_HOST_MEM_AVAILABLE_KIB = 50 * 1024 * 1024
LLAMA_CPP_SERVICE = "qwen38-llama-cpp"
LLAMA_CPP_CONTAINER_HOST = "0.0.0.0"
LLAMA_CPP_CONTAINER_PORT = 8080


@dataclass(frozen=True)
class LlamaCppRuntimeInputs:
    """Owner-controlled paths loaded only from the positional runtime env."""

    runtime_env: Path
    runtime_identity: Path
    gguf_root: Path
    build_manifest: Path
    sbom: Path
    values: Mapping[str, str]


@dataclass(frozen=True)
class LlamaCppLaunchContract:
    """Exact effective Compose and container contract for one GGUF runtime."""

    image_ref: str
    image_id: str
    gguf_root: Path
    gguf_filename: str
    gguf_digest: str
    gguf_bytes: int
    model_alias: str
    bind_address: str
    published_port: int
    context_size: int
    parallel: int
    batch_size: int
    ubatch_size: int
    gpu_layers: str
    kv_cache_type_k: str
    kv_cache_type_v: str
    reasoning: Literal["off"]
    flash_attention: Literal["on"]
    api_key: str

    @property
    def command(self) -> tuple[str, ...]:
        return (
            "--model",
            f"/models/{self.gguf_filename}",
            "--alias",
            self.model_alias,
            "--host",
            LLAMA_CPP_CONTAINER_HOST,
            "--port",
            str(LLAMA_CPP_CONTAINER_PORT),
            "--ctx-size",
            str(self.context_size),
            "--parallel",
            str(self.parallel),
            "--batch-size",
            str(self.batch_size),
            "--ubatch-size",
            str(self.ubatch_size),
            "--n-gpu-layers",
            self.gpu_layers,
            "--reasoning",
            self.reasoning,
            "--no-reasoning-preserve",
            "--flash-attn",
            self.flash_attention,
            "--cache-type-k",
            self.kv_cache_type_k,
            "--cache-type-v",
            self.kv_cache_type_v,
        )


class GGUFHostPreflightError(RuntimeError):
    """Pinned GGUF or llama.cpp host evidence is missing or inconsistent."""


class LlamaCppBuildManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal["csight_llama_cpp_build/1.0.0"]
    source_repository: Literal["ggml-org/llama.cpp"]
    source_revision: str = Field(pattern=_REVISION_PATTERN)
    dockerfile_digest: str = Field(pattern=_DIGEST_PATTERN)
    tool_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    quantizer_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    imatrix_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    tokenizer_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    cuda_architectures: tuple[str, ...] = Field(min_length=1)
    cmake_options: dict[str, str | bool] = Field(min_length=1)
    base_image_digests: dict[str, str] = Field(min_length=2)
    sbom_tool_image: str = Field(min_length=3, max_length=512)

    @field_validator("base_image_digests")
    @classmethod
    def require_pinned_base_images(cls, value: dict[str, str]) -> dict[str, str]:
        if any(
            not item.startswith("sha256:")
            or len(item) != 71
            or any(character not in "0123456789abcdef" for character in item[7:])
            for item in value.values()
        ):
            raise ValueError("base images must use exact SHA-256 digests")
        return value


def _regular_bytes(path: Path, *, maximum_bytes: int = MAX_JSON_BYTES) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise GGUFHostPreflightError("required input must be a regular non-symlink file")
    size = path.stat().st_size
    if size <= 0 or size > maximum_bytes:
        raise GGUFHostPreflightError("required input has an invalid size")
    return path.read_bytes()


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _json_object(path: Path) -> tuple[bytes, dict[str, Any]]:
    content = _regular_bytes(path)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GGUFHostPreflightError("evidence input is not valid JSON") from error
    if not isinstance(value, dict):
        raise GGUFHostPreflightError("evidence JSON root must be an object")
    return content, value


def _json_object_bounded(path: Path, *, maximum_bytes: int) -> tuple[bytes, dict[str, Any]]:
    content = _regular_bytes(path, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GGUFHostPreflightError("runtime evidence is not valid JSON") from error
    if not isinstance(value, dict):
        raise GGUFHostPreflightError("runtime evidence JSON root must be an object")
    return content, value


def load_exact_runtime_env(path: Path) -> dict[str, str]:
    """Read an exact owner/mode-600 env without consulting process environment."""

    if path.is_symlink() or not path.is_file():
        raise GGUFHostPreflightError("runtime env must be a regular non-symlink file")
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise GGUFHostPreflightError("runtime env must be owned by the caller with mode 600")
    if metadata.st_size <= 0 or metadata.st_size > MAX_RUNTIME_ENV_BYTES:
        raise GGUFHostPreflightError("runtime env has an invalid size")
    try:
        values, private = parse_private_env(path)
    except (HostPreflightError, UnicodeDecodeError) as error:
        raise GGUFHostPreflightError("runtime env failed strict parsing") from error
    if not private:
        raise GGUFHostPreflightError("runtime env is not private")
    return values


def _absolute_input_path(
    values: Mapping[str, str],
    name: str,
    *,
    directory: bool,
) -> Path:
    raw = values.get(name, "")
    path = Path(raw)
    if not raw or not path.is_absolute() or path.is_symlink():
        raise GGUFHostPreflightError(f"{name} must be an absolute non-symlink path")
    if directory:
        if not path.is_dir():
            raise GGUFHostPreflightError(f"{name} must identify an existing directory")
    elif not path.is_file():
        raise GGUFHostPreflightError(f"{name} must identify an existing regular file")
    return path.resolve(strict=True)


def load_runtime_inputs(runtime_env: Path) -> LlamaCppRuntimeInputs:
    values = load_exact_runtime_env(runtime_env)
    canonical_env = runtime_env.resolve(strict=True)
    declared_env = values.get("LLM_RUNTIME_ENV_FILE")
    if declared_env is not None:
        declared_path = Path(declared_env)
        if not declared_path.is_absolute() or declared_path.resolve(strict=False) != canonical_env:
            raise GGUFHostPreflightError(
                "LLM_RUNTIME_ENV_FILE must identify the positional runtime env when present"
            )
    return LlamaCppRuntimeInputs(
        runtime_env=canonical_env,
        runtime_identity=_absolute_input_path(
            values,
            "LLM_RUNTIME_IDENTITY_FILE",
            directory=False,
        ),
        gguf_root=_absolute_input_path(values, "LLAMA_CPP_GGUF_ROOT", directory=True),
        build_manifest=_absolute_input_path(
            values,
            "LLAMA_CPP_BUILD_MANIFEST",
            directory=False,
        ),
        sbom=_absolute_input_path(values, "LLAMA_CPP_SBOM", directory=False),
        values=values,
    )


def _require_decimal(
    values: Mapping[str, str],
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = values.get(name, "")
    if not raw.isascii() or not raw.isdecimal():
        raise GGUFHostPreflightError(f"{name} must be an explicit decimal integer")
    value = int(raw)
    if value < minimum or value > maximum:
        raise GGUFHostPreflightError(f"{name} is outside the allowed range")
    return value


def build_launch_contract(
    inputs: LlamaCppRuntimeInputs,
    *,
    identity: RuntimeLLMIdentityV1_1,
) -> LlamaCppLaunchContract:
    values = inputs.values
    required = {
        "LLAMA_CPP_IMAGE",
        "LLAMA_CPP_GGUF_FILENAME",
        "LLAMA_CPP_PORT",
        "LLM_BIND_ADDRESS",
        "LLM_API_KEY",
        "LLM_MODEL_ID",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "LLAMA_CPP_CONTEXT_SIZE",
        "LLAMA_CPP_PARALLEL",
        "LLAMA_CPP_BATCH_SIZE",
        "LLAMA_CPP_UBATCH_SIZE",
        "LLAMA_CPP_GPU_LAYERS",
        "LLAMA_CPP_KV_CACHE_TYPE_K",
        "LLAMA_CPP_KV_CACHE_TYPE_V",
        "LLAMA_CPP_REASONING",
        "LLAMA_CPP_FLASH_ATTN",
    }
    missing = tuple(sorted(name for name in required if not values.get(name)))
    if missing:
        raise GGUFHostPreflightError(
            "runtime env is missing explicit launch fields: " + ", ".join(missing)
        )

    try:
        bind = ipaddress.ip_address(values["LLM_BIND_ADDRESS"])
    except ValueError as error:
        raise GGUFHostPreflightError("LLM_BIND_ADDRESS is invalid") from error
    if not isinstance(bind, ipaddress.IPv4Address) or bind not in TAILSCALE_CGNAT:
        raise GGUFHostPreflightError("llama.cpp must bind to a Tailscale IPv4 address")
    if not api_key_valid(values["LLM_API_KEY"]):
        raise GGUFHostPreflightError("LLM_API_KEY is missing or invalid")
    if values["HF_HUB_OFFLINE"] != "1" or values["TRANSFORMERS_OFFLINE"] != "1":
        raise GGUFHostPreflightError("model runtime must be explicitly offline")

    expected = {
        "LLAMA_CPP_IMAGE": identity.runtime_image,
        "LLAMA_CPP_GGUF_FILENAME": identity.gguf_filename,
        "LLM_MODEL_ID": identity.served_model_name,
        "LLAMA_CPP_CONTEXT_SIZE": str(identity.max_context_tokens),
        "LLAMA_CPP_PARALLEL": str(identity.max_num_sequences),
        "LLAMA_CPP_BATCH_SIZE": str(identity.batch_size),
        "LLAMA_CPP_UBATCH_SIZE": str(identity.ubatch_size),
        "LLAMA_CPP_GPU_LAYERS": identity.gpu_layers,
        "LLAMA_CPP_KV_CACHE_TYPE_K": identity.kv_cache_type_k,
        "LLAMA_CPP_KV_CACHE_TYPE_V": identity.kv_cache_type_v,
        "LLAMA_CPP_REASONING": "off",
        "LLAMA_CPP_FLASH_ATTN": "on",
    }
    mismatches = tuple(sorted(name for name, value in expected.items() if values[name] != value))
    if mismatches:
        raise GGUFHostPreflightError(
            "runtime env differs from the pinned runtime identity: " + ", ".join(mismatches)
        )

    published_port = _require_decimal(
        values,
        "LLAMA_CPP_PORT",
        minimum=1,
        maximum=65535,
    )
    context_size = _require_decimal(
        values,
        "LLAMA_CPP_CONTEXT_SIZE",
        minimum=1,
        maximum=1_000_000,
    )
    parallel = _require_decimal(values, "LLAMA_CPP_PARALLEL", minimum=1, maximum=4)
    batch_size = _require_decimal(
        values,
        "LLAMA_CPP_BATCH_SIZE",
        minimum=32,
        maximum=4096,
    )
    ubatch_size = _require_decimal(
        values,
        "LLAMA_CPP_UBATCH_SIZE",
        minimum=32,
        maximum=4096,
    )
    if ubatch_size > batch_size:
        raise GGUFHostPreflightError("llama.cpp ubatch size cannot exceed batch size")

    return LlamaCppLaunchContract(
        image_ref=identity.runtime_image,
        image_id=identity.runtime_image_digest,
        gguf_root=inputs.gguf_root,
        gguf_filename=identity.gguf_filename,
        gguf_digest=identity.artifact_content_digest,
        gguf_bytes=identity.artifact_weight_bytes,
        model_alias=identity.served_model_name,
        bind_address=str(bind),
        published_port=published_port,
        context_size=context_size,
        parallel=parallel,
        batch_size=batch_size,
        ubatch_size=ubatch_size,
        gpu_layers=values["LLAMA_CPP_GPU_LAYERS"],
        kv_cache_type_k=values["LLAMA_CPP_KV_CACHE_TYPE_K"],
        kv_cache_type_v=values["LLAMA_CPP_KV_CACHE_TYPE_V"],
        reasoning="off",
        flash_attention="on",
        api_key=values["LLM_API_KEY"],
    )


def load_runtime_identity(path: Path) -> RuntimeLLMIdentityV1_1:
    content = _regular_bytes(path, maximum_bytes=1024 * 1024)
    try:
        return RuntimeLLMIdentityV1_1.model_validate_json(content)
    except ValidationError as error:
        raise GGUFHostPreflightError("runtime identity failed its strict GGUF schema") from error


def validate_build_manifest(
    path: Path,
    *,
    identity: RuntimeLLMIdentityV1_1,
) -> str:
    content = _regular_bytes(path, maximum_bytes=1024 * 1024)
    try:
        manifest = LlamaCppBuildManifest.model_validate_json(content)
    except ValidationError as error:
        raise GGUFHostPreflightError("llama.cpp build manifest failed its strict schema") from error
    if _digest(content) != identity.runtime_build_manifest_digest:
        raise GGUFHostPreflightError(
            "llama.cpp build-manifest digest does not match runtime identity"
        )
    expected = (
        (manifest.source_revision, identity.llama_cpp_revision),
        (manifest.runtime_image_digest, identity.runtime_image_digest),
        (manifest.runtime_binary_digest, identity.runtime_binary_digest),
        (manifest.quantizer_binary_digest, identity.quantizer_binary_digest),
    )
    if any(observed != pinned for observed, pinned in expected):
        raise GGUFHostPreflightError("llama.cpp build identity does not match runtime identity")
    if "89" not in manifest.cuda_architectures:
        raise GGUFHostPreflightError("llama.cpp build does not target CUDA architecture 89")
    if manifest.cmake_options.get("GGML_CUDA") not in {True, "ON"}:
        raise GGUFHostPreflightError("llama.cpp build did not enable GGML_CUDA")
    return _digest(content)


def validate_sbom(path: Path, *, identity: RuntimeLLMIdentityV1_1) -> str:
    content, document = _json_object(path)
    if not (
        document.get("bomFormat") == "CycloneDX" or isinstance(document.get("spdxVersion"), str)
    ):
        raise GGUFHostPreflightError("SBOM is not CycloneDX or SPDX JSON")
    observed_digest = _digest(content)
    if observed_digest != identity.sbom_digest:
        raise GGUFHostPreflightError("SBOM digest does not match runtime identity")
    return observed_digest


def validate_gguf_file(
    gguf_root: Path,
    *,
    identity: RuntimeLLMIdentityV1_1,
) -> tuple[str, int]:
    if gguf_root.is_symlink() or not gguf_root.is_dir():
        raise GGUFHostPreflightError("GGUF root must be a regular directory")
    root = gguf_root.resolve(strict=True)
    path = root / identity.gguf_filename
    if path.is_symlink() or not path.is_file() or path.resolve(strict=True).parent != root:
        raise GGUFHostPreflightError("exact GGUF file is missing or escapes its configured root")
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
        raise GGUFHostPreflightError("GGUF file changed while it was hashed")
    observed = "sha256:" + digest.hexdigest()
    if (
        observed != identity.artifact_content_digest
        or before.st_size != identity.artifact_weight_bytes
    ):
        raise GGUFHostPreflightError(
            "GGUF file digest or byte size does not match runtime identity"
        )
    return observed, before.st_size


def validate_candidate_identity(
    candidate: Qwen4090GGUFCandidate,
    identity: RuntimeLLMIdentityV1_1,
) -> None:
    artifact = candidate.artifact
    serving = candidate.serving
    expected = {
        "artifact": artifact.artifact,
        "artifact_revision": artifact.artifact_revision,
        "artifact_content_digest": artifact.artifact_content_digest,
        "artifact_weight_bytes": artifact.weight_bytes,
        "upstream_model_artifact": artifact.upstream_model_artifact,
        "upstream_model_revision": artifact.upstream_model_revision,
        "base_artifact": artifact.base_artifact,
        "base_revision": artifact.base_revision,
        "base_artifact_content_digest": artifact.base_artifact_content_digest,
        "gguf_filename": artifact.gguf_filename,
        "quantization_type": artifact.quantization_type.value,
        "quantization_recipe_digest": artifact.quantization_recipe_digest,
        "calibration_dataset_digest": artifact.calibration_dataset_digest,
        "calibration_manifest_digest": artifact.calibration_manifest_digest,
        "importance_matrix_digest": artifact.importance_matrix_digest,
        "tokenizer_digest": artifact.tokenizer_digest,
        "chat_template_digest": artifact.chat_template_digest,
        "quantizer_binary_digest": artifact.quantizer_binary_digest,
        "runtime_image": serving.runtime_image,
        "runtime_image_digest": serving.runtime_image_digest,
        "llama_cpp_revision": serving.llama_cpp_revision,
        "runtime_binary_digest": serving.runtime_binary_digest,
        "runtime_build_manifest_digest": serving.runtime_build_manifest_digest,
        "sbom_digest": serving.sbom_digest,
        "served_model_name": serving.served_model_name,
        "max_context_tokens": serving.max_context_tokens,
        "max_num_sequences": serving.max_num_sequences,
        "gpu_layers": serving.gpu_layers,
        "batch_size": serving.batch_size,
        "ubatch_size": serving.ubatch_size,
        "flash_attention": serving.flash_attention,
        "kv_cache_type_k": serving.kv_cache_type_k,
        "kv_cache_type_v": serving.kv_cache_type_v,
        "api_compatibility": serving.api_compatibility,
        "language_model_only": serving.language_model_only,
        "automatic_cross_model_fallback": serving.automatic_cross_model_fallback,
    }
    unpinned = tuple(key for key, value in expected.items() if value is None)
    if unpinned:
        raise GGUFHostPreflightError(
            "candidate matrix is not pinned for host execution: " + ", ".join(unpinned)
        )
    mismatches = tuple(key for key, value in expected.items() if getattr(identity, key) != value)
    if mismatches:
        raise GGUFHostPreflightError(
            "runtime identity differs from candidate matrix: " + ", ".join(mismatches)
        )


def _compose_service(document: Mapping[str, Any]) -> Mapping[str, Any]:
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != {LLAMA_CPP_SERVICE}:
        raise GGUFHostPreflightError("rendered Compose must contain exactly the llama.cpp service")
    service = services[LLAMA_CPP_SERVICE]
    if not isinstance(service, dict):
        raise GGUFHostPreflightError("rendered llama.cpp Compose service is invalid")
    return service


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def validate_compose_config(
    path: Path,
    *,
    contract: LlamaCppLaunchContract,
) -> str:
    """Validate the exact fully rendered Compose JSON that will be launched."""

    content, document = _json_object_bounded(path, maximum_bytes=MAX_COMPOSE_CONFIG_BYTES)
    service = _compose_service(document)
    mismatches: list[str] = []
    if service.get("image") != contract.image_ref:
        mismatches.append("image_ref")
    if service.get("pull_policy") != "never":
        mismatches.append("pull_policy")
    if service.get("read_only") is not True:
        mismatches.append("read_only")
    expected_user = f"{contract.gguf_root.stat().st_uid}:{contract.gguf_root.stat().st_gid}"
    if service.get("user") != expected_user:
        mismatches.append("user")
    if service.get("command") != list(contract.command):
        mismatches.append("command")

    environment = _string_mapping(service.get("environment"))
    expected_environment = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "LLAMA_API_KEY": contract.api_key,
    }
    if environment != expected_environment:
        mismatches.append("environment")

    volumes = service.get("volumes")
    bind_mounts = []
    if isinstance(volumes, list):
        bind_mounts = [
            item for item in volumes if isinstance(item, dict) and item.get("type") == "bind"
        ]
    if len(bind_mounts) != 1:
        mismatches.append("model_mount_count")
    else:
        mount = bind_mounts[0]
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

    labels = _string_mapping(service.get("labels"))
    if labels.get("org.csight.execution-mode") != "SHADOW":
        mismatches.append("execution_mode_label")
    if labels.get("org.csight.automatic-fallback") != "false":
        mismatches.append("fallback_label")
    if mismatches:
        raise GGUFHostPreflightError(
            "rendered Compose differs from the pinned launch contract: "
            + ", ".join(sorted(set(mismatches)))
        )
    return _digest(content)


def _container_document(path: Path) -> tuple[bytes, Mapping[str, Any]]:
    content = _regular_bytes(path, maximum_bytes=MAX_CONTAINER_INSPECT_BYTES)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GGUFHostPreflightError("container inspect is not valid JSON") from error
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise GGUFHostPreflightError("container inspect must contain exactly one object")
    return content, value[0]


def _container_environment(value: object) -> dict[str, str]:
    if not isinstance(value, list):
        return {}
    result: dict[str, str] = {}
    for item in value:
        if not isinstance(item, str) or "=" not in item:
            continue
        name, content = item.split("=", 1)
        result[name] = content
    return result


def validate_container_inspect(
    path: Path,
    *,
    contract: LlamaCppLaunchContract,
) -> str:
    """Bind the running container's image, mount, ports, and argv to preflight."""

    content, document = _container_document(path)
    config = document.get("Config")
    host_config = document.get("HostConfig")
    state = document.get("State")
    mounts = document.get("Mounts")
    if not all(isinstance(value, dict) for value in (config, host_config, state)):
        raise GGUFHostPreflightError("container inspect is missing required sections")
    assert isinstance(config, dict)
    assert isinstance(host_config, dict)
    assert isinstance(state, dict)
    mismatches: list[str] = []
    if document.get("Image") != contract.image_id:
        mismatches.append("image_id")
    if config.get("Image") != contract.image_ref:
        mismatches.append("image_ref")
    expected_user = f"{contract.gguf_root.stat().st_uid}:{contract.gguf_root.stat().st_gid}"
    if config.get("User") != expected_user:
        mismatches.append("user")
    if config.get("Cmd") != list(contract.command):
        mismatches.append("command")

    environment = _container_environment(config.get("Env"))
    expected_environment = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "LLAMA_API_KEY": contract.api_key,
    }
    if any(environment.get(name) != value for name, value in expected_environment.items()):
        mismatches.append("environment")

    model_mounts = []
    extra_bind_mounts = []
    if isinstance(mounts, list):
        for item in mounts:
            if not isinstance(item, dict) or item.get("Type") != "bind":
                continue
            if item.get("Destination") == "/models":
                model_mounts.append(item)
            else:
                extra_bind_mounts.append(item)
    if len(model_mounts) != 1 or extra_bind_mounts:
        mismatches.append("model_mount_count")
    else:
        mount = model_mounts[0]
        source = mount.get("Source")
        source_path = Path(source).resolve(strict=False) if isinstance(source, str) else None
        if source_path != contract.gguf_root or mount.get("RW") is not False:
            mismatches.append("model_mount")

    bindings = host_config.get("PortBindings")
    expected_port_key = f"{LLAMA_CPP_CONTAINER_PORT}/tcp"
    binding = bindings.get(expected_port_key) if isinstance(bindings, dict) else None
    if (
        not isinstance(binding, list)
        or len(binding) != 1
        or not isinstance(binding[0], dict)
        or binding[0].get("HostIp") != contract.bind_address
        or binding[0].get("HostPort") != str(contract.published_port)
    ):
        mismatches.append("port_binding")

    labels = _string_mapping(config.get("Labels"))
    if labels.get("org.csight.execution-mode") != "SHADOW":
        mismatches.append("execution_mode_label")
    if labels.get("org.csight.automatic-fallback") != "false":
        mismatches.append("fallback_label")
    health = state.get("Health")
    if (
        state.get("Running") is not True
        or not isinstance(health, dict)
        or health.get("Status") != "healthy"
    ):
        mismatches.append("healthy_running_state")
    if mismatches:
        raise GGUFHostPreflightError(
            "running container differs from the pinned launch contract: "
            + ", ".join(sorted(set(mismatches)))
        )
    return _digest(content)


def validate_served_model(contract: LlamaCppLaunchContract) -> None:
    """Require an authenticated OpenAI model listing with the exact served alias."""

    connection = http.client.HTTPConnection(
        contract.bind_address,
        contract.published_port,
        timeout=10,
    )
    try:
        connection.request(
            "GET",
            "/v1/models",
            headers={"Authorization": f"Bearer {contract.api_key}"},
        )
        response = connection.getresponse()
        content = response.read(MAX_MODELS_RESPONSE_BYTES + 1)
    except (OSError, TimeoutError, http.client.HTTPException) as error:
        raise GGUFHostPreflightError("authenticated /v1/models probe failed") from error
    finally:
        connection.close()
    if response.status != 200 or len(content) > MAX_MODELS_RESPONSE_BYTES:
        raise GGUFHostPreflightError(
            "authenticated /v1/models did not return a bounded 200 response"
        )
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GGUFHostPreflightError("authenticated /v1/models returned invalid JSON") from error
    data = document.get("data") if isinstance(document, dict) else None
    model_ids = (
        [item.get("id") for item in data if isinstance(item, dict)]
        if isinstance(data, list)
        else []
    )
    if model_ids != [contract.model_alias]:
        raise GGUFHostPreflightError("authenticated /v1/models served an unexpected model identity")


def _run(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise GGUFHostPreflightError(f"required host probe failed: {arguments[0]}") from error
    return result.stdout.strip()


def parse_mem_available_kib(content: str) -> int:
    matches = tuple(
        line.split() for line in content.splitlines() if line.startswith("MemAvailable:")
    )
    if len(matches) != 1 or len(matches[0]) != 3 or matches[0][2] != "kB":
        raise GGUFHostPreflightError("/proc/meminfo has no unique MemAvailable kB record")
    raw_value = matches[0][1]
    if not raw_value.isascii() or not raw_value.isdecimal():
        raise GGUFHostPreflightError("/proc/meminfo MemAvailable is invalid")
    value = int(raw_value)
    if value <= 0:
        raise GGUFHostPreflightError("/proc/meminfo MemAvailable must be positive")
    return value


def read_mem_available_kib(path: Path = Path("/proc/meminfo")) -> int:
    if path.is_symlink() or not path.is_file():
        raise GGUFHostPreflightError("/proc/meminfo is missing or unsafe")
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_MEMINFO_BYTES + 1)
    except OSError as error:
        raise GGUFHostPreflightError("/proc/meminfo could not be read") from error
    if len(content) > MAX_MEMINFO_BYTES:
        raise GGUFHostPreflightError("/proc/meminfo exceeded the safety bound")
    try:
        return parse_mem_available_kib(content.decode("ascii"))
    except UnicodeDecodeError as error:
        raise GGUFHostPreflightError("/proc/meminfo is not ASCII") from error


def validate_live_host(
    *,
    contract: LlamaCppLaunchContract,
) -> dict[str, object]:
    mem_available_kib = read_mem_available_kib()
    if mem_available_kib < MINIMUM_HOST_MEM_AVAILABLE_KIB:
        raise GGUFHostPreflightError("post-VLM-stop MemAvailable is below the required 50 GiB")
    gpu = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.free,compute_cap",
            "--format=csv,noheader,nounits",
        ]
    )
    gpu_lines = gpu.splitlines()
    if len(gpu_lines) != 1:
        raise GGUFHostPreflightError("host must expose exactly one parseable GPU")
    fields = [part.strip() for part in gpu_lines[0].split(",")]
    if len(fields) != 4:
        raise GGUFHostPreflightError("host must expose exactly one parseable GPU")
    name, total, free, capability = fields
    if name != "NVIDIA GeForce RTX 4090" or capability != "8.9":
        raise GGUFHostPreflightError("GPU is not the qualified RTX 4090 profile")
    image_identity = _run(
        [
            "docker",
            "image",
            "inspect",
            contract.image_ref,
            "--format",
            "{{json .Id}}",
        ]
    )
    try:
        observed_image_id = json.loads(image_identity)
    except json.JSONDecodeError as error:
        raise GGUFHostPreflightError("local llama.cpp image ID is invalid") from error
    if observed_image_id != contract.image_id:
        raise GGUFHostPreflightError("exact llama.cpp image digest is not staged locally")
    return {
        "gpu_name": name,
        "gpu_total_vram_mib": int(total),
        "gpu_free_vram_mib": int(free),
        "gpu_compute_capability": capability,
        "runtime_env_private": True,
        "bind_address_sha256": _digest(contract.bind_address.encode("ascii")),
        "runtime_image_digest": contract.image_id,
        "host_mem_available_mib": mem_available_kib // 1024,
    }


def _candidate(matrix_path: Path, candidate_id: str) -> Qwen4090GGUFCandidate:
    matrix = load_gguf_matrix(matrix_path)
    matches = tuple(item for item in matrix.candidates if item.candidate_id == candidate_id)
    if len(matches) != 1:
        raise GGUFHostPreflightError("candidate is not present exactly once in matrix v2")
    return matches[0]


def _require_path_override_matches(
    supplied: Path | None,
    *,
    expected: Path,
    option_name: str,
) -> None:
    if supplied is None:
        return
    if not supplied.is_absolute() or supplied.resolve(strict=False) != expected:
        raise GGUFHostPreflightError(
            f"{option_name} must match the value in the positional runtime env"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--runtime-identity", type=Path)
    parser.add_argument("--runtime-env", type=Path, required=True)
    parser.add_argument("--gguf-root", type=Path)
    parser.add_argument("--build-manifest", type=Path)
    parser.add_argument("--sbom", type=Path)
    parser.add_argument("--compose-config", type=Path)
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--post-start-container-inspect", type=Path)
    arguments = parser.parse_args()
    try:
        inputs = load_runtime_inputs(arguments.runtime_env)
        _require_path_override_matches(
            arguments.runtime_identity,
            expected=inputs.runtime_identity,
            option_name="--runtime-identity",
        )
        _require_path_override_matches(
            arguments.gguf_root,
            expected=inputs.gguf_root,
            option_name="--gguf-root",
        )
        _require_path_override_matches(
            arguments.build_manifest,
            expected=inputs.build_manifest,
            option_name="--build-manifest",
        )
        _require_path_override_matches(
            arguments.sbom,
            expected=inputs.sbom,
            option_name="--sbom",
        )
        candidate = _candidate(arguments.matrix, arguments.candidate_id)
        identity = load_runtime_identity(inputs.runtime_identity)
        validate_candidate_identity(candidate, identity)
        contract = build_launch_contract(inputs, identity=identity)
        runtime_env_digest = _digest(
            _regular_bytes(inputs.runtime_env, maximum_bytes=MAX_RUNTIME_ENV_BYTES)
        )
        compose_digest = (
            validate_compose_config(arguments.compose_config, contract=contract)
            if arguments.compose_config is not None
            else None
        )
        if arguments.post_start_container_inspect is not None:
            if arguments.compose_config is None:
                raise GGUFHostPreflightError("post-start validation requires --compose-config")
            inspect_digest = validate_container_inspect(
                arguments.post_start_container_inspect,
                contract=contract,
            )
            validate_served_model(contract)
            report = {
                "schema_version": "qwen4090_llama_cpp_post_start/1.0.0",
                "status": "PASS",
                "candidate_id": candidate.candidate_id,
                "runtime_env_digest": runtime_env_digest,
                "compose_config_digest": compose_digest,
                "container_inspect_digest": inspect_digest,
                "runtime_image_digest": contract.image_id,
                "artifact_content_digest": contract.gguf_digest,
                "artifact_weight_bytes": contract.gguf_bytes,
                "served_model_name": contract.model_alias,
            }
        elif arguments.config_only:
            if arguments.compose_config is None:
                raise GGUFHostPreflightError("config-only validation requires --compose-config")
            report = {
                "schema_version": "qwen4090_llama_cpp_config_preflight/1.0.0",
                "status": "PASS",
                "candidate_id": candidate.candidate_id,
                "runtime_env_digest": runtime_env_digest,
                "compose_config_digest": compose_digest,
                "runtime_image_digest": contract.image_id,
                "artifact_content_digest": contract.gguf_digest,
                "artifact_weight_bytes": contract.gguf_bytes,
                "served_model_name": contract.model_alias,
            }
        else:
            artifact_digest, artifact_bytes = validate_gguf_file(
                inputs.gguf_root,
                identity=identity,
            )
            validate_build_manifest(inputs.build_manifest, identity=identity)
            validate_sbom(inputs.sbom, identity=identity)
            host = validate_live_host(contract=contract)
            report = {
                "schema_version": "qwen4090_gguf_host_preflight/1.1.0",
                "status": (
                    "PASS"
                    if candidate.artifact.artifact.split("/", 1)[0] == "CSightICT"
                    else "SHADOW_CANDIDATE_ONLY"
                ),
                "strict_ready": candidate.artifact.artifact.split("/", 1)[0] == "CSightICT",
                "candidate_id": candidate.candidate_id,
                "runtime_env_digest": runtime_env_digest,
                "artifact_content_digest": artifact_digest,
                "artifact_weight_bytes": artifact_bytes,
                "compose_config_digest": compose_digest,
                "host": host,
            }
    except (GGUFHostPreflightError, OSError, ValueError) as error:
        report = {
            "schema_version": "qwen4090_gguf_host_preflight/1.1.0",
            "status": "FAIL",
            "strict_ready": False,
            "error": str(error),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] in {"PASS", "SHADOW_CANDIDATE_ONLY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
