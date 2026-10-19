from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from app.platform.quantization_assets import (
    LLAMA_CPP_B10419_REVISION,
    FinalCandidateSet,
    LlamaCppQuantizationRunPaths,
    LlamaCppQuantizationRunPlan,
    QuantizationAssetError,
    QuantizationRecipeName,
    TensorInfo,
    TensorInventory,
    compile_llama_cpp_b10419_calibration_run_plan,
    compile_llama_cpp_b10419_final_run_plan,
    compile_quantization_recipe,
    render_llama_cpp_tensor_type_file,
)
from scripts.compile_qwen38_quantization_recipes import (
    build_expected_final_output_digests,
    build_run_paths,
    require_run_plan_arguments,
    serialize_run_plan,
    validate_digest_arguments,
)
from scripts.compile_qwen38_quantization_recipes import main as compile_recipes_main
from scripts.run_qwen38_quantization_plan import (
    execute_final_run_plan_in_docker,
    execute_run_plan,
)

pytestmark = pytest.mark.unit


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _arguments(*, helper: str | None, emit: bool) -> argparse.Namespace:
    return argparse.Namespace(
        calibration_manifest_digest=None,
        helper_q8_digest=helper,
        imatrix_digest=None,
        emit_run_plans=emit,
    )


def _inventory(source_digest: str) -> TensorInventory:
    tensors = [
        TensorInfo(name="token_embd.weight", shape=(100, 64), dtype="F16", n_bytes=12800),
        TensorInfo(name="output_norm.weight", shape=(64,), dtype="F32", n_bytes=256),
        TensorInfo(name="output.weight", shape=(100, 64), dtype="F16", n_bytes=12800),
    ]
    for block in range(64):
        for suffix in ("ffn_gate.weight", "ffn_up.weight", "ffn_down.weight"):
            tensors.append(
                TensorInfo(
                    name=f"blk.{block}.{suffix}",
                    shape=(64, 64),
                    dtype="F16",
                    n_bytes=8192,
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
                    shape=(64, 64),
                    dtype="F16",
                    n_bytes=8192,
                )
            )
    return TensorInventory(source_gguf_digest=source_digest, tensors=tuple(tensors))


