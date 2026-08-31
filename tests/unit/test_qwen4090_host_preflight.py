"""Privacy-safe RTX 4090 host preflight tests without GPU or network access."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

import scripts.preflight_qwen4090_host as host_preflight
from app.platform.qwen4090_host import (
    HostCheckStatus,
    HostPreflightStatus,
    Qwen4090HostEvidence,
    RTX4090GpuHostEvidence,
    assess_qwen4090_host,
)
from app.platform.qwen4090_release import Qwen4090CandidateMatrix
from scripts.preflight_qwen4090_host import (
    HostPreflightError,
    _local_ipv4_addresses,  # pyright: ignore[reportPrivateUsage]
    api_key_valid,
    artifact_evidence,
    calibration_dataset_digest,
    canonical_dependency_lock_digest,
    parse_private_env,
    quantization_recipe_digest,
    sbom_digest,
)
from scripts.verify_qwen4090_candidates import DEFAULT_MATRIX, load_matrix

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/preflight_qwen4090_host.py"
LAUNCHER = ROOT / "infra/llm/serve_qwen_candidate.sh"
COMPOSE = ROOT / "infra/llm/compose.llm.yml"
CONTAINER_PREFLIGHT = ROOT / "infra/llm/run_qwen4090_host_preflight_container.sh"
CANDIDATE_ID = "qwen3-8b-fp8-official-vllm026"
COMMUNITY_CANDIDATE_ID = "qwen38-27b-awq-int4-community-vllm028"


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_local_address_probe_falls_back_when_iproute2_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Probe:
        def __enter__(self) -> _Probe:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def fileno(self) -> int:
            return 7

    def missing_ip(_arguments: list[str], *, timeout: int = 30) -> str:
        del timeout
        raise HostPreflightError("ip is unavailable")

    response = bytearray(256)
    response[20:24] = socket.inet_aton("100.116.246.125")

    def socket_factory(*_args: object) -> _Probe:
        return _Probe()

    def fake_ioctl(*_args: object) -> bytes:
        return bytes(response)

    monkeypatch.setattr(host_preflight, "_run", missing_ip)
    monkeypatch.setattr(host_preflight.socket, "socket", socket_factory)
    monkeypatch.setattr(host_preflight.socket, "if_nameindex", lambda: [(1, "tailscale0")])
    monkeypatch.setattr(host_preflight.fcntl, "ioctl", fake_ioctl)

    assert _local_ipv4_addresses() == {"100.116.246.125"}


def _evidence(candidate_id: str = CANDIDATE_ID, **updates: object) -> Qwen4090HostEvidence:
    candidate = next(
        item for item in load_matrix(DEFAULT_MATRIX).candidates if item.candidate_id == candidate_id
    )
    values: dict[str, object] = {
        "schema_version": "qwen4090_host_evidence/1.0.0",
        "collected_at": datetime(2026, 8, 30, tzinfo=UTC),
        "os_name": "Linux",
        "machine": "x86_64",
        "kernel_release": "6.8.0",
        "gpus": (
            RTX4090GpuHostEvidence(
                name="NVIDIA GeForce RTX 4090",
                driver_version="580.65.06",
                compute_capability="8.9",
                total_vram_mib=24564,
                free_vram_mib=24000,
                uuid_sha256=_sha256("GPU-private-id"),
            ),
        ),
        "active_compute_process_count": 0,
        "docker_server_os": "linux",
        "docker_server_arch": "x86_64",
        "docker_server_version": "28.3.3",
        "nvidia_runtime_available": True,
        "runtime_image_digest": candidate.serving.runtime_image_digest,
        "runtime_env_private": True,
        "api_key_valid": True,
        "hf_hub_offline": True,
        "transformers_offline": True,
        "bind_address_is_tailscale": True,
        "bind_address_is_local": True,
        "bind_address_sha256": _sha256("100.64.10.20"),
        "artifact": candidate.artifact.artifact,
        "artifact_revision": candidate.artifact.artifact_revision,
        "artifact_content_digest": _sha256("artifact"),
        "artifact_file_count": 12,
        "weight_bytes": candidate.artifact.weight_bytes,
        "dependency_lock_digest": _sha256("lock"),
        "sbom_digest": _sha256("sbom"),
        "quantization_recipe_digest": _sha256("recipe"),
        "calibration_dataset_digest": None,
    }
    values.update(updates)
    return Qwen4090HostEvidence.model_validate(values)


def _matrix_with_unpinned_candidate() -> Qwen4090CandidateMatrix:
    matrix = load_matrix(DEFAULT_MATRIX)
    candidate = next(item for item in matrix.candidates if item.candidate_id == CANDIDATE_ID)
    unpinned = candidate.model_copy(
        update={
            "artifact": candidate.artifact.model_copy(
                update={
                    "artifact_content_digest": None,
                    "quantization_recipe_digest": None,
                }
            ),
            "serving": candidate.serving.model_copy(
                update={"dependency_lock_digest": None, "sbom_digest": None}
            ),
        }
    )
    return matrix.model_copy(
        update={
            "candidates": tuple(
                unpinned if item.candidate_id == CANDIDATE_ID else item
                for item in matrix.candidates
            )
        }
    )


def test_complete_host_evidence_is_collected_but_not_claimed_ready_before_matrix_pinning() -> None:
    report = assess_qwen4090_host(
        _matrix_with_unpinned_candidate(),
        candidate_id=CANDIDATE_ID,
        evidence=_evidence(),
    )

    assert report.status is HostPreflightStatus.EVIDENCE_COLLECTED_NOT_PINNED
    assert report.strict_ready is False
    warning_codes = {
        item.reason_code for item in report.checks if item.status is HostCheckStatus.WARNING
    }
    assert warning_codes == {
        "ARTIFACT_CONTENT_DIGEST_NOT_PINNED",
        "DEPENDENCY_LOCK_DIGEST_NOT_PINNED",
        "SBOM_DIGEST_NOT_PINNED",
        "QUANTIZATION_RECIPE_DIGEST_NOT_PINNED",
    }


def test_pinned_package_with_only_undisclosed_calibration_is_shadow_ready_not_strict() -> None:
    matrix = load_matrix(DEFAULT_MATRIX)
    candidate = next(
        item for item in matrix.candidates if item.candidate_id == COMMUNITY_CANDIDATE_ID
    )

    report = assess_qwen4090_host(
        matrix,
        candidate_id=COMMUNITY_CANDIDATE_ID,
        evidence=_evidence(
            COMMUNITY_CANDIDATE_ID,
            artifact_content_digest=candidate.artifact.artifact_content_digest,
            dependency_lock_digest=candidate.serving.dependency_lock_digest,
            sbom_digest=candidate.serving.sbom_digest,
            quantization_recipe_digest=candidate.artifact.quantization_recipe_digest,
        ),
    )

    assert report.status is HostPreflightStatus.SHADOW_READY_PROVENANCE_INCOMPLETE
    assert report.strict_ready is False
    warning_codes = {
        item.reason_code for item in report.checks if item.status is HostCheckStatus.WARNING
    }
    assert warning_codes == {"CALIBRATION_DATASET_DIGEST_NOT_PINNED"}


def test_wrong_gpu_busy_host_and_public_bind_fail_independently() -> None:
    bad_gpu = RTX4090GpuHostEvidence(
        name="NVIDIA RTX 6000 Ada Generation",
        driver_version="580.65.06",
        compute_capability="8.9",
        total_vram_mib=49140,
        free_vram_mib=1000,
        uuid_sha256=_sha256("other-gpu"),
    )
    report = assess_qwen4090_host(
        load_matrix(DEFAULT_MATRIX),
        candidate_id=CANDIDATE_ID,
        evidence=_evidence(
            gpus=(bad_gpu,),
            active_compute_process_count=1,
            bind_address_is_tailscale=False,
        ),
    )

    assert report.status is HostPreflightStatus.FAIL
    failure_codes = {
        item.reason_code for item in report.checks if item.status is HostCheckStatus.FAIL
    }
    assert {
        "GPU_NAME_MISMATCH",
        "GPU_VRAM_PROFILE_MISMATCH",
        "GPU_FREE_VRAM_BELOW_PREFLIGHT_MINIMUM",
        "GPU_COMPUTE_PROCESS_ALREADY_ACTIVE",
        "PRIVATE_BIND_ADDRESS_INVALID",
    }.issubset(failure_codes)


def test_exactly_pinned_probe_is_strictly_ready() -> None:
    matrix = load_matrix(DEFAULT_MATRIX)
    evidence = _evidence()
    candidates = []
    for candidate in matrix.candidates:
        if candidate.candidate_id != CANDIDATE_ID:
            candidates.append(candidate)
            continue
        candidates.append(
            candidate.model_copy(
                update={
                    "artifact": candidate.artifact.model_copy(
                        update={
                            "artifact_content_digest": evidence.artifact_content_digest,
                            "quantization_recipe_digest": evidence.quantization_recipe_digest,
                            "calibration_dataset_digest": evidence.calibration_dataset_digest,
                        }
                    ),
                    "serving": candidate.serving.model_copy(
                        update={
                            "dependency_lock_digest": evidence.dependency_lock_digest,
                            "sbom_digest": evidence.sbom_digest,
                        }
                    ),
                }
            )
        )
    pinned_matrix = matrix.model_copy(update={"candidates": tuple(candidates)})

    report = assess_qwen4090_host(
        pinned_matrix,
        candidate_id=CANDIDATE_ID,
        evidence=evidence,
    )

    assert report.status is HostPreflightStatus.PASS
    assert report.strict_ready is True
    assert all(item.status is HostCheckStatus.PASS for item in report.checks)


def test_runtime_env_requires_owner_only_mode_and_a_non_placeholder_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.llm"
    env_file.write_text(
        "LLM_BIND_ADDRESS=100.64.10.20\n"
        "LLM_API_KEY=9Yp!4tJx6Qm2Nz8Bv7Kr5Ws3Hd1Lc0Ae\n"
        "LLM_MODEL_CACHE_DIR=/srv/csight/hf-cache\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)

    values, private = parse_private_env(env_file)

    assert private is True
    assert api_key_valid(values["LLM_API_KEY"]) is True
    assert api_key_valid("replace-with-a-long-random-secret") is False
    env_file.chmod(0o640)
    assert parse_private_env(env_file)[1] is False


def test_snapshot_digest_allows_hf_blob_links_but_rejects_escape(tmp_path: Path) -> None:
    revision = "2" * 40
    cache = tmp_path / "cache"
    blobs = cache / "hub/models--Qwen--Example/blobs"
    snapshot = cache / f"hub/models--Qwen--Example/snapshots/{revision}"
    blobs.mkdir(parents=True)
    snapshot.mkdir(parents=True)
    first = blobs / "first"
    second = blobs / "second"
    first.write_bytes(b"a" * 7)
    second.write_bytes(b"b" * 11)
    (snapshot / "model-00001-of-00002.safetensors").symlink_to(first)
    (snapshot / "model-00002-of-00002.safetensors").symlink_to(second)

    digest, file_count, weight_bytes = artifact_evidence(
        snapshot,
        cache_dir=cache,
        artifact="Qwen/Example",
        revision=revision,
    )

    assert digest.startswith("sha256:")
    assert file_count == 2
    assert weight_bytes == 18

    outside = tmp_path / "outside.safetensors"
    outside.write_bytes(b"unsafe")
    (snapshot / "escape.safetensors").symlink_to(outside)
    with pytest.raises(HostPreflightError, match="outside"):
        artifact_evidence(snapshot, cache_dir=cache, artifact="Qwen/Example", revision=revision)


def test_probe_cli_writes_immutable_privacy_safe_evidence_without_gpu(tmp_path: Path) -> None:
    probe = tmp_path / "probe.json"
    output = tmp_path / "evidence.json"
    matrix = tmp_path / "matrix.json"
    probe.write_text(_evidence().model_dump_json(), encoding="utf-8")
    matrix.write_text(_matrix_with_unpinned_candidate().model_dump_json(indent=2), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            os.fspath(SCRIPT),
            "--candidate-id",
            CANDIDATE_ID,
            "--matrix",
            os.fspath(matrix),
            "--probe",
            os.fspath(probe),
            "--output",
            os.fspath(output),
            "--collect-unpinned",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "EVIDENCE_COLLECTED_NOT_PINNED"
    assert stat_mode(output) == 0o600
    assert "GPU-private-id" not in completed.stdout + output.read_text(encoding="utf-8")

    replay = subprocess.run(
        [
            sys.executable,
            os.fspath(SCRIPT),
            "--candidate-id",
            CANDIDATE_ID,
            "--matrix",
            os.fspath(matrix),
            "--probe",
            os.fspath(probe),
            "--output",
            os.fspath(output),
            "--collect-unpinned",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert replay.returncode == 2
    assert "immutable" in replay.stdout


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_live_launcher_requires_strict_preflight_before_compose_start() -> None:
    launcher = LAUNCHER.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")

    assert launcher.index("scripts/preflight_qwen4090_host.py") < launcher.index("docker compose")
    assert "--collect-unpinned" not in launcher
    assert "--allow-shadow-provenance-incomplete" in launcher
    assert "QWEN4090_TOOLING_MODE" in launcher
    assert "run_qwen4090_host_preflight_container.sh" in launcher
    assert "${LLM_MODEL_CACHE_DIR:-qwen38-model-cache}:/model-cache" in compose


def test_container_preflight_sees_host_gpu_processes_and_never_pulls() -> None:
    runner = CONTAINER_PREFLIGHT.read_text(encoding="utf-8")

    assert "--pid host" in runner
    assert "--network host" in runner
    assert "--gpus all" in runner
    assert "-w /work" in runner
    assert "run --rm --pull=never" in runner
    assert "--allow-shadow-provenance-incomplete" in runner
    assert "LLM_API_KEY" not in runner


def test_package_documents_are_bound_to_runtime_and_artifact_identity(tmp_path: Path) -> None:
    candidate = next(
        item for item in load_matrix(DEFAULT_MATRIX).candidates if item.candidate_id == CANDIDATE_ID
    )
    sbom = tmp_path / "sbom.json"
    recipe = tmp_path / "recipe.json"
    calibration = tmp_path / "calibration.json"
    dataset_digest = _sha256("calibration-dataset")
    sbom.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "metadata": {"properties": [{"value": candidate.serving.runtime_image_digest}]},
            }
        ),
        encoding="utf-8",
    )
    recipe.write_text(
        json.dumps(
            {
                "artifact": candidate.artifact.artifact,
                "artifact_revision": candidate.artifact.artifact_revision,
                "format": "FP8_W8A8_BLOCK128_SAFE_TENSORS",
            }
        ),
        encoding="utf-8",
    )
    calibration.write_text(
        json.dumps(
            {
                "artifact": candidate.artifact.artifact,
                "artifact_revision": candidate.artifact.artifact_revision,
                "dataset_digest": dataset_digest,
            }
        ),
        encoding="utf-8",
    )

    assert sbom_digest(
        sbom,
        runtime_image_digest=candidate.serving.runtime_image_digest,
    ).startswith("sha256:")
    recipe_digest = quantization_recipe_digest(
        recipe,
        artifact=candidate.artifact.artifact,
        revision=candidate.artifact.artifact_revision,
    )
    assert recipe_digest is not None and recipe_digest.startswith("sha256:")
    assert (
        calibration_dataset_digest(
            calibration,
            artifact=candidate.artifact.artifact,
            revision=candidate.artifact.artifact_revision,
        )
        == dataset_digest
    )
    assert canonical_dependency_lock_digest("zeta==2\nalpha==1\n") == (
        canonical_dependency_lock_digest("alpha==1\nzeta==2\n")
    )

    bad_sbom = tmp_path / "bad-sbom.json"
    bad_sbom.write_text('{"bomFormat":"CycloneDX"}', encoding="utf-8")
    with pytest.raises(HostPreflightError, match="exact runtime image"):
        sbom_digest(bad_sbom, runtime_image_digest=candidate.serving.runtime_image_digest)
