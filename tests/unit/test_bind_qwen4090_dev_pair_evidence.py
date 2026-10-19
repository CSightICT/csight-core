"""Fail-closed evidence binding for the local RTX 4090 GGUF Dev pair."""

from __future__ import annotations

import hashlib
import json
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from app.platform.quantization_assets import (
    LLAMA_CPP_B10419_REVISION,
    FinalCandidateSet,
    LlamaCppQuantizationRunPaths,
    QuantizationRecipeName,
    TensorInfo,
    TensorInventory,
    compile_llama_cpp_b10419_final_run_plan,
    compile_quantization_recipe,
    render_llama_cpp_tensor_type_file,
)
from app.platform.qwen4090_gguf import CandidateReleaseStatusV2, assess_gguf_matrix
from scripts.bind_qwen4090_dev_pair_evidence import (
    MatrixBindingError,
    atomic_compare_and_replace,
    bind_evidence,
    main,
)
from scripts.qwen4090_imatrix_maintenance import (
    canonical_command_contract_digest,
    imatrix_command_contract,
)
from scripts.verify_qwen4090_gguf_candidates import DEFAULT_MATRIX, load_gguf_matrix

pytestmark = pytest.mark.unit
RUNTIME_IMAGE_REFERENCE = "csight/llama.cpp:b10419-cuda12.8.1-csight-test"


def _sha(value: bytes | str) -> str:
    content = value.encode() if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _write_json(path: Path, value: object) -> bytes:
    content = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(content)
    return content


def _inventory(source_digest: str) -> TensorInventory:
    tensors = [
        TensorInfo(name="token_embd.weight", shape=(16, 16), dtype="F16", n_bytes=512),
        TensorInfo(name="output_norm.weight", shape=(16,), dtype="F32", n_bytes=64),
        TensorInfo(name="output.weight", shape=(16, 16), dtype="F16", n_bytes=512),
    ]
    for block in range(64):
        for suffix in ("ffn_gate.weight", "ffn_up.weight", "ffn_down.weight"):
            tensors.append(
                TensorInfo(
                    name=f"blk.{block}.{suffix}",
                    shape=(16, 16),
                    dtype="F16",
                    n_bytes=512,
                )
            )
        attention = (
            ("attn_q.weight", "attn_k.weight", "attn_v.weight", "attn_output.weight")
            if block % 4 == 3
            else ("attn_qkv.weight", "attn_gate.weight", "ssm_out.weight")
        )
        for suffix in attention:
            tensors.append(
                TensorInfo(
                    name=f"blk.{block}.{suffix}",
                    shape=(16, 16),
                    dtype="F16",
                    n_bytes=512,
                )
            )
    return TensorInventory(source_gguf_digest=source_digest, tensors=tuple(tensors))


@dataclass(frozen=True)
class EvidenceBundle:
    matrix: Path
    plan: Path
    pair: Path
    imatrix: Path
    build: Path
    sbom: Path
    q4_digest: str
    q5_digest: str
    imatrix_digest: str
    build_digest: str
    runtime_digest: str