def _docker_final_plan(
    tmp_path: Path,
    *,
    reusable_control: bool,
    final_candidate_set: FinalCandidateSet = FinalCandidateSet.FOUR_WAY_COMPARISON,
) -> tuple[LlamaCppQuantizationRunPlan, LlamaCppQuantizationRunPaths, str]:
    source_dir = tmp_path / "source"
    corpus_dir = tmp_path / "corpus"
    work_dir = tmp_path / "work"
    output_dir = tmp_path / "output"
    evidence_dir = tmp_path / "evidence"
    recipe_dir = tmp_path / "recipes"
    for directory in (
        source_dir,
        corpus_dir,
        work_dir,
        output_dir,
        evidence_dir,
        recipe_dir,
    ):
        directory.mkdir(mode=0o700, parents=True)
    source = source_dir / "Qwen3.8-27B-BF16.gguf"
    corpus = corpus_dir / "calibration.txt"
    imatrix = work_dir / "calibration.imatrix.gguf"
    source.write_bytes(b"exact bf16 source")
    corpus.write_bytes(b"screened synthetic calibration")
    imatrix.write_bytes(b"exact importance matrix")
    paths = LlamaCppQuantizationRunPaths(
        quantize_binary="/app/llama-quantize",
        imatrix_binary="/app/llama-imatrix",
        source_bf16_gguf=str(source),
        calibration_text=str(corpus),
        q8_helper_gguf=str(work_dir / "helper.gguf"),
        imatrix_gguf=str(imatrix),
        q4_k_m_control_gguf=str(output_dir / "control.gguf"),
        q4_k_m_imatrix_gguf=str(output_dir / "q4-imatrix.gguf"),
        q4_k_m_csight_mixed_gguf=str(output_dir / "mixed.gguf"),
        q5_k_s_imatrix_gguf=str(output_dir / "q5.gguf"),
        mixed_tensor_type_file=str(recipe_dir / "mixed.txt"),
    )
    inventory = _inventory(_digest(source))
    calibration_manifest_digest = "sha256:" + "a" * 64
    helper_digest = "sha256:" + "b" * 64
    recipes = []
    for name in QuantizationRecipeName:
        recipes.append(
            compile_quantization_recipe(
                name=name,
                inventory=inventory,
                llama_cpp_revision=LLAMA_CPP_B10419_REVISION,
                calibration_manifest_digest=(
                    None
                    if name is QuantizationRecipeName.Q4_K_M_CONTROL
                    else calibration_manifest_digest
                ),
                calibration_helper_q8_digest=(
                    None if name is QuantizationRecipeName.Q4_K_M_CONTROL else helper_digest
                ),
                imatrix_digest=(
                    None if name is QuantizationRecipeName.Q4_K_M_CONTROL else _digest(imatrix)
                ),
            )
        )
    tensor_text = render_llama_cpp_tensor_type_file(recipes[2])
    tensor_file = Path(paths.mixed_tensor_type_file)
    tensor_file.write_text(tensor_text, encoding="utf-8")
    expected_outputs = None
    if reusable_control:
        control = Path(paths.q4_k_m_control_gguf)
        control.write_bytes(b"verified existing control")
        expected_outputs = {QuantizationRecipeName.Q4_K_M_CONTROL: _digest(control)}
    quantize_digest = "sha256:" + "c" * 64
    selected_recipes = (
        recipes
        if final_candidate_set is FinalCandidateSet.FOUR_WAY_COMPARISON
        else [
            item
            for item in recipes
            if item.recipe_name
            in {
                QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
                QuantizationRecipeName.Q5_K_S_IMATRIX,
            }
        ]
    )
    plan = compile_llama_cpp_b10419_final_run_plan(
        paths=paths,
        recipes=selected_recipes,
        calibration_text_digest=_digest(corpus),
        quantize_binary_digest=quantize_digest,
        imatrix_binary_digest="sha256:" + "d" * 64,
        mixed_tensor_type_file_digest=_digest(tensor_file),
        threads=16,
        expected_output_digests=expected_outputs,
        final_candidate_set=final_candidate_set,
    )
    return plan, paths, quantize_digest


def test_helper_only_digest_is_limited_to_resumable_calibration_plan() -> None:
    digest = "sha256:" + "a" * 64
    assert validate_digest_arguments(_arguments(helper=digest, emit=True)) is False
    with pytest.raises(QuantizationAssetError, match="helper-only"):
        validate_digest_arguments(_arguments(helper=digest, emit=False))


def test_compiler_paths_match_approved_live_artifact_names(tmp_path: Path) -> None:
    imatrix_path = tmp_path / "calibration/Qwen3.8-27B-CSight-calibration.imatrix.gguf"
    arguments = argparse.Namespace(
        artifact_output_dir=tmp_path / "artifacts",
        imatrix_path=imatrix_path,
        quantize_binary_path=tmp_path / "bin/llama-quantize",
        imatrix_binary_path=tmp_path / "bin/llama-imatrix",
        source_bf16_path=tmp_path / "source/Qwen3.8-27B-BF16.gguf",
        calibration_text_path=tmp_path / "corpus/calibration.txt",
    )
    paths = build_run_paths(arguments, tmp_path / "recipes")

    assert Path(paths.q8_helper_gguf).name == ("Qwen3.8-27B-CSight-Q8_0-imatrix-helper.gguf")
    assert Path(paths.q4_k_m_control_gguf).name == ("Qwen3.8-27B-CSight-Q4_K_M-control.gguf")
    assert Path(paths.imatrix_gguf) == imatrix_path.absolute()


def test_compiler_rejects_final_imatrix_inside_writable_output(tmp_path: Path) -> None:
    output = tmp_path / "output"
    arguments = argparse.Namespace(
        artifact_output_dir=output,
        imatrix_path=output / "calibration.imatrix.gguf",
        source_bf16_path=tmp_path / "source.gguf",
        calibration_text_path=tmp_path / "calibration.txt",
        calibration_text_digest="sha256:" + "a" * 64,
        quantize_binary_path=Path("/app/llama-quantize"),
        quantize_binary_digest="sha256:" + "b" * 64,
        imatrix_binary_path=Path("/app/llama-imatrix"),
        imatrix_binary_digest="sha256:" + "c" * 64,
        llama_cpp_revision=LLAMA_CPP_B10419_REVISION,
    )

    with pytest.raises(QuantizationAssetError, match="outside the writable"):
        require_run_plan_arguments(arguments, final_inputs_ready=True)


