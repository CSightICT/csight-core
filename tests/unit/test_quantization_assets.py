from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform import quantization_assets as subject
from app.platform.quantization_assets import (
    LLAMA_CPP_B10419_REVISION,
    LLAMA_CPP_IMATRIX_OUTPUT_FREQUENCY,
    ChatMessage,
    ChatRole,
    ChatTemplateContract,
    CorpusSplit,
    FinalCandidateSet,
    LlamaCppQuantizationRunPaths,
    MixCategory,
    MixQuota,
    NormalizedCorpusRecord,
    QuantizationAssetError,
    QuantizationCorpusPlan,
    QuantizationRecipeName,
    SourceKind,
    SourcePin,
    TensorInfo,
    TensorInventory,
    build_quantization_corpus,
    compile_calibration_helper_recipe,
    compile_llama_cpp_b10419_calibration_run_plan,
    compile_llama_cpp_b10419_final_run_plan,
    compile_quantization_recipe,
    pii_finding_codes,
    render_llama_cpp_tensor_type_file,
    render_qwen38_text_chat,
)
from app.platform.quantization_assets import (
    TestLeakageIndex as LeakageIndex,
)

DIGEST = "sha256:" + "a" * 64
OTHER_DIGEST = "sha256:" + "b" * 64
THIRD_DIGEST = "sha256:" + "c" * 64
REVISION = "1" * 40
ROOT = Path(__file__).resolve().parents[2]


class _CharacterTokenizer:
    identity_digest = DIGEST

    def encode(self, text: str) -> tuple[int, ...]:
        return tuple(ord(value) for value in text)

    def decode(self, token_ids: Sequence[int]) -> str:
        return "".join(chr(value) for value in token_ids)


def _plan() -> QuantizationCorpusPlan:
    pins = tuple(
        SourcePin(
            source_id=f"csight://source/{index}",
            kind=SourceKind.LOCAL_SYNTHETIC,
            category=category,
            revision="sha256:" + f"{index + 1:x}" * 64,
            license_identifier="CSIGHT-SYNTHETIC",
            visibility="LOCAL_SYNTHETIC",
            pii_usage="SYNTHETIC_PII_FREE",
        )
        for index, category in enumerate(MixCategory)
    )
    return QuantizationCorpusPlan(
        plan_name="unit-test-plan",
        seed="fixed-unit-seed",
        mix=tuple(
            MixQuota(category=category, percent=percent)
            for category, percent in zip(MixCategory, (35, 20, 10, 10, 20, 5), strict=True)
        ),
        chat_template=ChatTemplateContract(
            model_artifact="Qwen/Qwen3.8-27B",
            model_revision=REVISION,
            tokenizer_config_digest=DIGEST,
            chat_template_digest=OTHER_DIGEST,
            gguf_tokenizer_metadata_digest=DIGEST,
            llama_cpp_revision=REVISION,
            tokenizer_implementation="llama.cpp GGUF tokenizer",
            tokenizer_runtime_identity_digest=DIGEST,
        ),
        sources=pins,
        test_reference_digests=(DIGEST, OTHER_DIGEST, "sha256:" + "c" * 64),
    )


def _records(plan: QuantizationCorpusPlan) -> list[NormalizedCorpusRecord]:
    values: list[NormalizedCorpusRecord] = []
    for category_index, category in enumerate(MixCategory):
        pin = next(item for item in plan.sources if item.category is category)
        for record_index in range(4):
            distinctive = f"category-{category_index}-record-{record_index}-"
            values.append(
                NormalizedCorpusRecord(
                    record_id=f"R-{category_index}-{record_index}",
                    source_id=pin.source_id,
                    source_revision=pin.revision,
                    category=category,
                    license_identifier=pin.license_identifier,
                    pii_reviewed=True,
                    source_partition="DEV",
                    messages=(
                        ChatMessage(
                            role=ChatRole.USER,
                            content=distinctive + (chr(65 + category_index) * 600),
                        ),
                    ),
                )
            )
    return values


