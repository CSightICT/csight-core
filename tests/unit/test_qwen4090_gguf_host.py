"""Filesystem-safe GGUF, C++ build identity, and SBOM preflight checks."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import scripts.preflight_qwen4090_gguf_host as gguf_preflight
from scripts.preflight_qwen4090_gguf_host import (
    MINIMUM_HOST_MEM_AVAILABLE_KIB,
    GGUFHostPreflightError,
    LlamaCppLaunchContract,
    build_launch_contract,
    load_runtime_inputs,
    parse_mem_available_kib,
    validate_build_manifest,
    validate_compose_config,
    validate_container_inspect,
    validate_gguf_file,
    validate_sbom,
    validate_served_model,
)
from tests.unit.test_model_activation_gguf import (
    gguf_manifest_fixture,
    gguf_runtime_identity_fixture,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _runtime_bundle(
    tmp_path: Path,
) -> tuple[Path, LlamaCppLaunchContract]:
    identity = gguf_runtime_identity_fixture(gguf_manifest_fixture())
    gguf_root = tmp_path / "gguf"
    gguf_root.mkdir()
    (gguf_root / identity.gguf_filename).write_bytes(b"GGUF")
    identity_path = tmp_path / "runtime-identity.json"
    identity_path.write_text(identity.model_dump_json(), encoding="utf-8")
    build_manifest = tmp_path / "build-manifest.json"
    build_manifest.write_text("{}", encoding="utf-8")
    sbom = tmp_path / "sbom.json"
    sbom.write_text("{}", encoding="utf-8")
    runtime_env = tmp_path / "runtime.env"
    values = {
        "LLM_RUNTIME_ENV_FILE": str(runtime_env),
        "LLM_RUNTIME_IDENTITY_FILE": str(identity_path),
        "LLAMA_CPP_BUILD_MANIFEST": str(build_manifest),
        "LLAMA_CPP_SBOM": str(sbom),
        "LLAMA_CPP_IMAGE": identity.runtime_image,
        "LLAMA_CPP_GGUF_ROOT": str(gguf_root),
        "LLAMA_CPP_GGUF_FILENAME": identity.gguf_filename,
        "LLAMA_CPP_PORT": "18002",
        "LLM_BIND_ADDRESS": "100.64.10.20",
        "LLM_API_KEY": "9Yp!4tJx6Qm2Nz8Bv7Kr5Ws3Hd1Lc0Ae",
        "LLM_MODEL_ID": identity.served_model_name,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
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
    runtime_env.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )
    runtime_env.chmod(0o600)
    inputs = load_runtime_inputs(runtime_env)
    return runtime_env, build_launch_contract(inputs, identity=identity)


def _compose_document(contract: LlamaCppLaunchContract) -> dict[str, object]:
    return {
        "name": "llm",
        "services": {
            "qwen38-llama-cpp": {
                "image": contract.image_ref,
                "pull_policy": "never",
                "read_only": True,
                "user": f"{contract.gguf_root.stat().st_uid}:{contract.gguf_root.stat().st_gid}",
                "command": list(contract.command),
                "environment": {
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "LLAMA_API_KEY": contract.api_key,
                },
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(contract.gguf_root),
                        "target": "/models",
                        "read_only": True,
                    }
                ],
                "ports": [
                    {
                        "host_ip": contract.bind_address,
                        "published": str(contract.published_port),
                        "target": 8080,
                        "protocol": "tcp",
                    }
                ],
                "labels": {
                    "org.csight.execution-mode": "SHADOW",
                    "org.csight.automatic-fallback": "false",
                },
            }
        },
    }


def _container_document(contract: LlamaCppLaunchContract) -> list[dict[str, object]]:
    return [
        {
            "Image": contract.image_id,
            "Config": {
                "Image": contract.image_ref,
                "User": f"{contract.gguf_root.stat().st_uid}:{contract.gguf_root.stat().st_gid}",
                "Cmd": list(contract.command),
                "Env": [
                    "HF_HUB_OFFLINE=1",
                    "TRANSFORMERS_OFFLINE=1",
                    f"LLAMA_API_KEY={contract.api_key}",
                    "LD_LIBRARY_PATH=/usr/local/lib",
                ],
                "Labels": {
                    "org.csight.execution-mode": "SHADOW",
                    "org.csight.automatic-fallback": "false",
                },
            },
            "HostConfig": {
                "PortBindings": {
                    "8080/tcp": [
                        {
                            "HostIp": contract.bind_address,
                            "HostPort": str(contract.published_port),
                        }
                    ]
                }
            },
            "State": {"Running": True, "Health": {"Status": "healthy"}},
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": str(contract.gguf_root),
                    "Destination": "/models",
                    "RW": False,
                },
                {"Type": "tmpfs", "Source": "", "Destination": "/tmp", "RW": True},
            ],
        }
    ]


def test_cpp_build_sbom_and_exact_gguf_are_bound_to_runtime_identity(tmp_path: Path) -> None:
    gguf = b"GGUF-test-artifact"
    (tmp_path / gguf_manifest_fixture().gguf_filename).write_bytes(gguf)
    base = gguf_runtime_identity_fixture(gguf_manifest_fixture()).model_copy(
        update={
            "artifact_content_digest": _sha(gguf),
            "artifact_weight_bytes": len(gguf),
        }
    )
    build = {
        "schema_version": "csight_llama_cpp_build/1.0.0",
        "source_repository": "ggml-org/llama.cpp",
        "source_revision": base.llama_cpp_revision,
        "dockerfile_digest": "sha256:" + "a" * 64,
        "tool_image_digest": "sha256:" + "b" * 64,
        "runtime_image_digest": base.runtime_image_digest,
        "runtime_binary_digest": base.runtime_binary_digest,
        "quantizer_binary_digest": base.quantizer_binary_digest,
        "imatrix_binary_digest": "sha256:" + "c" * 64,
        "tokenizer_binary_digest": "sha256:" + "d" * 64,
        "cuda_architectures": ["89"],
        "cmake_options": {"GGML_CUDA": "ON", "CMAKE_BUILD_TYPE": "Release"},
        "base_image_digests": {
            "cuda_devel": "sha256:" + "e" * 64,
            "cuda_runtime": "sha256:" + "f" * 64,
        },
        "sbom_tool_image": "anchore/syft@sha256:" + "1" * 64,
    }
    build_bytes = json.dumps(build, sort_keys=True, separators=(",", ":")).encode()
    build_path = tmp_path / "build.json"
    build_path.write_bytes(build_bytes)
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "metadata": {
            "properties": [
                {"name": "runtime_image_digest", "value": base.runtime_image_digest},
                {"name": "llama_cpp_revision", "value": base.llama_cpp_revision},
                {"name": "runtime_binary_digest", "value": base.runtime_binary_digest},
                {"name": "quantizer_binary_digest", "value": base.quantizer_binary_digest},
            ]
        },
    }
    sbom_bytes = json.dumps(sbom, sort_keys=True, separators=(",", ":")).encode()
    sbom_path = tmp_path / "sbom.json"
    sbom_path.write_bytes(sbom_bytes)
    identity = base.model_copy(
        update={
            "runtime_build_manifest_digest": _sha(build_bytes),
            "sbom_digest": _sha(sbom_bytes),
        }
    )

    assert validate_gguf_file(tmp_path, identity=identity) == (_sha(gguf), len(gguf))
    assert validate_build_manifest(build_path, identity=identity) == _sha(build_bytes)
    assert validate_sbom(sbom_path, identity=identity) == _sha(sbom_bytes)


def test_cpp_build_validation_fails_without_cuda_architecture_89(tmp_path: Path) -> None:
    identity = gguf_runtime_identity_fixture(gguf_manifest_fixture())
    build = {
        "schema_version": "csight_llama_cpp_build/1.0.0",
        "source_repository": "ggml-org/llama.cpp",
        "source_revision": identity.llama_cpp_revision,
        "dockerfile_digest": "sha256:" + "a" * 64,
        "tool_image_digest": "sha256:" + "b" * 64,
        "runtime_image_digest": identity.runtime_image_digest,
        "runtime_binary_digest": identity.runtime_binary_digest,
        "quantizer_binary_digest": identity.quantizer_binary_digest,
        "imatrix_binary_digest": "sha256:" + "c" * 64,
        "tokenizer_binary_digest": "sha256:" + "d" * 64,
        "cuda_architectures": ["80"],
        "cmake_options": {"GGML_CUDA": "ON"},
        "base_image_digests": {
            "cuda_devel": "sha256:" + "e" * 64,
            "cuda_runtime": "sha256:" + "f" * 64,
        },
        "sbom_tool_image": "anchore/syft@sha256:" + "1" * 64,
    }
    content = json.dumps(build, sort_keys=True, separators=(",", ":")).encode()
    path = tmp_path / "build.json"
    path.write_bytes(content)
    identity = identity.model_copy(update={"runtime_build_manifest_digest": _sha(content)})

    with pytest.raises(GGUFHostPreflightError, match="architecture 89"):
        validate_build_manifest(path, identity=identity)


def test_mem_available_parser_enforces_unambiguous_kernel_units() -> None:
    assert parse_mem_available_kib("MemTotal: 100 kB\nMemAvailable: 52428800 kB\n") == (
        MINIMUM_HOST_MEM_AVAILABLE_KIB
    )
    for malformed in (
        "MemTotal: 100 kB\n",
        "MemAvailable: 50 GiB\n",
        "MemAvailable: nope kB\n",
        "MemAvailable: 1 kB\nMemAvailable: 2 kB\n",
    ):
        with pytest.raises(GGUFHostPreflightError):
            parse_mem_available_kib(malformed)


def test_runtime_env_is_the_only_owner_mode_600_launch_identity(tmp_path: Path) -> None:
    runtime_env, contract = _runtime_bundle(tmp_path)

    assert contract.model_alias == gguf_manifest_fixture().served_model_name
    assert contract.reasoning == "off"
    assert contract.flash_attention == "on"
    runtime_env.chmod(0o640)
    with pytest.raises(GGUFHostPreflightError, match="mode 600"):
        load_runtime_inputs(runtime_env)


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("LLAMA_CPP_IMAGE", "wrong/image:tag"),
        ("LLAMA_CPP_GGUF_FILENAME", "wrong.gguf"),
        ("LLM_MODEL_ID", "unexpected-model"),
        ("LLAMA_CPP_CONTEXT_SIZE", "8192"),
        ("LLAMA_CPP_PARALLEL", "2"),
        ("LLAMA_CPP_BATCH_SIZE", "1024"),
        ("LLAMA_CPP_UBATCH_SIZE", "256"),
        ("LLAMA_CPP_GPU_LAYERS", "40"),
        ("LLAMA_CPP_KV_CACHE_TYPE_K", "f16"),
        ("LLAMA_CPP_KV_CACHE_TYPE_V", "f16"),
        ("LLAMA_CPP_REASONING", "on"),
        ("LLAMA_CPP_FLASH_ATTN", "off"),
    ),
)
def test_runtime_env_drift_from_identity_fails_closed(
    tmp_path: Path,
    name: str,
    value: str,
) -> None:
    runtime_env, _ = _runtime_bundle(tmp_path)
    content = runtime_env.read_text(encoding="utf-8")
    content = "\n".join(
        f"{name}={value}" if line.startswith(f"{name}=") else line for line in content.splitlines()
    )
    runtime_env.write_text(content + "\n", encoding="utf-8")
    runtime_env.chmod(0o600)
    inputs = load_runtime_inputs(runtime_env)
    identity = gguf_runtime_identity_fixture(gguf_manifest_fixture())

    with pytest.raises(GGUFHostPreflightError, match="pinned runtime identity"):
        build_launch_contract(inputs, identity=identity)


def test_rendered_compose_and_running_container_match_exact_launch_contract(
    tmp_path: Path,
) -> None:
    _, contract = _runtime_bundle(tmp_path)
    compose_path = tmp_path / "compose.json"
    compose_path.write_text(json.dumps(_compose_document(contract)), encoding="utf-8")
    inspect_path = tmp_path / "inspect.json"
    inspect_path.write_text(json.dumps(_container_document(contract)), encoding="utf-8")

    assert validate_compose_config(compose_path, contract=contract).startswith("sha256:")
    assert validate_container_inspect(inspect_path, contract=contract).startswith("sha256:")


def test_compose_and_container_drift_fail_before_identity_can_be_claimed(tmp_path: Path) -> None:
    _, contract = _runtime_bundle(tmp_path)
    compose_path = tmp_path / "compose.json"
    inspect_path = tmp_path / "inspect.json"
    for drift, expected_error in (
        ("image_ref", "image_ref"),
        ("user", "user"),
        ("command", "command"),
        ("mount", "model_mount"),
        ("port", "port_binding"),
    ):
        compose = _compose_document(contract)
        service = compose["services"]["qwen38-llama-cpp"]  # type: ignore[index]
        if drift == "image_ref":
            service["image"] = "wrong/image:tag"  # type: ignore[index]
        elif drift == "user":
            service["user"] = "0:0"  # type: ignore[index]
        elif drift == "command":
            service["command"][3] = "wrong-alias"  # type: ignore[index]
        elif drift == "mount":
            service["volumes"][0]["source"] = str(tmp_path / "other")  # type: ignore[index]
        else:
            service["ports"][0]["host_ip"] = "127.0.0.1"  # type: ignore[index]
        compose_path.write_text(json.dumps(compose), encoding="utf-8")
        with pytest.raises(GGUFHostPreflightError, match=expected_error):
            validate_compose_config(compose_path, contract=contract)

    for drift, expected_error in (
        ("image_id", "image_id"),
        ("image_ref", "image_ref"),
        ("user", "user"),
        ("command", "command"),
        ("mount", "model_mount"),
        ("port", "port_binding"),
    ):
        container = _container_document(contract)
        if drift == "image_id":
            container[0]["Image"] = "sha256:" + "0" * 64
        elif drift == "image_ref":
            container[0]["Config"]["Image"] = "wrong/image:tag"  # type: ignore[index]
        elif drift == "user":
            container[0]["Config"]["User"] = "0:0"  # type: ignore[index]
        elif drift == "command":
            container[0]["Config"]["Cmd"][3] = "wrong-alias"  # type: ignore[index]
        elif drift == "mount":
            container[0]["Mounts"][0]["Source"] = str(tmp_path / "other")  # type: ignore[index]
        else:
            container[0]["HostConfig"]["PortBindings"]["8080/tcp"][0][  # type: ignore[index]
                "HostIp"
            ] = "127.0.0.1"
        inspect_path.write_text(json.dumps(container), encoding="utf-8")
        with pytest.raises(GGUFHostPreflightError, match=expected_error):
            validate_container_inspect(inspect_path, contract=contract)


def test_models_probe_uses_bearer_auth_and_requires_exact_single_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, contract = _runtime_bundle(tmp_path)
    observed: dict[str, object] = {}

    class _Response:
        status = 200

        def read(self, _maximum: int) -> bytes:
            return json.dumps({"data": [{"id": contract.model_alias}]}).encode()

    class _Connection:
        def __init__(self, host: str, port: int, *, timeout: int) -> None:
            observed.update(host=host, port=port, timeout=timeout)

        def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
            observed.update(method=method, path=path, headers=headers)

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            observed["closed"] = True

    monkeypatch.setattr(gguf_preflight.http.client, "HTTPConnection", _Connection)

    validate_served_model(contract)

    assert observed["path"] == "/v1/models"
    assert observed["headers"] == {"Authorization": f"Bearer {contract.api_key}"}
    assert observed["closed"] is True

    class _WrongResponse:
        status = 200

        def read(self, _maximum: int) -> bytes:
            return b'{"data":[{"id":"wrong-model"}]}'

    def wrong_getresponse(_self: _Connection) -> _WrongResponse:
        return _WrongResponse()

    monkeypatch.setattr(_Connection, "getresponse", wrong_getresponse)
    with pytest.raises(GGUFHostPreflightError, match="unexpected model identity"):
        validate_served_model(contract)


def test_launcher_freezes_and_validates_rendered_compose_before_and_after_up() -> None:
    launcher = ROOT / "infra/llm/serve_llama_cpp_candidate.sh"
    compose = ROOT / "infra/llm/compose.llama-cpp.yml"
    source = launcher.read_text(encoding="utf-8")
    compose_source = compose.read_text(encoding="utf-8")

    render_position = source.index("config --format json")
    preflight_position = source.index('"${preflight[@]}"\n', render_position)
    up_position = source.index('up --detach --wait "${service_name}"', preflight_position)
    inspect_position = source.index('inspect "${container_id}"', up_position)
    postflight_position = source.index("--post-start-container-inspect", inspect_position)
    assert (
        render_position < preflight_position < up_position < inspect_position < postflight_position
    )
    assert "env -i" in source
    assert '-f "${rendered_compose}"' in source
    assert '--runtime-env "${runtime_env}"' in source
    assert "${LLM_RUNTIME_ENV_FILE}" not in source
    assert "${LLM_RUNTIME_IDENTITY_FILE}" not in source
    assert "caller-owned with mode 600" in source
    assert "${LLAMA_CPP_REASONING:?reasoning mode required}" in compose_source
    assert "${LLAMA_CPP_FLASH_ATTN:?flash attention mode required}" in compose_source


def test_llama_cpp_image_packages_the_canonical_tools_and_dynamic_backends() -> None:
    dockerfile = ROOT / "infra/llm/llama.cpp/Dockerfile"
    source = dockerfile.read_text(encoding="utf-8")

    for binary in ("llama-server", "llama-quantize", "llama-imatrix", "llama-tokenize"):
        assert f"/app/{binary}" in source
    assert 'ldd "/app/${binary}"' in source
    assert "build/bin/*.so* /app/" in source
    assert "ENV LD_LIBRARY_PATH=/app" in source
    assert "test -e /app/libggml-cuda.so" in source
    assert "-name 'libggml-cpu*.so*'" in source
    assert 'grep -F "not found"' in source
    assert "libgomp1" in source
    assert 'ENTRYPOINT ["/app/llama-server"]' in source


def test_maintenance_checks_memory_after_stop_with_restore_trap_armed() -> None:
    script = ROOT / "infra/llm/run_qwen4090_llama_cpp_maintenance_dev.sh"
    source = script.read_text(encoding="utf-8")

    trap_position = source.index("trap restore_vlm EXIT")
    stop_position = source.index('stop "${vlm_service}"', trap_position)
    memory_position = source.index('mem_available_kib="$', stop_position)
    serve_position = source.index("ALLOW_LLAMA_CPP_SERVE=YES", memory_position)
    assert trap_position < stop_position < memory_position < serve_position
    assert "50 * 1024 * 1024" in source
    assert "below the required 50 GiB" in source
    assert '"${path}" != /*' in source
    assert "$(stat -c '%u:%a' \"${private_env}\")" in source
    assert 'ps --quiet "${vlm_service}"' in source
    assert "docker inspect --format '{{.Config.Image}}'" in source
    assert "docker inspect --format '{{.Image}}'" in source
    assert source.count("require_running_vlm_identity") >= 3
    subprocess.run(["bash", "-n", str(script)], check=True)