def test_compiler_maps_only_supplied_resume_output_digests() -> None:
    control_digest = "sha256:" + "a" * 64
    arguments = argparse.Namespace(
        expected_q4_k_m_control_digest=control_digest,
        expected_q4_k_m_imatrix_digest=None,
        expected_q4_k_m_csight_mixed_digest=None,
        expected_q5_k_s_imatrix_digest=None,
    )

    assert build_expected_final_output_digests(arguments) == {
        QuantizationRecipeName.Q4_K_M_CONTROL: control_digest
    }


def test_run_plan_serialization_preserves_v1_and_emits_v1_1_candidate_set(
    tmp_path: Path,
) -> None:
    legacy, _, _ = _docker_final_plan(tmp_path / "legacy", reusable_control=False)
    pair, _, _ = _docker_final_plan(
        tmp_path / "pair",
        reusable_control=False,
        final_candidate_set=FinalCandidateSet.DEV_QUALIFICATION_PAIR,
    )

    assert "final_candidate_set" not in serialize_run_plan(legacy)
    assert serialize_run_plan(pair)["final_candidate_set"] == "DEV_QUALIFICATION_PAIR"


def test_compiler_cli_emits_only_the_dev_pair_execution_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_digest = "sha256:" + "1" * 64
    inventory = tmp_path / "inventory.json"
    inventory.write_text(_inventory(source_digest).model_dump_json(), encoding="utf-8")
    recipes = tmp_path / "recipes"
    outputs = tmp_path / "gguf"
    outputs.mkdir(mode=0o700)
    argv = [
        "compile_qwen38_quantization_recipes.py",
        "--inventory",
        str(inventory),
        "--llama-cpp-revision",
        LLAMA_CPP_B10419_REVISION,
        "--output-dir",
        str(recipes),
        "--calibration-manifest-digest",
        "sha256:" + "2" * 64,
        "--helper-q8-digest",
        "sha256:" + "3" * 64,
        "--imatrix-digest",
        "sha256:" + "4" * 64,
        "--emit-run-plans",
        "--source-bf16-path",
        str(tmp_path / "source.gguf"),
        "--calibration-text-path",
        str(tmp_path / "calibration.txt"),
        "--calibration-text-digest",
        "sha256:" + "5" * 64,
        "--quantize-binary-path",
        "/app/llama-quantize",
        "--quantize-binary-digest",
        "sha256:" + "6" * 64,
        "--imatrix-binary-path",
        "/app/llama-imatrix",
        "--imatrix-binary-digest",
        "sha256:" + "7" * 64,
        "--imatrix-path",
        str(tmp_path / "clean.imatrix.gguf"),
        "--artifact-output-dir",
        str(outputs),
        "--threads",
        "16",
        "--final-candidate-set",
        "DEV_QUALIFICATION_PAIR",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    assert compile_recipes_main() == 0
    assert not (recipes / "final_run_plan.json").exists()
    plan = LlamaCppQuantizationRunPlan.model_validate_json(
        (recipes / "dev_qualification_pair_run_plan.json").read_bytes()
    )
    assert tuple(item.recipe_name for item in plan.commands) == (
        QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
        QuantizationRecipeName.Q5_K_S_IMATRIX,
    )


def test_executor_reuses_only_an_exact_expected_q8_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary_dir = tmp_path / "bin"
    source_dir = tmp_path / "source"
    corpus_dir = tmp_path / "corpus"
    work_dir = tmp_path / "work"
    output_dir = tmp_path / "output"
    evidence_dir = tmp_path / "evidence"
    recipe_dir = tmp_path / "recipes"
    for directory in (
        binary_dir,
        source_dir,
        corpus_dir,
        work_dir,
        output_dir,
        evidence_dir,
        recipe_dir,
    ):
        directory.mkdir()
    quantize = binary_dir / "llama-quantize"
    imatrix = binary_dir / "llama-imatrix"
    source = source_dir / "source.gguf"
    corpus = corpus_dir / "calibration.txt"
    helper = work_dir / "helper.gguf"
    for path, content in (
        (quantize, b"quantizer"),
        (imatrix, b"imatrix"),
        (source, b"bf16"),
        (corpus, b"synthetic calibration"),
        (helper, b"verified q8 helper"),
    ):
        path.write_bytes(content)
    paths = LlamaCppQuantizationRunPaths(
        quantize_binary=str(quantize),
        imatrix_binary=str(imatrix),
        source_bf16_gguf=str(source),
        calibration_text=str(corpus),
        q8_helper_gguf=str(helper),
        imatrix_gguf=str(work_dir / "matrix.gguf"),
        q4_k_m_control_gguf=str(output_dir / "control.gguf"),
        q4_k_m_imatrix_gguf=str(output_dir / "q4.gguf"),
        q4_k_m_csight_mixed_gguf=str(output_dir / "mixed.gguf"),
        q5_k_s_imatrix_gguf=str(output_dir / "q5.gguf"),
        mixed_tensor_type_file=str(recipe_dir / "mixed.txt"),
    )
    plan = compile_llama_cpp_b10419_calibration_run_plan(
        paths=paths,
        source_bf16_gguf_digest=_digest(source),
        calibration_text_digest=_digest(corpus),
        quantize_binary_digest=_digest(quantize),
        imatrix_binary_digest=_digest(imatrix),
        threads=2,
        expected_helper_q8_digest=_digest(helper),
    )
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], *, check: bool) -> subprocess.CompletedProcess[bytes]:
        assert check is True
        calls.append(arguments)
        Path(paths.imatrix_gguf).write_bytes(b"computed matrix")
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setenv("ALLOW_QWEN38_QUANTIZATION", "YES")
    monkeypatch.setattr(subprocess, "run", fake_run)
    evidence = execute_run_plan(plan, evidence_output=evidence_dir / "run.json")

    assert len(calls) == 1
    assert calls[0][0] == str(imatrix)
    commands = cast(list[dict[str, Any]], evidence["commands"])
    assert commands[0]["execution"] == "REUSED_VERIFIED"
    assert commands[1]["execution"] == "EXECUTED"