def _hybrid_inventory() -> TensorInventory:
    tensors = [
        TensorInfo(name="token_embd.weight", shape=(100, 64), dtype="F16", n_bytes=12800),
        TensorInfo(name="output_norm.weight", shape=(64,), dtype="F32", n_bytes=256),
        TensorInfo(name="output.weight", shape=(100, 64), dtype="F16", n_bytes=12800),
    ]
    for block in range(64):
        for suffix in ("ffn_gate.weight", "ffn_up.weight", "ffn_down.weight"):
            tensors.append(
                TensorInfo(name=f"blk.{block}.{suffix}", shape=(64, 64), dtype="F16", n_bytes=8192)
            )
        attention = (
            ("attn_q.weight", "attn_k.weight", "attn_v.weight", "attn_output.weight")
            if block % 4 == 3
            else ("attn_qkv.weight", "attn_gate.weight", "ssm_out.weight")
        )
        for suffix in attention:
            tensors.append(
                TensorInfo(name=f"blk.{block}.{suffix}", shape=(64, 64), dtype="F16", n_bytes=8192)
            )
    return TensorInventory(source_gguf_digest=DIGEST, tensors=tuple(tensors))


def _run_paths() -> LlamaCppQuantizationRunPaths:
    root = "/opt/csight/qwen38"
    return LlamaCppQuantizationRunPaths(
        quantize_binary=f"{root}/bin/llama-quantize",
        imatrix_binary=f"{root}/bin/llama-imatrix",
        source_bf16_gguf=f"{root}/source/Qwen3.8-27B-BF16.gguf",
        calibration_text=f"{root}/corpus/calibration.txt",
        q8_helper_gguf=f"{root}/work/Qwen3.8-27B-CSight-Q8_0-imatrix-helper.gguf",
        imatrix_gguf=f"{root}/work/Qwen3.8-27B-CSight-calibration.imatrix.gguf",
        q4_k_m_control_gguf=f"{root}/output/Qwen3.8-27B-CSight-Q4_K_M-control.gguf",
        q4_k_m_imatrix_gguf=f"{root}/output/Qwen3.8-27B-Q4_K_M-imatrix.gguf",
        q4_k_m_csight_mixed_gguf=f"{root}/output/Qwen3.8-27B-CSight-Q4_K_M.gguf",
        q5_k_s_imatrix_gguf=f"{root}/output/Qwen3.8-27B-CSight-Q5_K_S.gguf",
        mixed_tensor_type_file=f"{root}/recipes/q4_k_m_csight_mixed.tensor-types.txt",
    )


def _compiled_recipes() -> tuple[subject.CompiledQuantizationRecipe, ...]:
    inventory = _hybrid_inventory()
    values = []
    for name in QuantizationRecipeName:
        values.append(
            compile_quantization_recipe(
                name=name,
                inventory=inventory,
                llama_cpp_revision=LLAMA_CPP_B10419_REVISION,
                calibration_manifest_digest=(
                    None if name is QuantizationRecipeName.Q4_K_M_CONTROL else DIGEST
                ),
                calibration_helper_q8_digest=(
                    None if name is QuantizationRecipeName.Q4_K_M_CONTROL else OTHER_DIGEST
                ),
                imatrix_digest=(
                    None if name is QuantizationRecipeName.Q4_K_M_CONTROL else THIRD_DIGEST
                ),
            )
        )
    return tuple(values)


@pytest.mark.unit
def test_frozen_mix_and_exact_text_renderer() -> None:
    plan = _plan()
    assert tuple(item.percent for item in plan.mix) == (35, 20, 10, 10, 20, 5)
    assert tuple(item.category for item in plan.mix) == tuple(MixCategory)
    rendered = render_qwen38_text_chat(
        (
            ChatMessage(role=ChatRole.SYSTEM, content=" system "),
            ChatMessage(role=ChatRole.USER, content=" question "),
            ChatMessage(role=ChatRole.ASSISTANT, content=" answer "),
        )
    )
    assert rendered == (
        "<|im_start|>system\nsystem<|im_end|>\n"
        "<|im_start|>user\nquestion<|im_end|>\n"
        "<|im_start|>assistant\nanswer<|im_end|>\n"
    )


