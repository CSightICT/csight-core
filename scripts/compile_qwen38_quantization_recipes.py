"""Validate the Qwen3.8 GGUF tensor inventory and compile auditable quant recipes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from app.platform.quantization_assets import (
    LLAMA_CPP_B10419_REVISION,
    FinalCandidateSet,
    LlamaCppQuantizationRunPaths,
    LlamaCppQuantizationRunPlan,
    QuantizationAssetError,
    QuantizationRecipeName,
    TensorInventory,
    compile_calibration_helper_recipe,
    compile_llama_cpp_b10419_calibration_run_plan,
    compile_llama_cpp_b10419_final_run_plan,
    compile_quantization_recipe,
    render_llama_cpp_tensor_type_file,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "local-data/qwen38-27b-quantization/recipes-v1"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--llama-cpp-revision", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--calibration-manifest-digest")
    parser.add_argument("--helper-q8-digest")
    parser.add_argument("--imatrix-digest")
    parser.add_argument("--emit-run-plans", action="store_true")
    parser.add_argument("--source-bf16-path", type=Path)
    parser.add_argument("--calibration-text-path", type=Path)
    parser.add_argument("--calibration-text-digest")
    parser.add_argument("--quantize-binary-path", type=Path)
    parser.add_argument("--quantize-binary-digest")
    parser.add_argument("--imatrix-binary-path", type=Path)
    parser.add_argument("--imatrix-binary-digest")
    parser.add_argument("--imatrix-path", type=Path)
    parser.add_argument("--artifact-output-dir", type=Path)
    parser.add_argument("--expected-q4-k-m-control-digest")
    parser.add_argument("--expected-q4-k-m-imatrix-digest")
    parser.add_argument("--expected-q4-k-m-csight-mixed-digest")
    parser.add_argument("--expected-q5-k-s-imatrix-digest")
    parser.add_argument(
        "--final-candidate-set",
        choices=tuple(item.value for item in FinalCandidateSet),
        default=FinalCandidateSet.FOUR_WAY_COMPARISON.value,
        help=(
            "GGUF output set to place in the executable final plan; "
            "DEV_QUALIFICATION_PAIR emits only mixed Q4/Q6 and Q5"
        ),
    )
    parser.add_argument("--threads", type=int, default=16)
    return parser.parse_args()


def _write_once(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise QuantizationAssetError(f"refusing to overwrite recipe artifact: {path}")
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text_once(path: Path, value: str) -> str:
    if path.exists() or path.is_symlink():
        raise QuantizationAssetError(f"refusing to overwrite recipe artifact: {path}")
    path.write_text(value, encoding="utf-8")
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def serialize_run_plan(plan: LlamaCppQuantizationRunPlan) -> dict[str, object]:
    exclusions = (
        {"final_candidate_set"}
        if plan.schema_version == "llama_cpp_quantization_run_plan/1.0.0"
        else set()
    )
    return plan.model_dump(mode="json", exclude=exclusions)


def require_run_plan_arguments(arguments: argparse.Namespace, *, final_inputs_ready: bool) -> None:
    required = {
        "source_bf16_path": arguments.source_bf16_path,
        "calibration_text_path": arguments.calibration_text_path,
        "calibration_text_digest": arguments.calibration_text_digest,
        "quantize_binary_path": arguments.quantize_binary_path,
        "quantize_binary_digest": arguments.quantize_binary_digest,
        "imatrix_binary_path": arguments.imatrix_binary_path,
        "imatrix_binary_digest": arguments.imatrix_binary_digest,
        "artifact_output_dir": arguments.artifact_output_dir,
    }
    missing = tuple(name for name, value in required.items() if value is None)
    if missing:
        raise QuantizationAssetError("executable run plans require: " + ", ".join(missing))
    if arguments.llama_cpp_revision != LLAMA_CPP_B10419_REVISION:
        raise QuantizationAssetError("executable run plans require pinned llama.cpp b10419")
    if final_inputs_ready and arguments.imatrix_path is None:
        raise QuantizationAssetError("final executable run plans require a separate --imatrix-path")
    if (
        final_inputs_ready
        and arguments.imatrix_path.absolute().parent == arguments.artifact_output_dir.absolute()
    ):
        raise QuantizationAssetError(
            "final imatrix input must be outside the writable artifact output directory"
        )


def validate_digest_arguments(arguments: argparse.Namespace) -> bool:
    """Return whether all final-candidate inputs are pinned.

    A Q8 helper digest alone is useful for resuming the calibration phase without
    overwriting the existing helper. It is not sufficient to compile final recipes.
    """

    has_calibration_manifest = arguments.calibration_manifest_digest is not None
    has_helper = arguments.helper_q8_digest is not None
    has_imatrix = arguments.imatrix_digest is not None
    final_inputs_ready = has_calibration_manifest and has_helper and has_imatrix
    if has_calibration_manifest != has_imatrix or (
        (has_calibration_manifest or has_imatrix) and not has_helper
    ):
        raise QuantizationAssetError(
            "final imatrix recipes require calibration, Q8 helper, and imatrix digests together"
        )
    if has_helper and not final_inputs_ready and not arguments.emit_run_plans:
        raise QuantizationAssetError(
            "a helper-only digest is valid only when emitting a resumable calibration run plan"
        )
    return final_inputs_ready


def build_run_paths(arguments: argparse.Namespace, output: Path) -> LlamaCppQuantizationRunPaths:
    artifact_output = arguments.artifact_output_dir.absolute()
    imatrix_path = (
        arguments.imatrix_path.absolute()
        if arguments.imatrix_path is not None
        else artifact_output / "Qwen3.8-27B-CSight-calibration.imatrix.gguf"
    )
    return LlamaCppQuantizationRunPaths(
        quantize_binary=str(arguments.quantize_binary_path.absolute()),
        imatrix_binary=str(arguments.imatrix_binary_path.absolute()),
        source_bf16_gguf=str(arguments.source_bf16_path.absolute()),
        calibration_text=str(arguments.calibration_text_path.absolute()),
        q8_helper_gguf=str(artifact_output / "Qwen3.8-27B-CSight-Q8_0-imatrix-helper.gguf"),
        imatrix_gguf=str(imatrix_path),
        q4_k_m_control_gguf=str(artifact_output / "Qwen3.8-27B-CSight-Q4_K_M-control.gguf"),
        q4_k_m_imatrix_gguf=str(artifact_output / "Qwen3.8-27B-Q4_K_M-imatrix.gguf"),
        q4_k_m_csight_mixed_gguf=str(artifact_output / "Qwen3.8-27B-CSight-Q4_K_M.gguf"),
        q5_k_s_imatrix_gguf=str(artifact_output / "Qwen3.8-27B-CSight-Q5_K_S.gguf"),
        mixed_tensor_type_file=str(output / "q4_k_m_csight_mixed.tensor-types.txt"),
    )


def build_expected_final_output_digests(
    arguments: argparse.Namespace,
) -> dict[QuantizationRecipeName, str]:
    candidates = {
        QuantizationRecipeName.Q4_K_M_CONTROL: arguments.expected_q4_k_m_control_digest,
        QuantizationRecipeName.Q4_K_M_IMATRIX: arguments.expected_q4_k_m_imatrix_digest,
        QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED: (arguments.expected_q4_k_m_csight_mixed_digest),
        QuantizationRecipeName.Q5_K_S_IMATRIX: arguments.expected_q5_k_s_imatrix_digest,
    }
    return {name: digest for name, digest in candidates.items() if digest is not None}


def main() -> int:
    arguments = _arguments()
    if arguments.inventory.is_symlink() or not arguments.inventory.is_file():
        raise QuantizationAssetError("tensor inventory must be a regular file")
    try:
        inventory = TensorInventory.model_validate_json(arguments.inventory.read_bytes())
    except ValidationError as error:
        raise QuantizationAssetError("tensor inventory failed the Qwen3.8 contract") from error
    final_inputs_ready = validate_digest_arguments(arguments)
    if arguments.emit_run_plans:
        require_run_plan_arguments(arguments, final_inputs_ready=final_inputs_ready)
    output = arguments.output_dir
    if output.is_symlink():
        raise QuantizationAssetError("output directory must not be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    helper = compile_calibration_helper_recipe(
        inventory=inventory,
        llama_cpp_revision=arguments.llama_cpp_revision,
    )
    _write_once(output / "q8_0_calibration_helper_recipe.json", helper.model_dump(mode="json"))
    control = compile_quantization_recipe(
        name=QuantizationRecipeName.Q4_K_M_CONTROL,
        inventory=inventory,
        llama_cpp_revision=arguments.llama_cpp_revision,
        calibration_manifest_digest=None,
        imatrix_digest=None,
    )
    _write_once(output / "q4_k_m_control_recipe.json", control.model_dump(mode="json"))
    recipes = [control]
    if final_inputs_ready:
        for name in (
            QuantizationRecipeName.Q4_K_M_IMATRIX,
            QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
            QuantizationRecipeName.Q5_K_S_IMATRIX,
        ):
            recipe = compile_quantization_recipe(
                name=name,
                inventory=inventory,
                llama_cpp_revision=arguments.llama_cpp_revision,
                calibration_manifest_digest=arguments.calibration_manifest_digest,
                calibration_helper_q8_digest=arguments.helper_q8_digest,
                imatrix_digest=arguments.imatrix_digest,
            )
            _write_once(
                output / f"{name.value.casefold()}_recipe.json", recipe.model_dump(mode="json")
            )
            recipes.append(recipe)
    if arguments.emit_run_plans:
        paths = build_run_paths(arguments, output.absolute())
        calibration_plan = compile_llama_cpp_b10419_calibration_run_plan(
            paths=paths,
            source_bf16_gguf_digest=inventory.source_gguf_digest,
            calibration_text_digest=arguments.calibration_text_digest,
            quantize_binary_digest=arguments.quantize_binary_digest,
            imatrix_binary_digest=arguments.imatrix_binary_digest,
            threads=arguments.threads,
            expected_helper_q8_digest=arguments.helper_q8_digest,
            expected_imatrix_digest=arguments.imatrix_digest,
        )
        _write_once(
            output / "calibration_run_plan.json",
            serialize_run_plan(calibration_plan),
        )
        if final_inputs_ready:
            final_candidate_set = FinalCandidateSet(arguments.final_candidate_set)
            selected_recipe_names = (
                tuple(QuantizationRecipeName)
                if final_candidate_set is FinalCandidateSet.FOUR_WAY_COMPARISON
                else (
                    QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
                    QuantizationRecipeName.Q5_K_S_IMATRIX,
                )
            )
            mixed_recipe = next(
                item
                for item in recipes
                if item.recipe_name is QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED
            )
            tensor_type_digest = _write_text_once(
                Path(paths.mixed_tensor_type_file),
                render_llama_cpp_tensor_type_file(mixed_recipe),
            )
            final_plan = compile_llama_cpp_b10419_final_run_plan(
                paths=paths,
                recipes=tuple(
                    item for item in recipes if item.recipe_name in selected_recipe_names
                ),
                calibration_text_digest=arguments.calibration_text_digest,
                quantize_binary_digest=arguments.quantize_binary_digest,
                imatrix_binary_digest=arguments.imatrix_binary_digest,
                mixed_tensor_type_file_digest=tensor_type_digest,
                threads=arguments.threads,
                expected_output_digests=build_expected_final_output_digests(arguments),
                final_candidate_set=final_candidate_set,
            )
            final_plan_name = (
                "final_run_plan.json"
                if final_candidate_set is FinalCandidateSet.FOUR_WAY_COMPARISON
                else "dev_qualification_pair_run_plan.json"
            )
            _write_once(output / final_plan_name, serialize_run_plan(final_plan))
    run_order = {
        "schema_version": "gguf_quantization_run_order/1.0.0",
        "steps": [
            {
                "order": 1,
                "operation": "VALIDATE_BF16_TENSOR_INVENTORY",
                "input_digest": inventory.source_gguf_digest,
            },
            {
                "order": 2,
                "operation": "CREATE_Q8_0_CALIBRATION_HELPER_FROM_BF16",
                "purpose": "IMATRIX_COMPUTE_ONLY",
            },
            {
                "order": 3,
                "operation": "COMPUTE_IMATRIX_ON_Q8_0_HELPER",
                "token_budget": 750000,
            },
            {
                "order": 4,
                "operation": (
                    "QUANTIZE_ALL_FINAL_CANDIDATES_DIRECTLY_FROM_BF16"
                    if arguments.final_candidate_set == FinalCandidateSet.FOUR_WAY_COMPARISON.value
                    else "QUANTIZE_DEV_QUALIFICATION_PAIR_DIRECTLY_FROM_BF16"
                ),
                "final_candidate_set": arguments.final_candidate_set,
                "forbid_helper_as_final_source": True,
            },
            {"order": 5, "operation": "PPL_HOLDOUT", "token_budget": 100000},
            {"order": 6, "operation": "LOGITS_HOLDOUT", "token_budget": 16000},
        ],
    }
    _write_once(output / "run_order.json", run_order)
    plan_status = " executable_plans=YES" if arguments.emit_run_plans else ""
    print(
        "QWEN38_QUANTIZATION_RECIPES_COMPILED "
        f"blocks={inventory.block_count} helper=Q8_0 final_source=BF16_GGUF{plan_status}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