def _bundle(tmp_path: Path) -> EvidenceBundle:
    tmp_path.mkdir(parents=True, exist_ok=True)
    matrix = tmp_path / "matrix.json"
    matrix.write_bytes(DEFAULT_MATRIX.read_bytes())
    current = load_gguf_matrix(matrix)
    source_digest = cast(str, current.candidates[0].artifact.base_artifact_content_digest)
    corpus_digest = cast(str, current.candidates[0].artifact.calibration_dataset_digest)
    calibration_manifest_digest = cast(
        str, current.candidates[0].artifact.calibration_manifest_digest
    )
    helper_digest = _sha("new-q8-helper")
    imatrix_digest = _sha("new-clean-imatrix")
    quantizer_digest = _sha("new-quantizer")
    imatrix_binary_digest = _sha("new-imatrix-binary")
    runtime_digest = _sha("new-runtime-image")
    q4_digest = _sha("new-mixed-q4-q6")
    q5_digest = _sha("new-q5")

    inventory = _inventory(source_digest)
    recipes = tuple(
        compile_quantization_recipe(
            name=name,
            inventory=inventory,
            llama_cpp_revision=LLAMA_CPP_B10419_REVISION,
            calibration_manifest_digest=calibration_manifest_digest,
            calibration_helper_q8_digest=helper_digest,
            imatrix_digest=imatrix_digest,
        )
        for name in (
            QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
            QuantizationRecipeName.Q5_K_S_IMATRIX,
        )
    )
    paths = LlamaCppQuantizationRunPaths(
        quantize_binary="/app/llama-quantize",
        imatrix_binary="/app/llama-imatrix",
        source_bf16_gguf="/private/source/Qwen3.8-27B-BF16.gguf",
        calibration_text="/private/corpus/calibration.txt",
        q8_helper_gguf="/private/calibration/helper-q8.gguf",
        imatrix_gguf="/private/calibration/clean.imatrix.gguf",
        q4_k_m_control_gguf="/private/output/control.gguf",
        q4_k_m_imatrix_gguf="/private/output/imatrix-q4.gguf",
        q4_k_m_csight_mixed_gguf=("/private/output/Qwen3.8-27B-CSight-Q4_K_M.gguf"),
        q5_k_s_imatrix_gguf="/private/output/Qwen3.8-27B-CSight-Q5_K_S.gguf",
        mixed_tensor_type_file="/private/recipes/mixed.txt",
    )
    tensor_file_digest = _sha(render_llama_cpp_tensor_type_file(recipes[0]))
    run_plan = compile_llama_cpp_b10419_final_run_plan(
        paths=paths,
        recipes=recipes,
        calibration_text_digest=corpus_digest,
        quantize_binary_digest=quantizer_digest,
        imatrix_binary_digest=imatrix_binary_digest,
        mixed_tensor_type_file_digest=tensor_file_digest,
        threads=16,
        expected_output_digests={
            QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED: q4_digest,
            QuantizationRecipeName.Q5_K_S_IMATRIX: q5_digest,
        },
        final_candidate_set=FinalCandidateSet.DEV_QUALIFICATION_PAIR,
    )
    plan = tmp_path / "pair-plan.json"
    _write_json(plan, run_plan.model_dump(mode="json"))

    tool_digest = _sha("new-unified-image")
    build = tmp_path / "build.json"
    build_content = _write_json(
        build,
        {
            "schema_version": "csight_llama_cpp_build/1.0.0",
            "source_repository": "ggml-org/llama.cpp",
            "source_revision": LLAMA_CPP_B10419_REVISION,
            "dockerfile_digest": _sha("dockerfile"),
            "tool_image_digest": tool_digest,
            "runtime_image_digest": runtime_digest,
            "runtime_binary_digest": _sha("llama-server"),
            "quantizer_binary_digest": quantizer_digest,
            "imatrix_binary_digest": imatrix_binary_digest,
            "tokenizer_binary_digest": _sha("llama-tokenize"),
            "cuda_architectures": ["89"],
            "cmake_options": {"GGML_CUDA": "ON", "CMAKE_BUILD_TYPE": "Release"},
            "base_image_digests": {
                "cuda_devel": _sha("cuda-devel"),
                "cuda_runtime": _sha("cuda-runtime"),
            },
            "sbom_tool_image": "anchore/syft:v1@" + _sha("syft"),
        },
    )
    build_digest = _sha(build_content)

    command_contract = imatrix_command_contract()
    imatrix = tmp_path / "imatrix.json"
    _write_json(
        imatrix,
        {
            "schema_version": "qwen4090_imatrix_run_evidence/1.1.0",
            "status": "PASS",
            "run_exit_code": 0,
            "vlm_restored": True,
            "started_at": "2026-09-01T01:00:00Z",
            "finished_at": "2026-09-01T02:00:00Z",
            "q8_helper_digest": helper_digest,
            "calibration_corpus_digest": corpus_digest,
            "llama_cpp_revision": LLAMA_CPP_B10419_REVISION,
            "build_manifest_digest": build_digest,
            "tool_image_digest": tool_digest,
            "imatrix_binary_digest": imatrix_binary_digest,
            "imatrix_digest": imatrix_digest,
            "imatrix_bytes": 13_000_000,
            "imatrix_gguf": {
                "valid": True,
                "version": 3,
                "tensor_count": 994,
                "metadata_count": 12,
            },
            "log_digest": _sha("imatrix-log"),
            "log_bytes": 1024,
            "command_contract": command_contract,
            "command_contract_digest": canonical_command_contract_digest(command_contract),
            "output_file_argument": "/output/qwen38-27b-imatrix.gguf",
            "context_size": 512,
            "batch_size": 512,
            "ubatch_size": 128,
            "gpu_layers": "auto",
            "threads": 16,
            "threads_batch": 16,
            "chunks": -1,
            "output_frequency": 1_000_000,
            "save_frequency": 0,
            "process_output": True,
            "no_ppl": True,
            "flash_attention": "on",
            "network_mode": "NONE",
            "output_format": "GGUF",
            "parse_special": True,
            "perplexity_computed": False,
            "test_data_used": False,
        },
    )

    pair = tmp_path / "pair.json"
    pair_commands: list[dict[str, Any]] = []
    command_bytes = {1: 19_300_000_000, 2: 18_700_000_000}
    for command in run_plan.commands:
        pair_commands.append(
            {
                "order": command.order,
                "operation": command.operation,
                "recipe_name": command.recipe_name,
                "recipe_digest": command.recipe_digest,
                "output_name": Path(command.output_path).name,
                "output_digest": cast(str, command.expected_output_digest),
                "output_bytes": command_bytes[command.order],
                "execution": "EXECUTED",
            }
        )
    _write_json(
        pair,
        {
            "schema_version": "llama_cpp_quantization_run_evidence/1.1.0",
            "status": "PASS",
            "execution_mode": "DOCKER_OFFLINE",
            "phase": "FINAL_CANDIDATES",
            "plan_digest": run_plan.plan_digest,
            "llama_cpp_revision": LLAMA_CPP_B10419_REVISION,
            "tool_image_id": tool_digest,
            "quantize_binary_path": "/app/llama-quantize",
            "quantize_binary_digest": quantizer_digest,
            "docker_limits": {
                "cpus": "16",
                "memory": "56g",
                "memory_swap": "56g",
                "pids": "1024",
                "network": "NONE",
                "root_filesystem": "READ_ONLY",
                "gpu_devices": "NONE",
                "pull": "NEVER",
                "uid": 1000,
                "gid": 1000,
            },
            "commands": pair_commands,
            "all_host_inputs_reverified_after_execution": True,
            "final_candidates_from_bf16": True,
            "q8_helper_used_as_final_source": False,
            "sealed_test_data_used": False,
            "shell_interpolation_used": False,
        },
    )

    sbom = tmp_path / "sbom.json"
    _write_json(
        sbom,
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "metadata": {
                "properties": [
                    {"name": "runtime_image_digest", "value": runtime_digest},
                ]
            },
        },
    )
    return EvidenceBundle(
        matrix=matrix,
        plan=plan,
        pair=pair,
        imatrix=imatrix,
        build=build,
        sbom=sbom,
        q4_digest=q4_digest,
        q5_digest=q5_digest,
        imatrix_digest=imatrix_digest,
        build_digest=build_digest,
        runtime_digest=runtime_digest,
    )