@pytest.mark.unit
def test_tracked_source_registry_pins_public_revisions_and_approved_mix() -> None:
    registry = json.loads(
        (ROOT / "evaluation/llm/qwen38_quantization_v1/source_registry.json").read_text()
    )
    assert registry["source_bf16_artifact"] == "ggml-org/Qwen3.8-27B-GGUF"
    assert registry["source_bf16_revision"] == "0669b98607d47046c7c2b3f801011d54a08cfccf"
    assert registry["source_bf16_content_digest"] == (
        "sha256:5a3eedc837bcbd1365cdbf5b71e698df3122e76586ba872f07ce3ed4a9bfa97e"
    )
    assert registry["source_bf16_bytes"] == 53_808_281_952
    assert [(item["category"], item["percent"]) for item in registry["mix"]] == [
        ("CSIGHT_EXTRACTION", 35),
        ("CSIGHT_POLICY_GROUNDING", 20),
        ("CSIGHT_QUERY_BUILDER", 10),
        ("CSIGHT_SAFETY_JSON_INJECTION", 10),
        ("PUBLIC_KO_WIKIPEDIA", 20),
        ("PUBLIC_EN_WIKITEXT", 5),
    ]
    public = {item["source_id"]: item for item in registry["mix"] if "config" in item}
    assert public["wikimedia/wikipedia"]["revision"] == ("b04c8d1ceb2f5cd4588862100d08de323dccfbaa")
    assert public["wikimedia/wikipedia"]["config"] == "20231101.ko"
    assert public["Salesforce/wikitext"]["revision"] == ("b08601e04326c79dfdd32d625aee71d232d685c3")
    assert public["Salesforce/wikitext"]["config"] == "wikitext-2-raw-v1"


@pytest.mark.unit
def test_private_hub_source_cannot_enter_calibration_plan() -> None:
    with pytest.raises(ValidationError, match="SHADOW-only"):
        SourcePin(
            source_id="private/personal-model-data",
            kind=SourceKind.HUGGING_FACE_DATASET,
            category=MixCategory.PUBLIC_EN_WIKITEXT,
            revision=REVISION,
            license_identifier="PRIVATE",
            visibility="LOCAL_SYNTHETIC",
            config="default",
            split="train",
            pii_usage="PUBLIC_LICENSED_PII_SCREENED",
        )


@pytest.mark.unit
def test_builder_enforces_exact_three_way_budgets_and_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 1000, "PPL_HOLDOUT": 1000, "LOGITS_HOLDOUT": 1000},
    )
    plan = _plan()
    build = build_quantization_corpus(
        plan=plan,
        records=_records(plan),
        tokenizer=_CharacterTokenizer(),
        test_leakage_index=LeakageIndex(("sealed holdout phrase never emitted here",)),
    )
    assert len({item.record_id_hash for item in build.samples}) == len(build.samples)
    for split in CorpusSplit:
        assert sum(item.token_count for item in build.samples_for(split)) == 1000
        for category in MixCategory:
            assert sum(
                item.token_count for item in build.samples_for(split) if item.category is category
            ) == plan.target_for(split, category)


@pytest.mark.unit
def test_pii_and_test_leakage_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    assert pii_finding_codes("연락처 010-1234-5678") == ("KOREAN_PHONE",)
    monkeypatch.setattr(
        subject,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 1000, "PPL_HOLDOUT": 1000, "LOGITS_HOLDOUT": 1000},
    )
    plan = _plan()
    records = _records(plan)
    bad = records[0].model_copy(
        update={
            "record_id": "R-PII",
            "messages": (ChatMessage(role=ChatRole.USER, content="010-1234-5678"),),
        }
    )
    with pytest.raises(QuantizationAssetError, match="insufficient screened tokens"):
        build_quantization_corpus(
            plan=plan,
            records=(bad,),
            tokenizer=_CharacterTokenizer(),
            test_leakage_index=LeakageIndex(("sealed holdout phrase",)),
        )