def test_final_docker_executor_is_offline_bounded_and_records_owner_only_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, paths, quantize_digest = _docker_final_plan(tmp_path, reusable_control=True)
    image_id = "sha256:" + "e" * 64
    calls: list[list[str]] = []
    output_paths = {command.output_path for command in plan.commands}

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["check"] is True
        assert kwargs["text"] is True
        calls.append(arguments)
        if arguments[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(arguments, 0, stdout=image_id + "\n", stderr="")
        if "--entrypoint=/usr/bin/sha256sum" in arguments:
            assert f"--user={os.getuid()}:{os.getgid()}" in arguments
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=quantize_digest.removeprefix("sha256:") + "  /app/llama-quantize\n",
                stderr="",
            )
        output = next(Path(value) for value in arguments if value in output_paths)
        output.write_bytes(f"generated:{output.name}".encode())
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setenv("ALLOW_QWEN38_QUANTIZATION", "YES")
    monkeypatch.setattr(subprocess, "run", fake_run)
    evidence_path = tmp_path / "evidence" / "final-run.json"

    evidence = execute_final_run_plan_in_docker(
        plan,
        image_id=image_id,
        evidence_output=evidence_path,
    )

    quantization_calls = [call for call in calls if "--entrypoint=/app/llama-quantize" in call]
    assert len(quantization_calls) == 3
    for call in quantization_calls:
        assert {
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cpus=16",
            "--memory=56g",
            "--memory-swap=56g",
            "--pids-limit=1024",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
        } <= set(call)
        assert not any("gpu" in argument.casefold() for argument in call)
        assert "/bin/sh" not in call and "-c" not in call
        assert f"--user={os.getuid()}:{os.getgid()}" in call
        assert image_id in call
        assert paths.source_bf16_gguf in call
        assert paths.q8_helper_gguf not in call
        command = next(command for command in plan.commands if command.output_path in call)
        for raw_path in command.input_digests:
            if raw_path != "/app/llama-quantize":
                assert f"type=bind,source={raw_path},target={raw_path},readonly" in call
        writable_mount = (
            f"type=bind,source={Path(paths.q4_k_m_control_gguf).parent},"
            f"target={Path(paths.q4_k_m_control_gguf).parent}"
        )
        mounts = [call[index + 1] for index, value in enumerate(call[:-1]) if value == "--mount"]
        assert writable_mount in mounts
        assert [mount for mount in mounts if not mount.endswith(",readonly")] == [writable_mount]
    commands = cast(list[dict[str, Any]], evidence["commands"])
    assert commands[0]["execution"] == "REUSED_VERIFIED"
    assert all(command["output_digest"].startswith("sha256:") for command in commands)
    assert evidence["tool_image_id"] == image_id
    assert evidence["quantize_binary_digest"] == quantize_digest
    assert evidence["plan_digest"] == plan.plan_digest
    assert evidence["all_host_inputs_reverified_after_execution"] is True
    assert evidence["final_candidates_from_bf16"] is True
    assert stat.S_IMODE(evidence_path.stat().st_mode) == 0o600
    assert json.loads(evidence_path.read_text(encoding="utf-8")) == evidence