def _bind(bundle: EvidenceBundle) -> tuple[bytes, dict[str, object]]:
    return bind_evidence(
        matrix_path=bundle.matrix,
        run_plan_path=bundle.plan,
        pair_evidence_path=bundle.pair,
        imatrix_evidence_path=bundle.imatrix,
        build_manifest_path=bundle.build,
        sbom_path=bundle.sbom,
        runtime_image_reference=RUNTIME_IMAGE_REFERENCE,
        recorded_at="2026-09-01T03:00:00Z",
    )


def test_binder_updates_only_dev_content_and_runtime_identity(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    before = bundle.matrix.read_bytes()

    proposed, report = _bind(bundle)

    assert bundle.matrix.read_bytes() == before
    path = tmp_path / "proposed.json"
    path.write_bytes(proposed)
    matrix = load_gguf_matrix(path)
    assert report["release_status"] == "NO_RELEASE_ELIGIBLE"
    assert report["runtime_image_reference"] == RUNTIME_IMAGE_REFERENCE
    assert report["build_manifest_digest"] == bundle.build_digest
    expected_digests = {
        "qwen38-27b-csight-q4-k-m-llama-cpp": bundle.q4_digest,
        "qwen38-27b-csight-q5-k-s-llama-cpp": bundle.q5_digest,
    }
    for candidate in matrix.candidates:
        assert candidate.artifact.artifact_revision is None
        assert candidate.qualification is None
        assert (
            candidate.artifact.artifact_content_digest == expected_digests[candidate.candidate_id]
        )
        assert candidate.artifact.importance_matrix_digest == bundle.imatrix_digest
        assert candidate.serving.runtime_image == RUNTIME_IMAGE_REFERENCE
        assert candidate.serving.runtime_image_digest == bundle.runtime_digest
    assert all(
        assessment.status is CandidateReleaseStatusV2.PENDING_QUALIFICATION
        and assessment.reason_codes
        == ("ARTIFACT_REVISION_UNPINNED", "ORG_OWNED_ARTIFACT_MIRROR_REQUIRED")
        for assessment in assess_gguf_matrix(matrix)
    )
    allowed_suffixes = {
        "recorded_at",
        "artifact_content_digest",
        "weight_bytes",
        "quantization_recipe_digest",
        "importance_matrix_digest",
        "quantizer_binary_digest",
        "runtime_image",
        "runtime_image_digest",
        "llama_cpp_revision",
        "runtime_binary_digest",
        "runtime_build_manifest_digest",
        "sbom_digest",
    }
    assert {
        str(path).rsplit("/", 1)[-1] for path in cast(tuple[str, ...], report["changed_fields"])
    } <= (allowed_suffixes)


def test_binder_rejects_a_pair_not_bound_to_the_clean_imatrix(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    document = json.loads(bundle.imatrix.read_bytes())
    document["imatrix_digest"] = _sha("different-imatrix")
    _write_json(bundle.imatrix, document)

    with pytest.raises(MatrixBindingError, match="consume the clean imatrix"):
        _bind(bundle)


def test_binder_rejects_recipe_or_sbom_runtime_identity_drift(tmp_path: Path) -> None:
    recipe_bundle = _bundle(tmp_path / "recipe")
    pair = json.loads(recipe_bundle.pair.read_bytes())
    pair["commands"][0]["recipe_name"] = "Q4_K_M_IMATRIX"
    _write_json(recipe_bundle.pair, pair)
    with pytest.raises(MatrixBindingError, match="command, recipe, or output"):
        _bind(recipe_bundle)

    sbom_bundle = _bundle(tmp_path / "sbom")
    _write_json(
        sbom_bundle.sbom,
        {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []},
    )
    with pytest.raises(MatrixBindingError, match="exact runtime image digest"):
        _bind(sbom_bundle)


def test_atomic_write_requires_checked_digest_and_preserves_mode(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    proposed, _ = _bind(bundle)
    bundle.matrix.chmod(0o640)

    with pytest.raises(MatrixBindingError, match="changed after check"):
        atomic_compare_and_replace(
            bundle.matrix,
            expected_file_digest=_sha("wrong"),
            content=proposed,
        )
    expected = _sha(bundle.matrix.read_bytes())
    assert (
        atomic_compare_and_replace(
            bundle.matrix,
            expected_file_digest=expected,
            content=proposed,
        )
        == "WRITTEN"
    )
    assert bundle.matrix.read_bytes() == proposed
    assert stat.S_IMODE(bundle.matrix.stat().st_mode) == 0o640
    assert (
        atomic_compare_and_replace(
            bundle.matrix,
            expected_file_digest=_sha(proposed),
            content=proposed,
        )
        == "ALREADY_BOUND"
    )


def test_cli_check_is_read_only_and_write_requires_explicit_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle(tmp_path)
    before = bundle.matrix.read_bytes()
    common = [
        "bind_qwen4090_dev_pair_evidence.py",
        "--matrix",
        str(bundle.matrix),
        "--run-plan",
        str(bundle.plan),
        "--pair-evidence",
        str(bundle.pair),
        "--imatrix-evidence",
        str(bundle.imatrix),
        "--build-manifest",
        str(bundle.build),
        "--sbom",
        str(bundle.sbom),
        "--runtime-image-reference",
        RUNTIME_IMAGE_REFERENCE,
        "--recorded-at",
        "2026-09-01T03:00:00Z",
    ]

    monkeypatch.setattr(sys, "argv", [*common, "--check"])
    assert main() == 0
    assert bundle.matrix.read_bytes() == before

    monkeypatch.setattr(
        sys,
        "argv",
        [
            *common,
            "--write",
            "--expected-matrix-file-digest",
            _sha(before),
        ],
    )
    assert main() == 2
    assert bundle.matrix.read_bytes() == before
