"""Protected offline llama-imatrix maintenance contracts."""

import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from scripts.qwen4090_imatrix_maintenance import (
    ImatrixMaintenanceError,
    canonical_command_contract_digest,
    finalize_evidence,
    imatrix_command_contract,
    pinned_image_digest,
    validate_imatrix_gguf_header,
    validate_inputs,
    write_json_once,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "b" * 64
LLAMA_CPP_REVISION = "aee56b3abfeb134218fe5c496c329a1faac1ef28"


def _sha(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _private_file(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    path.chmod(0o600)


def _private_directory(path: Path) -> None:
    path.mkdir()
    path.chmod(0o700)


def _build_manifest() -> dict[str, object]:
    return {
        "schema_version": "csight_llama_cpp_build/1.0.0",
        "source_repository": "ggml-org/llama.cpp",
        "source_revision": LLAMA_CPP_REVISION,
        "dockerfile_digest": "sha256:" + "a" * 64,
        "tool_image_reference": None,
        "tool_image_digest": DIGEST,
        "runtime_image_reference": None,
        "runtime_image_digest": "sha256:" + "c" * 64,
        "runtime_binary_digest": "sha256:" + "d" * 64,
        "quantizer_binary_digest": "sha256:" + "e" * 64,
        "imatrix_binary_digest": "sha256:" + "f" * 64,
        "tokenizer_binary_digest": "sha256:" + "0" * 64,
        "cuda_architectures": ["89"],
        "cmake_options": {"GGML_CUDA": "ON"},
        "base_image_digests": {
            "cuda_devel": "sha256:" + "2" * 64,
            "cuda_runtime": "sha256:" + "3" * 64,
        },
        "sbom_tool_image": "anchore/syft@sha256:" + "4" * 64,
    }


def _imatrix_gguf() -> bytes:
    return struct.pack("<4sIQQ", b"GGUF", 3, 994, 12) + b"imatrix-payload"


def test_preflight_accepts_exact_local_image_id_and_owner_only_inputs(tmp_path: Path) -> None:
    q8 = tmp_path / "helper-q8.gguf"
    corpus = tmp_path / "calibration.txt"
    manifest = tmp_path / "build.json"
    output = tmp_path / "output"
    evidence = tmp_path / "evidence"
    _private_file(q8, b"q8-helper")
    _private_file(corpus, b"synthetic calibration corpus")
    _private_file(manifest, json.dumps(_build_manifest()).encode())
    _private_directory(output)
    _private_directory(evidence)

    result = validate_inputs(
        q8_helper=q8,
        expected_q8_digest=_sha(q8.read_bytes()),
        calibration_corpus=corpus,
        expected_corpus_digest=_sha(corpus.read_bytes()),
        build_manifest_path=manifest,
        expected_build_manifest_digest=_sha(manifest.read_bytes()),
        tool_image=DIGEST,
        output_root=output,
        evidence_root=evidence,
    )

    assert result["tool_image_digest"] == DIGEST
    assert result["network_mode"] == "NONE"
    command_contract = result["command_contract"]
    assert isinstance(command_contract, dict)
    assert command_contract == imatrix_command_contract()
    assert result["command_contract_digest"] == canonical_command_contract_digest(command_contract)
    assert pinned_image_digest(DIGEST) == DIGEST
    assert pinned_image_digest(f"csight/llama.cpp@{DIGEST}") == DIGEST


def test_preflight_rejects_tags_and_shared_calibration_input(tmp_path: Path) -> None:
    with pytest.raises(ImatrixMaintenanceError, match="exact local image ID"):
        pinned_image_digest("csight/llama.cpp:latest")
    corpus = tmp_path / "calibration.txt"
    q8 = tmp_path / "helper-q8.gguf"
    manifest = tmp_path / "build.json"
    output = tmp_path / "output"
    evidence = tmp_path / "evidence"
    _private_file(corpus, b"synthetic")
    _private_file(q8, b"q8")
    _private_file(manifest, json.dumps(_build_manifest()).encode())
    _private_directory(output)
    _private_directory(evidence)
    corpus.chmod(0o640)
    with pytest.raises(ImatrixMaintenanceError, match="no shared mode"):
        validate_inputs(
            q8_helper=q8,
            expected_q8_digest=_sha(b"q8"),
            calibration_corpus=corpus,
            expected_corpus_digest=_sha(b"synthetic"),
            build_manifest_path=manifest,
            expected_build_manifest_digest=_sha(manifest.read_bytes()),
            tool_image=DIGEST,
            output_root=output,
            evidence_root=evidence,
        )


def test_evidence_tool_is_standalone_and_shell_preserves_vlm(tmp_path: Path) -> None:
    python_script = ROOT / "scripts/qwen4090_imatrix_maintenance.py"
    shell_script = ROOT / "infra/llm/run_qwen4090_llama_imatrix_maintenance.sh"
    environment = {"PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        [sys.executable, "-I", str(python_script), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    source = shell_script.read_text(encoding="utf-8")
    preflight_position = source.index('"${evidence_tool}" preflight')
    backend_probe_position = source.index("backend_probe_output=", preflight_position)
    trap_position = source.index("trap cleanup_and_restore EXIT")
    stop_position = source.index('stop "${vlm_service}"', trap_position)
    memory_position = source.index('mem_available_kib="$', stop_position)
    run_position = source.index('docker run --name "${container_name}"', memory_position)
    assert (
        preflight_position
        < backend_probe_position
        < trap_position
        < stop_position
        < memory_position
        < run_position
    )
    assert '--entrypoint /app/llama-imatrix "${tool_image}" --list-devices' in source
    assert 'grep -Fq "Available devices:"' in source
    assert "'^  CUDA[0-9]+:'" in source
    assert "--network none" in source
    assert "--cpus 16 --memory 56g --memory-swap 56g" in source
    assert "--threads 16" in source and "--threads-batch 16" in source
    assert "--n-gpu-layers auto" in source
    assert "--n-gpu-layers all" not in source
    assert "/app/llama-imatrix" in source
    assert "LLAMA_IMATRIX_CHUNKS:--1" in source
    assert "--process-output" in source
    assert "--output-frequency 1000000 --save-frequency 0" in source
    assert "--output-file /output/qwen38-27b-imatrix.gguf" in source
    assert "--flash-attn on" in source
    assert '--context-size "${context_size}"' in source
    assert '--batch-size "${batch_size}"' in source
    assert '--ubatch-size "${ubatch_size}"' in source
    assert '--chunks "${chunks}"' in source
    assert "LLAMA_CPP_BUILD_MANIFEST_DIGEST" in source
    assert "--build-manifest-digest" in source
    assert source.index('docker rm --force "${container_name}"') < source.index(
        '"${vlm_compose[@]}" up --detach --wait'
    )
    assert source.index('chmod 600 "${output_file}"') < source.index('"${evidence_tool}" finalize')
    subprocess.run(["bash", "-n", str(shell_script)], check=True)


def test_final_evidence_binds_canonical_b10419_command_contract(tmp_path: Path) -> None:
    q8 = tmp_path / "helper-q8.gguf"
    corpus = tmp_path / "calibration.txt"
    manifest = tmp_path / "build.json"
    output_root = tmp_path / "output-root"
    evidence_root = tmp_path / "evidence-root"
    _private_file(q8, b"q8-helper")
    _private_file(corpus, b"synthetic calibration corpus")
    _private_file(manifest, json.dumps(_build_manifest()).encode())
    _private_directory(output_root)
    _private_directory(evidence_root)
    preflight = validate_inputs(
        q8_helper=q8,
        expected_q8_digest=_sha(q8.read_bytes()),
        calibration_corpus=corpus,
        expected_corpus_digest=_sha(corpus.read_bytes()),
        build_manifest_path=manifest,
        expected_build_manifest_digest=_sha(manifest.read_bytes()),
        tool_image=DIGEST,
        output_root=output_root,
        evidence_root=evidence_root,
    )
    preflight_file = evidence_root / "preflight.json"
    log_file = evidence_root / "llama-imatrix.log"
    output_file = output_root / "qwen38-27b-imatrix.gguf"
    evidence_file = evidence_root / "evidence.json"
    write_json_once(preflight_file, preflight)
    _private_file(log_file, b"completed")
    _private_file(output_file, _imatrix_gguf())

    evidence = finalize_evidence(
        preflight_report=preflight_file,
        output_file=output_file,
        log_file=log_file,
        evidence_file=evidence_file,
        run_exit_code=0,
        vlm_restored=True,
        started_at="2026-08-31T12:00:00Z",
        finished_at="2026-08-31T12:10:00Z",
        context_size=512,
        batch_size=512,
        ubatch_size=128,
        chunks=-1,
    )

    assert evidence["schema_version"] == "qwen4090_imatrix_run_evidence/1.1.0"
    assert evidence["status"] == "PASS"
    assert evidence["imatrix_gguf"] == {
        "valid": True,
        "version": 3,
        "tensor_count": 994,
        "metadata_count": 12,
    }
    assert evidence["command_contract"] == imatrix_command_contract()
    assert evidence["command_contract_digest"] == preflight["command_contract_digest"]
    assert evidence["output_file_argument"] == "/output/qwen38-27b-imatrix.gguf"
    assert evidence["context_size"] == 512
    assert evidence["batch_size"] == 512
    assert evidence["ubatch_size"] == 128
    assert evidence["gpu_layers"] == "auto"
    assert evidence["threads"] == 16
    assert evidence["threads_batch"] == 16
    assert evidence["chunks"] == -1
    assert evidence["output_frequency"] == 1_000_000
    assert evidence["save_frequency"] == 0
    assert evidence["process_output"] is True
    assert evidence["no_ppl"] is True
    assert evidence["parse_special"] is True
    assert evidence["flash_attention"] == "on"


def test_finalize_records_fail_for_non_gguf_output(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence-root"
    output_root = tmp_path / "output-root"
    _private_directory(evidence_root)
    _private_directory(output_root)
    preflight: dict[str, object] = {
        "schema_version": "qwen4090_imatrix_preflight/1.0.0",
        "q8_helper_digest": _sha(b"q8"),
        "calibration_corpus_digest": _sha(b"corpus"),
        "llama_cpp_revision": LLAMA_CPP_REVISION,
        "build_manifest_digest": _sha(b"manifest"),
        "tool_image_digest": DIGEST,
        "imatrix_binary_digest": "sha256:" + "f" * 64,
    }
    preflight_file = evidence_root / "preflight.json"
    log_file = evidence_root / "llama-imatrix.log"
    output_file = output_root / "qwen38-27b-imatrix.gguf"
    evidence_file = evidence_root / "evidence.json"
    write_json_once(preflight_file, preflight)
    _private_file(log_file, b"process returned zero")
    _private_file(output_file, b"not a gguf output")

    evidence = finalize_evidence(
        preflight_report=preflight_file,
        output_file=output_file,
        log_file=log_file,
        evidence_file=evidence_file,
        run_exit_code=0,
        vlm_restored=True,
        started_at="2026-08-31T12:00:00Z",
        finished_at="2026-08-31T12:10:00Z",
        context_size=512,
        batch_size=512,
        ubatch_size=128,
        chunks=-1,
    )

    assert evidence["status"] == "FAIL"
    gguf_evidence = cast(dict[str, object], evidence["imatrix_gguf"])
    assert gguf_evidence["valid"] is False
    assert validate_imatrix_gguf_header(output_file)["valid"] is False


def test_finalize_rejects_tampered_preflight_command_contract(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence-root"
    output_root = tmp_path / "output-root"
    _private_directory(evidence_root)
    _private_directory(output_root)
    contract = imatrix_command_contract()
    contract["threads"] = 8
    preflight: dict[str, object] = {
        "schema_version": "qwen4090_imatrix_preflight/1.1.0",
        "q8_helper_digest": _sha(b"q8"),
        "calibration_corpus_digest": _sha(b"corpus"),
        "llama_cpp_revision": LLAMA_CPP_REVISION,
        "build_manifest_digest": _sha(b"manifest"),
        "tool_image_digest": DIGEST,
        "imatrix_binary_digest": "sha256:" + "f" * 64,
        "command_contract": contract,
        "command_contract_digest": canonical_command_contract_digest(contract),
    }
    preflight_file = evidence_root / "preflight.json"
    log_file = evidence_root / "llama-imatrix.log"
    output_file = output_root / "qwen38-27b-imatrix.gguf"
    write_json_once(preflight_file, preflight)
    _private_file(log_file, b"failed")

    with pytest.raises(ImatrixMaintenanceError, match="preflight command contract"):
        finalize_evidence(
            preflight_report=preflight_file,
            output_file=output_file,
            log_file=log_file,
            evidence_file=evidence_root / "evidence.json",
            run_exit_code=75,
            vlm_restored=True,
            started_at="2026-08-31T12:00:00Z",
            finished_at="2026-08-31T12:00:01Z",
            context_size=512,
            batch_size=512,
            ubatch_size=128,
            chunks=-1,
        )


def test_preflight_rejects_unpinned_manifest_digest_or_wrong_llama_revision(
    tmp_path: Path,
) -> None:
    q8 = tmp_path / "helper-q8.gguf"
    corpus = tmp_path / "calibration.txt"
    manifest = tmp_path / "build.json"
    output = tmp_path / "output"
    evidence = tmp_path / "evidence"
    _private_file(q8, b"q8")
    _private_file(corpus, b"synthetic")
    _private_file(manifest, json.dumps(_build_manifest()).encode())
    _private_directory(output)
    _private_directory(evidence)

    with pytest.raises(ImatrixMaintenanceError, match="manifest digest"):
        validate_inputs(
            q8_helper=q8,
            expected_q8_digest=_sha(q8.read_bytes()),
            calibration_corpus=corpus,
            expected_corpus_digest=_sha(corpus.read_bytes()),
            build_manifest_path=manifest,
            expected_build_manifest_digest="sha256:" + "9" * 64,
            tool_image=DIGEST,
            output_root=output,
            evidence_root=evidence,
        )

    wrong = _build_manifest()
    wrong["source_revision"] = "1" * 40
    _private_file(manifest, json.dumps(wrong).encode())
    with pytest.raises(ImatrixMaintenanceError, match="build manifest is invalid"):
        validate_inputs(
            q8_helper=q8,
            expected_q8_digest=_sha(q8.read_bytes()),
            calibration_corpus=corpus,
            expected_corpus_digest=_sha(corpus.read_bytes()),
            build_manifest_path=manifest,
            expected_build_manifest_digest=_sha(manifest.read_bytes()),
            tool_image=DIGEST,
            output_root=output,
            evidence_root=evidence,
        )
