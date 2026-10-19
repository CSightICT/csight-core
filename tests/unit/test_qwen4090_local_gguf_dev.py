"""Fail-closed contracts for unpublished local GGUF canary/Dev execution."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from app.platform.model_activation import RuntimeLLMIdentityV1_1
from app.platform.qwen4090_gguf import (
    GGUFQuantizationVariant,
    LocalUnpublishedGGUFDevIdentity,
)
from scripts.preflight_qwen4090_gguf_host import (
    LlamaCppBuildManifest,
    LlamaCppLaunchContract,
)
from scripts.preflight_qwen4090_local_gguf_dev import (
    LocalGGUFDevPreflightError,
    build_local_dev_identity,
    container_instance_digest,
    load_local_dev_runtime_inputs,
    select_local_dev_candidate,
    validate_authentication_and_canary,
    validate_local_dev_compose_config,
    validate_local_dev_container_inspect,
    validate_quantization_evidence,
)
from scripts.verify_qwen4090_gguf_candidates import DEFAULT_MATRIX, load_gguf_matrix

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "a" * 64
EVIDENCE_DIGEST = "sha256:" + "e" * 64


def _candidate(candidate_id: str = "qwen38-27b-csight-q4-k-m-llama-cpp"):
    matrix = load_gguf_matrix(DEFAULT_MATRIX)
    candidate = select_local_dev_candidate(matrix, candidate_id)
    return matrix, candidate


def _identity() -> LocalUnpublishedGGUFDevIdentity:
    matrix, candidate = _candidate()
    return LocalUnpublishedGGUFDevIdentity.from_candidate(
        candidate,
        candidate_matrix_digest=matrix.matrix_digest,
        quantization_run_evidence_digest=EVIDENCE_DIGEST,
    )


def _contract(tmp_path: Path) -> LlamaCppLaunchContract:
    identity = _identity()
    return LlamaCppLaunchContract(
        image_ref=identity.runtime_image,
        image_id=identity.runtime_image_digest,
        gguf_root=tmp_path,
        gguf_filename=identity.gguf_filename,
        gguf_digest=identity.artifact_content_digest,
        gguf_bytes=identity.artifact_weight_bytes,
        model_alias=identity.served_model_name,
        bind_address="100.116.246.125",
        published_port=18002,
        context_size=identity.max_context_tokens,
        parallel=identity.max_num_sequences,
        batch_size=identity.batch_size,
        ubatch_size=identity.ubatch_size,
        gpu_layers=identity.gpu_layers,
        kv_cache_type_k=identity.kv_cache_type_k,
        kv_cache_type_v=identity.kv_cache_type_v,
        reasoning="off",
        flash_attention="on",
        api_key="local-dev-private-key-with-enough-entropy",
    )


def _labels() -> dict[str, str]:
    return {
        "org.csight.automatic-fallback": "false",
        "org.csight.core-routing": "false",
        "org.csight.execution-scope": "CANARY_DEV_ONLY",
        "org.csight.primary-allowed": "false",
        "org.csight.publication-state": "LOCAL_UNPUBLISHED",
        "org.csight.release-eligible": "false",
    }


def _compose_document(contract: LlamaCppLaunchContract) -> dict[str, Any]:
    return {
        "name": "csight-qwen38-local-dev",
        "services": {
            "qwen38-llama-cpp": {
                "image": contract.image_ref,
                "pull_policy": "never",
                "read_only": True,
                "restart": "no",
                "user": f"{contract.gguf_root.stat().st_uid}:{contract.gguf_root.stat().st_gid}",
                "pids_limit": 1024,
                "command": list(contract.command),
                "environment": {
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "LLAMA_API_KEY": contract.api_key,
                },
                "labels": _labels(),
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "networks": {"local-dev": None},
                "logging": {
                    "driver": "json-file",
                    "options": {"max-file": "3", "max-size": "10m"},
                },
                "deploy": {
                    "resources": {
                        "reservations": {
                            "devices": [
                                {
                                    "driver": "nvidia",
                                    "count": 1,
                                    "capabilities": ["gpu"],
                                }
                            ]
                        }
                    }
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
            }
        },
        "networks": {
            "local-dev": {
                "name": "csight-qwen38-local-dev-inbound",
                "driver": "bridge",
                "internal": False,
                "driver_opts": {"com.docker.network.bridge.enable_ip_masquerade": "false"},
            }
        },
    }


def _container_document(contract: LlamaCppLaunchContract) -> list[dict[str, Any]]:
    labels = {
        **_labels(),
        "com.docker.compose.project": "csight-qwen38-local-dev",
        "com.docker.compose.service": "qwen38-llama-cpp",
    }
    return [
        {
            "Image": contract.image_id,
            "Id": "c" * 64,
            "Config": {
                "Image": contract.image_ref,
                "User": f"{contract.gguf_root.stat().st_uid}:{contract.gguf_root.stat().st_gid}",
                "Cmd": list(contract.command),
                "Env": [
                    "HF_HUB_OFFLINE=1",
                    "TRANSFORMERS_OFFLINE=1",
                    f"LLAMA_API_KEY={contract.api_key}",
                ],
                "Labels": labels,
            },
            "HostConfig": {
                "ReadonlyRootfs": True,
                "PidsLimit": 1024,
                "NetworkMode": "csight-qwen38-local-dev-inbound",
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges:true"],
                "DeviceRequests": [{"Driver": "nvidia", "Count": 1, "Capabilities": [["gpu"]]}],
                "LogConfig": {
                    "Type": "json-file",
                    "Config": {"max-file": "3", "max-size": "10m"},
                },
                "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
                "PortBindings": {
                    "8080/tcp": [
                        {
                            "HostIp": contract.bind_address,
                            "HostPort": str(contract.published_port),
                        }
                    ]
                },
            },
            "State": {"Running": True, "Health": {"Status": "healthy"}},
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": str(contract.gguf_root),
                    "Destination": "/models",
                    "RW": False,
                }
            ],
            "NetworkSettings": {"Networks": {"csight-qwen38-local-dev-inbound": {}}},
        }
    ]


def _sha(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def test_local_dev_identity_keeps_revision_null_and_all_promotion_gates_false() -> None:
    identity = _identity()

    assert identity.artifact_revision is None
    assert identity.publication_state == "LOCAL_UNPUBLISHED"
    assert identity.execution_scope == "CANARY_DEV_ONLY"
    assert identity.quantization_variant is GGUFQuantizationVariant.MIXED_Q4_Q6
    assert identity.release_eligible is False
    assert identity.primary_allowed is False
    assert identity.core_routing_allowed is False
    assert identity.sealed_test_allowed is False
    assert identity.freeze_allowed is False
    assert identity.raw_customer_data_allowed is False
    assert identity.identity_digest.startswith("sha256:")

    with pytest.raises(ValidationError):
        RuntimeLLMIdentityV1_1.model_validate(identity.model_dump(mode="json"))


def test_local_dev_identity_rejects_fake_revision_and_unqualified_variant() -> None:
    matrix, candidate = _candidate()
    published = candidate.model_copy(
        update={"artifact": candidate.artifact.model_copy(update={"artifact_revision": "1" * 40})}
    )
    with pytest.raises(ValueError, match="artifact_revision=null"):
        LocalUnpublishedGGUFDevIdentity.from_candidate(
            published,
            candidate_matrix_digest=matrix.matrix_digest,
            quantization_run_evidence_digest=EVIDENCE_DIGEST,
        )

    legacy_variant = candidate.model_copy(
        update={
            "artifact": candidate.artifact.model_copy(
                update={"quantization_variant": GGUFQuantizationVariant.UNKNOWN_LEGACY}
            )
        }
    )
    with pytest.raises(ValueError, match="explicit quantization variant"):
        LocalUnpublishedGGUFDevIdentity.from_candidate(
            legacy_variant,
            candidate_matrix_digest=matrix.matrix_digest,
            quantization_run_evidence_digest=EVIDENCE_DIGEST,
        )


def test_local_dev_selection_requires_exact_unpublished_blockers() -> None:
    matrix, candidate = _candidate()
    published = candidate.model_copy(
        update={"artifact": candidate.artifact.model_copy(update={"artifact_revision": "1" * 40})}
    )
    mutated_matrix = matrix.model_copy(update={"candidates": (published, matrix.candidates[1])})

    with pytest.raises(LocalGGUFDevPreflightError, match="unpublished-revision"):
        select_local_dev_candidate(mutated_matrix, candidate.candidate_id)


def test_runtime_env_forbids_release_revision_and_binds_matrix_and_evidence(
    tmp_path: Path,
) -> None:
    matrix, candidate = _candidate()
    gguf_root = tmp_path / "gguf"
    gguf_root.mkdir()
    build = tmp_path / "build.json"
    sbom = tmp_path / "sbom.json"
    evidence = tmp_path / "quant.json"
    for path in (build, sbom, evidence):
        path.write_text("{}", encoding="utf-8")
    runtime = tmp_path / "runtime.env"
    runtime.write_text(
        "\n".join(
            (
                f"LLM_RUNTIME_ENV_FILE={runtime}",
                f"QWEN4090_CANDIDATE_MATRIX_DIGEST={matrix.matrix_digest}",
                f"QWEN4090_QUANTIZATION_EVIDENCE={evidence}",
                f"QWEN4090_QUANTIZATION_EVIDENCE_DIGEST={_sha(evidence.read_bytes())}",
                f"LLAMA_CPP_BUILD_MANIFEST={build}",
                f"LLAMA_CPP_SBOM={sbom}",
                f"LLAMA_CPP_GGUF_ROOT={gguf_root}",
                f"LLAMA_CPP_IMAGE={candidate.serving.runtime_image}",
                f"LLAMA_CPP_GGUF_FILENAME={candidate.artifact.gguf_filename}",
                "LLAMA_CPP_PORT=18002",
                "LLM_BIND_ADDRESS=100.116.246.125",
                "LLM_API_KEY=local-dev-private-key-with-enough-entropy",
                f"LLM_MODEL_ID={candidate.serving.served_model_name}",
                "HF_HUB_OFFLINE=1",
                "TRANSFORMERS_OFFLINE=1",
                "LLAMA_CPP_CONTEXT_SIZE=4096",
                "LLAMA_CPP_PARALLEL=1",
                "LLAMA_CPP_BATCH_SIZE=512",
                "LLAMA_CPP_UBATCH_SIZE=128",
                "LLAMA_CPP_GPU_LAYERS=all",
                "LLAMA_CPP_KV_CACHE_TYPE_K=q8_0",
                "LLAMA_CPP_KV_CACHE_TYPE_V=q8_0",
                "LLAMA_CPP_REASONING=off",
                "LLAMA_CPP_FLASH_ATTN=on",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    runtime.chmod(0o600)
    inputs = load_local_dev_runtime_inputs(runtime)
    identity = build_local_dev_identity(matrix=matrix, candidate=candidate, inputs=inputs)
    assert identity.artifact_revision is None

    runtime.write_text(runtime.read_text(encoding="utf-8") + f"LLM_MODEL_REVISION={'1' * 40}\n")
    with pytest.raises(LocalGGUFDevPreflightError, match="forbidden"):
        load_local_dev_runtime_inputs(runtime)


def test_quantization_evidence_binds_selected_output_recipe_and_toolchain(tmp_path: Path) -> None:
    identity = _identity()
    tool_digest = "sha256:" + "b" * 64
    build = LlamaCppBuildManifest(
        schema_version="csight_llama_cpp_build/1.0.0",
        source_repository="ggml-org/llama.cpp",
        source_revision=identity.llama_cpp_revision,
        dockerfile_digest=DIGEST,
        tool_image_digest=tool_digest,
        runtime_image_digest=identity.runtime_image_digest,
        runtime_binary_digest=identity.runtime_binary_digest,
        quantizer_binary_digest=identity.quantizer_binary_digest,
        imatrix_binary_digest=DIGEST,
        tokenizer_binary_digest=DIGEST,
        cuda_architectures=("89",),
        cmake_options={"GGML_CUDA": True},
        base_image_digests={"cuda_devel": DIGEST, "cuda_runtime": DIGEST},
        sbom_tool_image="syft@" + DIGEST,
    )
    evidence = {
        "schema_version": "llama_cpp_quantization_run_evidence/1.1.0",
        "status": "PASS",
        "execution_mode": "DOCKER_OFFLINE",
        "phase": "FINAL_CANDIDATES",
        "plan_digest": DIGEST,
        "llama_cpp_revision": identity.llama_cpp_revision,
        "tool_image_id": tool_digest,
        "quantize_binary_path": "/app/llama-quantize",
        "quantize_binary_digest": identity.quantizer_binary_digest,
        "docker_limits": {
            "network": "NONE",
            "root_filesystem": "READ_ONLY",
            "gpu_devices": "NONE",
            "pull": "NEVER",
        },
        "commands": [
            {
                "order": 1,
                "operation": "QUANTIZE",
                "recipe_name": "mixed",
                "recipe_digest": identity.quantization_recipe_digest,
                "output_name": identity.gguf_filename,
                "output_digest": identity.artifact_content_digest,
                "output_bytes": identity.artifact_weight_bytes,
                "execution": "EXECUTED",
            }
        ],
        "all_host_inputs_reverified_after_execution": True,
        "final_candidates_from_bf16": True,
        "q8_helper_used_as_final_source": False,
        "sealed_test_data_used": False,
        "shell_interpolation_used": False,
    }
    content = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    path = tmp_path / "evidence.json"
    path.write_bytes(content)
    identity = identity.model_copy(update={"quantization_run_evidence_digest": _sha(content)})

    assert validate_quantization_evidence(path, identity=identity, build_manifest=build) == _sha(
        content
    )

    evidence["commands"][0]["output_bytes"] = identity.artifact_weight_bytes + 1  # type: ignore[index]
    tampered = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(tampered)
    identity = identity.model_copy(update={"quantization_run_evidence_digest": _sha(tampered)})
    with pytest.raises(LocalGGUFDevPreflightError, match="differs"):
        validate_quantization_evidence(path, identity=identity, build_manifest=build)


def test_local_dev_compose_and_container_reject_promotion_or_routing_labels(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path)
    compose = _compose_document(contract)
    compose_path = tmp_path / "compose.json"
    compose_path.write_text(json.dumps(compose), encoding="utf-8")
    assert validate_local_dev_compose_config(compose_path, contract=contract).startswith("sha256:")

    compose["services"]["qwen38-llama-cpp"]["labels"][  # type: ignore[index]
        "org.csight.core-routing"
    ] = "true"
    compose_path.write_text(json.dumps(compose), encoding="utf-8")
    with pytest.raises(LocalGGUFDevPreflightError, match="labels"):
        validate_local_dev_compose_config(compose_path, contract=contract)

    compose = _compose_document(contract)
    del compose["services"]["qwen38-llama-cpp"]["deploy"]  # type: ignore[index]
    compose_path.write_text(json.dumps(compose), encoding="utf-8")
    with pytest.raises(LocalGGUFDevPreflightError, match="gpu_reservation"):
        validate_local_dev_compose_config(compose_path, contract=contract)

    compose = _compose_document(contract)
    compose["services"]["qwen38-llama-cpp"]["user"] = "0:0"  # type: ignore[index]
    compose_path.write_text(json.dumps(compose), encoding="utf-8")
    with pytest.raises(LocalGGUFDevPreflightError, match="user"):
        validate_local_dev_compose_config(compose_path, contract=contract)

    inspect = _container_document(contract)
    inspect_path = tmp_path / "inspect.json"
    inspect_path.write_text(json.dumps(inspect), encoding="utf-8")
    assert validate_local_dev_container_inspect(inspect_path, contract=contract).startswith(
        "sha256:"
    )
    assert container_instance_digest(inspect_path).startswith("sha256:")
    inspect[0]["Config"]["Labels"]["org.csight.release-eligible"] = "true"
    inspect_path.write_text(json.dumps(inspect), encoding="utf-8")
    with pytest.raises(LocalGGUFDevPreflightError, match="labels"):
        validate_local_dev_container_inspect(inspect_path, contract=contract)

    inspect = _container_document(contract)
    inspect[0]["HostConfig"]["LogConfig"]["Config"]["max-size"] = "unbounded"
    inspect_path.write_text(json.dumps(inspect), encoding="utf-8")
    with pytest.raises(LocalGGUFDevPreflightError, match="bounded_logging"):
        validate_local_dev_container_inspect(inspect_path, contract=contract)

    inspect = _container_document(contract)
    inspect[0]["Config"]["User"] = "0:0"
    inspect_path.write_text(json.dumps(inspect), encoding="utf-8")
    with pytest.raises(LocalGGUFDevPreflightError, match="user"):
        validate_local_dev_container_inspect(inspect_path, contract=contract)


def test_authenticated_canary_requires_unauthenticated_rejection_and_exact_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del tmp_path
    contract = _contract(Path("/tmp/csight-local-dev-test"))
    calls: list[dict[str, object]] = []
    responses = iter(
        (
            (401, b"{}"),
            (
                200,
                json.dumps(
                    {
                        "model": contract.model_alias,
                        "choices": [{"message": {"content": '{"status":"ok"}'}}],
                    }
                ).encode(),
            ),
        )
    )

    class _Response:
        def __init__(self, status: int, content: bytes) -> None:
            self.status = status
            self.content = content

        def read(self, maximum: int) -> bytes:
            return self.content[:maximum]

    class _Connection:
        def __init__(self, *_: object, **__: object) -> None:
            self.response = _Response(*next(responses))

        def request(self, method: str, path: str, **kwargs: object) -> None:
            calls.append({"method": method, "path": path, **kwargs})

        def getresponse(self) -> _Response:
            return self.response

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "scripts.preflight_qwen4090_local_gguf_dev.http.client.HTTPConnection",
        _Connection,
    )
    validate_authentication_and_canary(contract)

    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/v1/chat/completions"
    unauthenticated_headers = calls[0]["headers"]
    assert isinstance(unauthenticated_headers, dict)
    assert "Authorization" not in unauthenticated_headers
    assert calls[1]["method"] == "POST"
    headers = calls[1]["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == f"Bearer {contract.api_key}"


def test_local_dev_launcher_is_separate_guarded_and_shell_valid() -> None:
    launcher = ROOT / "infra/llm/serve_llama_cpp_local_dev.sh"
    strict_launcher = ROOT / "infra/llm/serve_llama_cpp_candidate.sh"
    source = launcher.read_text(encoding="utf-8")
    strict_source = strict_launcher.read_text(encoding="utf-8")

    guard_position = source.index("if ! require_live_restore_guard")
    preflight_position = source.index('"${preflight[@]}"\n', guard_position)
    up_position = source.index('up --detach --wait "${service_name}"', preflight_position)
    assert guard_position < preflight_position < up_position
    assert "ALLOW_LLAMA_CPP_LOCAL_DEV" in source
    assert 'python_bin="${CSIGHT_LOCAL_DEV_PYTHON_BIN:-${repo_root}/.venv/bin/python}"' in source
    assert '[[ "${python_bin}" != /* || ! -f "${python_bin}" || ! -x "${python_bin}" ]]' in source
    assert "python_uid" in source
    assert "8#${python_mode} & 8#022" in source
    assert source.index("stat -c '%u:%a'") < source.index("stat -f '%u:%Lp'")
    assert strict_source.index("stat -c '%u:%a'") < strict_source.index("stat -f '%u:%Lp'")
    assert 'preflight=(\n  "${python_bin}"' in source
    assert "CSIGHT_LOCAL_DEV_POST_START_EVIDENCE" in source
    assert 'startup_log="${post_start_parent}/local-dev-startup.log"' in source
    assert 'post_start_failure="${post_start_parent}/local-dev-post-start-failure.json"' in source
    assert '"${timeout_bin}" --signal=KILL 10s' in source
    assert 'logs --no-color --timestamps --tail 1000 "${service_name}"' in source
    assert 'chmod 600 "${startup_log}"' in source
    assert 'ln "${post_start_temporary}" "${post_start_failure}"' in source
    capture_position = source.index("capture_startup_log", source.index("cleanup()"))
    failure_down_position = source.index("down --remove-orphans", capture_position)
    assert capture_position < failure_down_position
    assert 'ln "${post_start_temporary}" "${post_start_evidence}"' in source
    assert "post_start_digest=" in source
    assert "preflight_qwen4090_local_gguf_dev.py" in source
    assert '--project-name "${project_name}"' in source
    assert "preflight_qwen4090_local_gguf_dev.py" not in strict_source
    assert "ALLOW_LLAMA_CPP_LOCAL_DEV" not in strict_source
    subprocess.run(["bash", "-n", str(launcher)], check=True)


def test_container_python_launcher_is_pinned_read_only_and_shell_valid() -> None:
    launcher = ROOT / "infra/llm/qwen4090_local_dev_container_python.sh"
    source = launcher.read_text(encoding="utf-8")

    assert "CSIGHT_LOCAL_DEV_PYTHON_IMAGE_ID" in source
    assert "--pull=never" in source
    assert "--network host" in source
    assert "--gpus all" in source
    assert "--read-only" in source
    assert "--volume /home/data:/home/data:ro" in source
    assert "--volume /home/user:/home/user:ro" in source
    assert "--entrypoint /app/.venv/bin/python" in source
    subprocess.run(["bash", "-n", str(launcher)], check=True)


def test_local_dev_compose_declares_isolated_non_promotable_runtime() -> None:
    compose_path = ROOT / "infra/llm/compose.llama-cpp-local-dev.yml"
    document = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    service = document["services"]["qwen38-llama-cpp"]

    assert document["name"] == "csight-qwen38-local-dev"
    assert document["networks"]["local-dev"] == {
        "name": "csight-qwen38-local-dev-inbound",
        "driver": "bridge",
        "internal": False,
        "driver_opts": {"com.docker.network.bridge.enable_ip_masquerade": "false"},
    }
    assert service["restart"] == "no"
    assert service["read_only"] is True
    assert service["labels"] == _labels()
    assert service["logging"]["options"] == {"max-size": "10m", "max-file": "3"}
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]


def test_local_dev_maintenance_arms_independent_restore_before_vlm_stop() -> None:
    runner = ROOT / "infra/llm/run_qwen4090_llama_cpp_local_dev_maintenance.sh"
    watchdog = ROOT / "infra/llm/qwen4090_local_dev_restore_watchdog.sh"
    runner_source = runner.read_text(encoding="utf-8")
    watchdog_source = watchdog.read_text(encoding="utf-8")

    watchdog_position = runner_source.index('nohup setsid bash "${watchdog}" monitor')
    guard_position = runner_source.index("schema_version=csight_local_dev_restore_guard/1.0.0")
    trap_position = runner_source.index("trap cleanup EXIT", guard_position)
    process_definition_position = runner_source.index("process_matches() {")
    live_watchdog_position = runner_source.index(
        'if ! process_matches "${watchdog_pid}" "${watchdog_ticks}"', trap_position
    )
    stop_position = runner_source.index('docker stop --time 60 "${vlm_id}"', trap_position)
    launch_position = runner_source.index('"${launcher}" "${candidate_id}"', stop_position)
    assert (
        watchdog_position
        < guard_position
        < trap_position
        < live_watchdog_position
        < stop_position
        < launch_position
    )
    assert process_definition_position < live_watchdog_position
    assert "for command in awk docker flock nohup setsid ps" in runner_source
    assert runner_source.count('wait_with_live_watchdog "${dev_pid}" "${dev_ticks}"') == 2
    assert 'while process_matches "${child_pid}" "${child_ticks}"' in runner_source
    assert "independent VLM restoration watchdog exited after DEV_LOCAL child" in runner_source
    assert runner_source.count('dev_ticks="$(process_start_ticks "${dev_pid}")"') == 2
    assert 'CSIGHT_LOCAL_DEV_PYTHON_BIN="${local_dev_python_bin}"' in runner_source
    assert 'CSIGHT_LOCAL_DEV_POST_START_EVIDENCE="${post_start_evidence}"' in runner_source

    candidate_down_position = watchdog_source.index("candidate_down()")
    restore_position = watchdog_source.index("restore_resources()")
    candidate_call_position = watchdog_source.index("candidate_down", restore_position)
    vlm_start_position = watchdog_source.index('docker start "${vlm_id}"', candidate_call_position)
    exact_check_position = watchdog_source.index(
        "validate_exact_vlm && authenticated_vlm_canary", vlm_start_position
    )
    assert candidate_down_position < restore_position < candidate_call_position
    assert candidate_call_position < vlm_start_position < exact_check_position
    assert "docker compose" not in watchdog_source[vlm_start_position:exact_check_position]
    assert "OWNER_LOST" in watchdog_source
    assert "RestartCount" in watchdog_source
    assert "OOMKilled" in watchdog_source
    assert "flock -x 9" in watchdog_source

    subprocess.run(["bash", "-n", str(runner)], check=True)
    subprocess.run(["bash", "-n", str(watchdog)], check=True)