@pytest.mark.unit
def test_qwen38_hybrid_inventory_and_q8_imatrix_provenance() -> None:
    inventory = _hybrid_inventory()
    assert inventory.block_count == 64
    helper = compile_calibration_helper_recipe(
        inventory=inventory,
        llama_cpp_revision=REVISION,
    )
    assert helper.helper_type == "Q8_0"
    assert helper.final_quantization_source == "BF16_GGUF"
    recipe = compile_quantization_recipe(
        name=QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
        inventory=inventory,
        llama_cpp_revision=REVISION,
        calibration_manifest_digest=DIGEST,
        calibration_helper_q8_digest=OTHER_DIGEST,
        imatrix_digest="sha256:" + "c" * 64,
    )
    assert recipe.quantization_source == "BF16_GGUF"
    assert recipe.imatrix_compute_source == "Q8_0_HELPER"
    assert recipe.calibration_helper_q8_digest == OTHER_DIGEST
    assert any(item.tensor_name == "blk.0.attn_qkv.weight" for item in recipe.overrides)
    assert any(item.tensor_name == "blk.63.attn_q.weight" for item in recipe.overrides)
    assert all(item.target_type != "Q8_0" for item in recipe.overrides)


@pytest.mark.unit
def test_hybrid_inventory_rejects_full_attention_in_linear_block() -> None:
    inventory = _hybrid_inventory()
    values = list(inventory.tensors)
    values = [item for item in values if item.name != "blk.0.attn_qkv.weight"]
    values.extend(
        TensorInfo(name=f"blk.0.{suffix}", shape=(64, 64), dtype="F16", n_bytes=8192)
        for suffix in (
            "attn_q.weight",
            "attn_k.weight",
            "attn_v.weight",
            "attn_output.weight",
        )
    )
    with pytest.raises(ValidationError, match="attention family"):
        TensorInventory(source_gguf_digest=DIGEST, tensors=tuple(values))


@pytest.mark.unit
def test_control_forbids_imatrix_and_helper() -> None:
    with pytest.raises(QuantizationAssetError, match="must not use"):
        compile_quantization_recipe(
            name=QuantizationRecipeName.Q4_K_M_CONTROL,
            inventory=_hybrid_inventory(),
            llama_cpp_revision=REVISION,
            calibration_manifest_digest=None,
            calibration_helper_q8_digest=OTHER_DIGEST,
            imatrix_digest=DIGEST,
        )


@pytest.mark.unit
def test_recipe_digests_fail_closed_after_content_tampering() -> None:
    helper = compile_calibration_helper_recipe(
        inventory=_hybrid_inventory(),
        llama_cpp_revision=REVISION,
    )
    helper_payload = helper.model_dump(mode="json")
    helper_payload["source_bf16_gguf_digest"] = OTHER_DIGEST
    with pytest.raises(ValidationError, match="digest does not match"):
        subject.CalibrationHelperRecipe.model_validate(helper_payload)

    recipe = _compiled_recipes()[1]
    recipe_payload = recipe.model_dump(mode="json")
    recipe_payload["default_type"] = "Q5_K_S"
    with pytest.raises(ValidationError, match="digest does not match"):
        subject.CompiledQuantizationRecipe.model_validate(recipe_payload)


@pytest.mark.unit
def test_mixed_recipe_renders_anchored_q6_tensor_type_file() -> None:
    recipe = _compiled_recipes()[2]
    assert recipe.recipe_name is QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED
    assert {item.target_type for item in recipe.overrides} == {"Q6_K"}
    rendered = render_llama_cpp_tensor_type_file(recipe)
    assert "^blk\\.0\\.attn_qkv\\.weight$=q6_k\n" in rendered
    assert "^blk\\.63\\.attn_q\\.weight$=q6_k\n" in rendered
    assert "token_embd\\.weight$=q6_k\n" in rendered
    assert "q5_k" not in rendered
    assert rendered.splitlines()[0] == "^blk\\.0\\.attn_gate\\.weight$=q6_k"
    assert rendered.splitlines()[-1] == "^token_embd\\.weight$=q6_k"