def test_final_docker_executor_runs_only_the_dev_qualification_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _, quantize_digest = _docker_final_plan(
        tmp_path,
        reusable_control=False,
        final_candidate_set=FinalCandidateSet.DEV_QUALIFICATION_PAIR,
    )
    image_id = "sha256:" + "e" * 64
    calls: list[list[str]] = []
    output_paths = {command.output_path for command in plan.commands}

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["check"] is True
        calls.append(arguments)
        if arguments[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(arguments, 0, stdout=image_id + "\n", stderr="")
        if "--entrypoint=/usr/bin/sha256sum" in arguments:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=quantize_digest.removeprefix("sha256:") + "  /app/llama-quantize\n",
                stderr="",
            )
        output = next(Path(value) for value in arguments if value in output_paths)
        output.write_bytes(f"generated:{output.name}".encode())
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setenv("ALLOW_QWEN38_QUANTIZATION", "YES")
    monkeypatch.setattr(subprocess, "run", fake_run)
    evidence = execute_final_run_plan_in_docker(
        plan,
        image_id=image_id,
        evidence_output=tmp_path / "evidence" / "pair.json",
    )

    quantization_calls = [call for call in calls if "--entrypoint=/app/llama-quantize" in call]
    assert len(quantization_calls) == 2
    assert tuple(
        item["recipe_name"] for item in cast(list[dict[str, Any]], evidence["commands"])
    ) == (
        QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED.value,
        QuantizationRecipeName.Q5_K_S_IMATRIX.value,
    )
    absent_outputs = {
        tmp_path / "output" / "control.gguf",
        tmp_path / "output" / "q4-imatrix.gguf",
    }
    assert all(not path.exists() for path in absent_outputs)


