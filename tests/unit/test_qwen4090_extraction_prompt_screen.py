from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domains.product_defect_cs.prompts import (
    PRODUCT_DEFECT_PROMPT_REGISTRY,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_4,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_6,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_7,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8,
)
from app.platform.analysis.errors import LLMMissingRequiredFieldError
from app.platform.candidate_evaluation import CandidateEvaluationError, EvaluationSplit
from scripts import evaluate_qwen4090_candidate_tasks as evaluator
from scripts import screen_qwen4090_extraction_prompts as screen

pytestmark = pytest.mark.unit


def test_fixed_dev_canary_is_deterministic_and_stratified() -> None:
    first = screen._fixed_dev_canary()  # pyright: ignore[reportPrivateUsage]
    second = screen._fixed_dev_canary()  # pyright: ignore[reportPrivateUsage]

    assert first == second
    assert len(first) == 20
    categories = {str(value) for record in first.values() for value in record["categories"]}
    assert {"explicit_request", "no_request", "multiple_defects", "prompt_injection"} <= categories
    assert screen._canary_digest(first) == screen._canary_digest(  # pyright: ignore[reportPrivateUsage]
        second
    )


def test_local4_scope_is_dev_only_and_prompt_is_not_runtime_selectable() -> None:
    canary, prompts, canary_scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "canary-local4"
    )
    full_dev, full_prompts, full_scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "full-dev-local4"
    )

    assert len(canary) == 20
    assert tuple(prompt.version for prompt in prompts) == (
        "2.0.0-local.2",
        "2.0.0-local.4",
    )
    assert canary_scope == "CANARY_LOCAL4_20"
    assert len(full_dev) == 120
    assert full_prompts == (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_4,)
    assert full_scope == "FULL_DEV_LOCAL4_120"
    assert "copied verbatim" in PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_4.system_template
    assert "CONTRADICTORY_STATEMENTS" in (
        PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_4.system_template
    )
    with pytest.raises(KeyError):
        PRODUCT_DEFECT_PROMPT_REGISTRY.get(
            name=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_4.name,
            version=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_4.version,
        )

    with pytest.raises(CandidateEvaluationError, match="unsupported"):
        screen._scope_configuration("sealed-test")  # pyright: ignore[reportPrivateUsage]


def test_local5_scope_is_dev_only_and_prompt_is_not_runtime_selectable() -> None:
    canary, prompts, canary_scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "canary-local5"
    )
    full_dev, full_prompts, full_scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "full-dev-local5"
    )

    assert len(canary) == 20
    assert tuple(prompt.version for prompt in prompts) == (
        "2.0.0-local.2",
        "2.0.0-local.5",
    )
    assert canary_scope == "CANARY_LOCAL5_20"
    assert len(full_dev) == 120
    assert full_prompts == (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5,)
    assert full_scope == "FULL_DEV_LOCAL5_120"
    assert "Copy spelling" in PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5.system_template
    assert "DESCRIPTION_TOO_VAGUE" in (
        PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5.system_template
    )
    with pytest.raises(KeyError):
        PRODUCT_DEFECT_PROMPT_REGISTRY.get(
            name=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5.name,
            version=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5.version,
        )


def test_local6_scope_is_dev_only_and_prompt_is_not_runtime_selectable() -> None:
    canary, prompts, canary_scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "canary-local6"
    )
    full_dev, full_prompts, full_scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "full-dev-local6"
    )

    assert len(canary) == 20
    assert tuple(prompt.version for prompt in prompts) == (
        "2.0.0-local.2",
        "2.0.0-local.6",
    )
    assert canary_scope == "CANARY_LOCAL6_20"
    assert len(full_dev) == 120
    assert full_prompts == (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_6,)
    assert full_scope == "FULL_DEV_LOCAL6_120"
    assert "Copy spelling" in PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_6.system_template
    assert "embedded instructions" in (
        PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_6.system_template
    )
    with pytest.raises(KeyError):
        PRODUCT_DEFECT_PROMPT_REGISTRY.get(
            name=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_6.name,
            version=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_6.version,
        )