@pytest.mark.unit
def test_b10419_calibration_plan_uses_q8_helper_only_for_imatrix() -> None:
    paths = _run_paths()
    plan = compile_llama_cpp_b10419_calibration_run_plan(
        paths=paths,
        source_bf16_gguf_digest=DIGEST,
        calibration_text_digest=OTHER_DIGEST,
        quantize_binary_digest=THIRD_DIGEST,
        imatrix_binary_digest="sha256:" + "d" * 64,
        threads=12,
    )
    helper, imatrix = plan.commands
    assert helper.argv == (
        paths.quantize_binary,
        paths.source_bf16_gguf,
        paths.q8_helper_gguf,
        "Q8_0",
        "12",
    )
    assert imatrix.argv[0] == paths.imatrix_binary
    assert imatrix.generated_input_paths == (paths.q8_helper_gguf,)
    assert imatrix.argv[imatrix.argv.index("--model") + 1] == paths.q8_helper_gguf
    assert imatrix.argv[imatrix.argv.index("--output-file") + 1] == paths.imatrix_gguf
    assert imatrix.argv[imatrix.argv.index("--output-format") + 1] == "gguf"
    assert imatrix.argv[imatrix.argv.index("--n-gpu-layers") + 1] == "auto"
    assert imatrix.argv[imatrix.argv.index("--threads-batch") + 1] == "12"
    assert imatrix.argv[imatrix.argv.index("--flash-attn") + 1] == "on"
    assert imatrix.argv[imatrix.argv.index("--output-frequency") + 1] == str(
        LLAMA_CPP_IMATRIX_OUTPUT_FREQUENCY
    )
    assert {"--process-output", "--no-ppl", "--parse-special"} <= set(imatrix.argv)
    assert plan.final_candidates_from_bf16 is False


@pytest.mark.unit
def test_calibration_plan_rejects_self_digested_arbitrary_argv() -> None:
    plan = compile_llama_cpp_b10419_calibration_run_plan(
        paths=_run_paths(),
        source_bf16_gguf_digest=DIGEST,
        calibration_text_digest=OTHER_DIGEST,
        quantize_binary_digest=THIRD_DIGEST,
        imatrix_binary_digest="sha256:" + "d" * 64,
        threads=12,
    )
    payload = plan.model_dump(mode="json")
    payload["commands"][0]["argv"] = ["/bin/sh", "-c", "unsafe"]
    payload["plan_digest"] = subject.canonical_digest(
        {key: value for key, value in payload.items() if key != "plan_digest"}
    )
    with pytest.raises(ValidationError, match=r"threads are invalid|pinned b10419 argv"):
        subject.LlamaCppQuantizationRunPlan.model_validate(payload)


@pytest.mark.unit
def test_b10419_final_plan_is_exact_four_candidate_bf16_direct_comparison() -> None:
    paths = _run_paths()
    recipes = _compiled_recipes()
    tensor_file = render_llama_cpp_tensor_type_file(recipes[2])
    tensor_digest = "sha256:" + hashlib.sha256(tensor_file.encode()).hexdigest()
    plan = compile_llama_cpp_b10419_final_run_plan(
        paths=paths,
        recipes=recipes,
        calibration_text_digest="sha256:" + "d" * 64,
        quantize_binary_digest="sha256:" + "e" * 64,
        imatrix_binary_digest="sha256:" + "f" * 64,
        mixed_tensor_type_file_digest=tensor_digest,
        threads=12,
    )
    assert tuple(item.recipe_name for item in plan.commands) == tuple(QuantizationRecipeName)
    assert plan.calibration_helper_q8_digest == OTHER_DIGEST
    assert plan.imatrix_digest == THIRD_DIGEST
    for command in plan.commands:
        assert paths.source_bf16_gguf in command.argv
        assert paths.q8_helper_gguf not in command.argv
        assert "--allow-requantize" not in command.argv
        assert command.argv[-1] == "12"
    assert "--imatrix" not in plan.commands[0].argv
    assert all("--imatrix" in item.argv for item in plan.commands[1:])
    assert "--tensor-type-file" in plan.commands[2].argv
    assert plan.commands[-1].argv[-2] == "Q5_K_S"
    assert plan.final_candidates_from_bf16 is True