def test_final_docker_executor_requires_owner_only_output_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _, _ = _docker_final_plan(tmp_path, reusable_control=False)
    Path(plan.commands[0].output_path).parent.chmod(0o750)
    calls: list[list[str]] = []

    def fail_if_called(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        raise AssertionError("Docker must not be touched for a non-private output directory")

    monkeypatch.setenv("ALLOW_QWEN38_QUANTIZATION", "YES")
    monkeypatch.setattr(subprocess, "run", fail_if_called)
    with pytest.raises(QuantizationAssetError, match="owner-only mode 700"):
        execute_final_run_plan_in_docker(
            plan,
            image_id="sha256:" + "e" * 64,
            evidence_output=tmp_path / "evidence" / "private.json",
        )
    assert calls == []


def test_final_docker_executor_revalidates_plan_before_docker_or_output_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, paths, _ = _docker_final_plan(tmp_path, reusable_control=False)
    tampered = plan.model_copy(update={"plan_digest": "sha256:" + "f" * 64})
    calls: list[list[str]] = []

    def fail_if_called(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        raise AssertionError("Docker must not be touched for a tampered plan")

    monkeypatch.setenv("ALLOW_QWEN38_QUANTIZATION", "YES")
    monkeypatch.setattr(subprocess, "run", fail_if_called)
    evidence_path = tmp_path / "evidence" / "tampered.json"

    with pytest.raises(QuantizationAssetError, match="strict revalidation"):
        execute_final_run_plan_in_docker(
            tampered,
            image_id="sha256:" + "e" * 64,
            evidence_output=evidence_path,
        )

    assert calls == []
    assert not evidence_path.exists()
    assert all(not Path(command.output_path).exists() for command in plan.commands)
    assert Path(paths.source_bf16_gguf).read_bytes() == b"exact bf16 source"


def test_final_docker_executor_quarantines_outputs_when_an_input_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, paths, quantize_digest = _docker_final_plan(tmp_path, reusable_control=False)
    image_id = "sha256:" + "e" * 64
    output_paths = {command.output_path for command in plan.commands}
    quantization_calls = 0

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal quantization_calls
        assert kwargs["check"] is True
        if arguments[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(arguments, 0, stdout=image_id + "\n", stderr="")
        if "--entrypoint=/usr/bin/sha256sum" in arguments:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=quantize_digest.removeprefix("sha256:") + "  /app/llama-quantize\n",
                stderr="",
            )
        output = next(Path(value) for value in arguments if value in output_paths)
        output.write_bytes(f"generated:{output.name}".encode())
        quantization_calls += 1
        if quantization_calls == len(plan.commands):
            Path(paths.source_bf16_gguf).write_bytes(b"source changed during execution")
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setenv("ALLOW_QWEN38_QUANTIZATION", "YES")
    monkeypatch.setattr(subprocess, "run", fake_run)
    evidence_path = tmp_path / "evidence" / "changed-input.json"

    with pytest.raises(QuantizationAssetError, match="input changed during execution"):
        execute_final_run_plan_in_docker(
            plan,
            image_id=image_id,
            evidence_output=evidence_path,
        )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "FAIL"
    assert evidence["failure_code"] == "QUANTIZATION_EXECUTION_FAILED"
    assert len(evidence["completed_commands"]) == len(plan.commands)
    assert all(row["state"] == "PRESENT_UNQUALIFIED" for row in evidence["partial_outputs"])
    assert stat.S_IMODE(evidence_path.stat().st_mode) == 0o600


def test_final_docker_executor_refuses_unpinned_existing_output_before_docker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _, _ = _docker_final_plan(tmp_path, reusable_control=False)
    Path(plan.commands[0].output_path).write_bytes(b"unapproved output")
    calls: list[list[str]] = []

    def record_unexpected_call(
        arguments: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setenv("ALLOW_QWEN38_QUANTIZATION", "YES")
    monkeypatch.setattr(subprocess, "run", record_unexpected_call)

    with pytest.raises(QuantizationAssetError, match="refusing to overwrite"):
        execute_final_run_plan_in_docker(
            plan,
            image_id="sha256:" + "e" * 64,
            evidence_output=tmp_path / "evidence" / "refused.json",
        )

    assert calls == []


def test_final_docker_executor_rejects_tag_and_binary_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _, _ = _docker_final_plan(tmp_path, reusable_control=False)
    calls: list[list[str]] = []
    monkeypatch.setenv("ALLOW_QWEN38_QUANTIZATION", "YES")

    def reject_binary(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if arguments[:3] == ["docker", "image", "inspect"]:
            image_id = "sha256:" + "e" * 64
            return subprocess.CompletedProcess(arguments, 0, stdout=image_id + "\n", stderr="")
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout=("0" * 64) + "  /app/llama-quantize\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", reject_binary)
    evidence_path = tmp_path / "evidence" / "bad-image.json"
    with pytest.raises(QuantizationAssetError, match="exact local sha256 image ID"):
        execute_final_run_plan_in_docker(
            plan,
            image_id="local/llama.cpp:b10419",
            evidence_output=evidence_path,
        )
    assert calls == []

    with pytest.raises(QuantizationAssetError, match="digest does not match"):
        execute_final_run_plan_in_docker(
            plan,
            image_id="sha256:" + "e" * 64,
            evidence_output=evidence_path,
        )
    assert len(calls) == 2
    assert not evidence_path.exists()
    assert all(not Path(command.output_path).exists() for command in plan.commands)