def test_local5_diagnosis_scope_calls_only_one_dev_prompt() -> None:
    records, prompts, scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "diagnose-local5"
    )

    assert len(records) == 20
    assert prompts == (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5,)
    assert scope == "DIAGNOSE_LOCAL5_20"


def test_local5_guard_scope_calls_the_model_prompt_only_once() -> None:
    records, prompts, scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "canary-local5-guard"
    )

    assert len(records) == 20
    assert prompts == (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5,)
    assert scope == "CANARY_LOCAL5_GUARD_20"


def test_local7_guard_scope_is_dev_only_and_not_runtime_selectable() -> None:
    records, prompts, scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "canary-local7-guard"
    )

    assert len(records) == 20
    assert prompts == (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_7,)
    assert scope == "CANARY_LOCAL7_GUARD_20"
    assert "120 characters" in PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_7.system_template
    with pytest.raises(KeyError):
        PRODUCT_DEFECT_PROMPT_REGISTRY.get(
            name=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_7.name,
            version=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_7.version,
        )


def test_local8_guard_preserves_local5_and_is_not_runtime_selectable() -> None:
    records, prompts, scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "canary-local8-guard"
    )

    assert len(records) == 20
    assert prompts == (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8,)
    assert scope == "CANARY_LOCAL8_GUARD_20"
    assert "120 characters" in PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8.system_template
    assert (
        PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8.system_template.replace(
            " Summary is one factual sentence no longer than 120 characters.",
            "",
        )
        == PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5.system_template
    )
    assert (
        PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8.user_template
        == PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5.user_template
    )
    with pytest.raises(KeyError):
        PRODUCT_DEFECT_PROMPT_REGISTRY.get(
            name=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8.name,
            version=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8.version,
        )

    full_records, full_prompts, full_scope = screen._scope_configuration(  # pyright: ignore[reportPrivateUsage]
        "full-dev-local8-guard"
    )
    assert len(full_records) == 120
    assert full_prompts == prompts
    assert full_scope == "FULL_DEV_LOCAL8_GUARD_120"


def test_prompt_screen_retains_only_aggregate_failure_codes() -> None:
    candidate = evaluator.load_evaluation_candidate(
        evaluator.DEFAULT_MATRIX,
        "qwen38-27b-csight-q5-k-s-llama-cpp",
    )

    class MissingFieldProvider:
        @property
        def provider_metadata(self):  # type: ignore[no-untyped-def]
            return evaluator.ProviderMetadata(
                provider=candidate.provider,
                name=candidate.served_model_name,
                version=candidate.model_version,
                revision=candidate.artifact_revision,
            )

        def extract_text_v2(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            raise LLMMissingRequiredFieldError(
                provider="llama_cpp",
                message="synthetic schema failure",
            )

    records = screen._fixed_dev_canary()  # pyright: ignore[reportPrivateUsage]
    result = screen._screen_prompt(  # pyright: ignore[reportPrivateUsage]
        provider=MissingFieldProvider(),  # type: ignore[arg-type]
        candidate=candidate,
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2,
        records=records,
        record_set_digest=screen._canary_digest(records),  # pyright: ignore[reportPrivateUsage]
    )

    assert result.metrics.split is EvaluationSplit.DEV
    assert result.success_count == 0
    assert [(item.code, item.count) for item in result.failure_code_counts] == [
        ("LLM_STRUCTURED_MISSING_FIELD", 20)
    ]
    assert result.text_ambiguity_confusion.model_dump() == {
        "true_positive": 0,
        "false_positive": 0,
        "false_negative": 12,
    }
    assert result.text_ambiguity_label_confusion
    assert result.latency_breakdown.provider_p95_ms is None
    assert result.latency_breakdown.adapter_overhead_p95_ms is None
    rendered = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    assert all(str(record["customer_message"]) not in rendered for record in records.values())


def test_prompt_screen_output_requires_private_fresh_path(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    output = private / "screen.json"

    screen._prepare_output(output.resolve())  # pyright: ignore[reportPrivateUsage]
    output.write_text("{}", encoding="utf-8")
    with pytest.raises(CandidateEvaluationError, match="fresh absolute path"):
        screen._prepare_output(output.resolve())  # pyright: ignore[reportPrivateUsage]