@pytest.mark.unit
def test_b10419_final_plan_can_pin_exact_outputs_for_verified_resume() -> None:
    paths = _run_paths()
    recipes = _compiled_recipes()
    tensor_file = render_llama_cpp_tensor_type_file(recipes[2])
    tensor_digest = "sha256:" + hashlib.sha256(tensor_file.encode()).hexdigest()
    expected_outputs = {
        recipe_name: "sha256:" + f"{index:x}" * 64
        for index, recipe_name in enumerate(QuantizationRecipeName, start=1)
    }

    plan = compile_llama_cpp_b10419_final_run_plan(
        paths=paths,
        recipes=recipes,
        calibration_text_digest="sha256:" + "d" * 64,
        quantize_binary_digest="sha256:" + "e" * 64,
        imatrix_binary_digest="sha256:" + "f" * 64,
        mixed_tensor_type_file_digest=tensor_digest,
        threads=12,
        expected_output_digests=expected_outputs,
    )

    assert {
        command.recipe_name: command.expected_output_digest for command in plan.commands
    } == expected_outputs
    assert all(command.final_quantization_source == "BF16_GGUF" for command in plan.commands)


@pytest.mark.unit
def test_b10419_dev_qualification_pair_plan_emits_only_mixed_and_q5() -> None:
    paths = _run_paths()
    recipes = _compiled_recipes()
    selected = tuple(
        item
        for item in recipes
        if item.recipe_name
        in {
            QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
            QuantizationRecipeName.Q5_K_S_IMATRIX,
        }
    )
    tensor_file = render_llama_cpp_tensor_type_file(selected[0])
    plan = compile_llama_cpp_b10419_final_run_plan(
        paths=paths,
        recipes=selected,
        calibration_text_digest="sha256:" + "d" * 64,
        quantize_binary_digest="sha256:" + "e" * 64,
        imatrix_binary_digest="sha256:" + "f" * 64,
        mixed_tensor_type_file_digest=(
            "sha256:" + hashlib.sha256(tensor_file.encode()).hexdigest()
        ),
        threads=12,
        final_candidate_set=FinalCandidateSet.DEV_QUALIFICATION_PAIR,
    )

    assert plan.schema_version == "llama_cpp_quantization_run_plan/1.1.0"
    assert plan.final_candidate_set is FinalCandidateSet.DEV_QUALIFICATION_PAIR
    assert tuple(item.recipe_name for item in plan.commands) == (
        QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
        QuantizationRecipeName.Q5_K_S_IMATRIX,
    )
    assert tuple(Path(item.output_path).name for item in plan.commands) == (
        "Qwen3.8-27B-CSight-Q4_K_M.gguf",
        "Qwen3.8-27B-CSight-Q5_K_S.gguf",
    )
    assert all(paths.source_bf16_gguf in item.argv for item in plan.commands)
    assert all(paths.q8_helper_gguf not in item.argv for item in plan.commands)


@pytest.mark.unit
def test_b10419_dev_pair_rejects_control_or_imatrix_q4_recipes() -> None:
    recipes = _compiled_recipes()
    with pytest.raises(QuantizationAssetError, match="selected output set"):
        compile_llama_cpp_b10419_final_run_plan(
            paths=_run_paths(),
            recipes=recipes,
            calibration_text_digest="sha256:" + "d" * 64,
            quantize_binary_digest="sha256:" + "e" * 64,
            imatrix_binary_digest="sha256:" + "f" * 64,
            mixed_tensor_type_file_digest="sha256:" + "1" * 64,
            threads=12,
            final_candidate_set=FinalCandidateSet.DEV_QUALIFICATION_PAIR,
        )
