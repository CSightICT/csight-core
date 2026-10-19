"""Compare two frozen Extraction prompts on a fixed synthetic Dev canary.

This is a diagnosis-only screen. It cannot open sealed Test, freeze a profile,
select a release, or change a Core model route.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.bootstrap.dependencies import build_llm_provider
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs.ambiguity_guard import (
    DEV_AMBIGUITY_GUARD_CONTENT_HASH,
    DEV_AMBIGUITY_GUARD_VERSION,
    apply_dev_ambiguity_guard,
)
from app.domains.product_defect_cs.prompts import (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_4,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_6,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_7,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8,
)
from app.platform.analysis.llm_v2 import TextAmbiguity
from app.platform.analysis.prompts import PromptManifest
from app.platform.candidate_evaluation import (
    CandidateEvaluationError,
    CandidateEvaluationProfile,
    CandidateTask,
    EvaluationCandidate,
    EvaluationSplit,
    ExtractionEvaluationMetrics,
    compute_extraction_metrics,
)
from app.platform.model_activation import ModelReleaseTask
from app.ports.llm import LLMProvider
from scripts import evaluate_qwen4090_candidate_tasks as evaluator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "evaluation/llm/qwen4090_candidate_matrix_v2.json"
_CANARY_RECORD_COUNT = 20
_FULL_DEV_RECORD_COUNT = 120
_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_PROMPTS = (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2,
)
_LOCAL4_PROMPTS = (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_4,
)
_LOCAL5_PROMPTS = (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5,
)
_LOCAL6_PROMPTS = (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_6,
)
type ReportScope = Literal[
    "CANARY_20",
    "FULL_DEV_120",
    "CANARY_LOCAL4_20",
    "FULL_DEV_LOCAL4_120",
    "CANARY_LOCAL5_20",
    "FULL_DEV_LOCAL5_120",
    "CANARY_LOCAL6_20",
    "FULL_DEV_LOCAL6_120",
    "DIAGNOSE_LOCAL5_20",
    "CANARY_LOCAL5_GUARD_20",
    "CANARY_LOCAL7_GUARD_20",
    "CANARY_LOCAL8_GUARD_20",
    "FULL_DEV_LOCAL8_GUARD_120",
]


class _StrictReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ConfusionCounts(_StrictReport):
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)


class AmbiguityLabelConfusion(_StrictReport):
    label: TextAmbiguity
    counts: ConfusionCounts


class LatencyBreakdown(_StrictReport):
    end_to_end_p50_ms: float = Field(ge=0)
    end_to_end_p95_ms: float = Field(ge=0)
    provider_p50_ms: float | None = Field(default=None, ge=0)
    provider_p95_ms: float | None = Field(default=None, ge=0)
    adapter_overhead_p50_ms: float | None = Field(default=None, ge=0)
    adapter_overhead_p95_ms: float | None = Field(default=None, ge=0)


class PromptScreenResult(_StrictReport):
    variant_id: str
    prompt_version: str
    prompt_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_digest: str = Field(pattern=_DIGEST_PATTERN)
    scoring_profile_digest: str = Field(pattern=_DIGEST_PATTERN)
    postprocessor_version: str | None = None
    postprocessor_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    success_count: int = Field(ge=0, le=_FULL_DEV_RECORD_COUNT)
    failure_code_counts: tuple[evaluator.FailureCodeCount, ...]
    metrics: ExtractionEvaluationMetrics
    text_ambiguity_confusion: ConfusionCounts
    text_ambiguity_label_confusion: tuple[AmbiguityLabelConfusion, ...]
    latency_breakdown: LatencyBreakdown
    result_set_digest: str = Field(pattern=_DIGEST_PATTERN)
    raw_provider_response_retained: Literal[False] = False
    provider_request_id_retained: Literal[False] = False
    typed_prediction_retained: Literal[False] = False


class ExtractionPromptScreenReport(_StrictReport):
    schema_version: Literal["qwen4090_extraction_prompt_screen/1.3.0"] = (
        "qwen4090_extraction_prompt_screen/1.3.0"
    )
    status: Literal["COMPLETE"] = "COMPLETE"
    candidate_id: str
    candidate_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    provider_metadata_digest: str = Field(pattern=_DIGEST_PATTERN)
    record_count: int = Field(ge=_CANARY_RECORD_COUNT, le=_FULL_DEV_RECORD_COUNT)
    record_set_digest: str = Field(pattern=_DIGEST_PATTERN)
    prompt_results: tuple[PromptScreenResult, ...] = Field(min_length=1, max_length=2)
    structural_leader_prompt_version: str
    structural_leader_variant_id: str
    started_at: datetime
    completed_at: datetime
    split: Literal["dev"] = "dev"
    scope: ReportScope
    data_provenance: Literal["SYNTHETIC_EVALUATION"] = "SYNTHETIC_EVALUATION"
    diagnosis_only: Literal[True] = True
    qualification_decision_created: Literal[False] = False
    frozen_profile_created: Literal[False] = False
    sealed_test_used: Literal[False] = False
    core_route_changed: Literal[False] = False
    external_business_actions_performed: Literal[False] = False
    raw_inputs_retained: Literal[False] = False
    raw_predictions_retained: Literal[False] = False


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--scope",
        choices=(
            "canary20",
            "full-dev-local2",
            "canary-local4",
            "full-dev-local4",
            "canary-local5",
            "full-dev-local5",
            "canary-local6",
            "full-dev-local6",
            "diagnose-local5",
            "canary-local5-guard",
            "canary-local7-guard",
            "canary-local8-guard",
            "full-dev-local8-guard",
        ),
        default="canary20",
    )
    return parser.parse_args()


def _require_private_file(path: Path, *, label: str) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise CandidateEvaluationError(f"{label} must be an absolute regular file")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise CandidateEvaluationError(f"{label} must have owner-only mode 600")


def _prepare_output(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or path.exists():
        raise CandidateEvaluationError("screen output must be a fresh absolute path")
    if path.parent.exists():
        if path.parent.is_symlink() or not path.parent.is_dir():
            raise CandidateEvaluationError("screen output parent must be a real directory")
        if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
            raise CandidateEvaluationError("screen output parent must have owner-only mode 700")
    else:
        path.parent.mkdir(parents=True, mode=0o700)
        os.chmod(path.parent, 0o700)


def _fixed_dev_canary() -> dict[str, dict[str, Any]]:
    gold = evaluator._load_gold_records(  # pyright: ignore[reportPrivateUsage]
        evaluator.EXTRACTION_DATASET,
        EvaluationSplit.DEV,
    )
    ordered = sorted(gold.items(), key=lambda item: str(item[1]["record_id"]))
    selected = dict(ordered[:_CANARY_RECORD_COUNT])
    if len(selected) != _CANARY_RECORD_COUNT:
        raise CandidateEvaluationError("the frozen Dev dataset lacks the 20-record canary")
    return selected


def _full_dev_records() -> dict[str, dict[str, Any]]:
    records = evaluator._load_gold_records(  # pyright: ignore[reportPrivateUsage]
        evaluator.EXTRACTION_DATASET,
        EvaluationSplit.DEV,
    )
    if len(records) != _FULL_DEV_RECORD_COUNT:
        raise CandidateEvaluationError("the frozen Extraction Dev split is not exactly 120 records")
    return records


def _scope_configuration(
    requested_scope: str,
) -> tuple[dict[str, dict[str, Any]], tuple[PromptManifest, ...], ReportScope]:
    if requested_scope == "canary20":
        return _fixed_dev_canary(), _PROMPTS, "CANARY_20"
    if requested_scope == "full-dev-local2":
        return (
            _full_dev_records(),
            (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_2,),
            "FULL_DEV_120",
        )
    if requested_scope == "canary-local4":
        return _fixed_dev_canary(), _LOCAL4_PROMPTS, "CANARY_LOCAL4_20"
    if requested_scope == "full-dev-local4":
        return (
            _full_dev_records(),
            (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_4,),
            "FULL_DEV_LOCAL4_120",
        )
    if requested_scope == "canary-local5":
        return _fixed_dev_canary(), _LOCAL5_PROMPTS, "CANARY_LOCAL5_20"
    if requested_scope == "full-dev-local5":
        return (
            _full_dev_records(),
            (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5,),
            "FULL_DEV_LOCAL5_120",
        )
    if requested_scope == "canary-local6":
        return _fixed_dev_canary(), _LOCAL6_PROMPTS, "CANARY_LOCAL6_20"
    if requested_scope == "full-dev-local6":
        return (
            _full_dev_records(),
            (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_6,),
            "FULL_DEV_LOCAL6_120",
        )
    if requested_scope == "diagnose-local5":
        return (
            _fixed_dev_canary(),
            (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5,),
            "DIAGNOSE_LOCAL5_20",
        )
    if requested_scope == "canary-local5-guard":
        return (
            _fixed_dev_canary(),
            (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_5,),
            "CANARY_LOCAL5_GUARD_20",
        )
    if requested_scope == "canary-local7-guard":
        return (
            _fixed_dev_canary(),
            (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_7,),
            "CANARY_LOCAL7_GUARD_20",
        )
    if requested_scope == "canary-local8-guard":
        return (
            _fixed_dev_canary(),
            (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8,),
            "CANARY_LOCAL8_GUARD_20",
        )
    if requested_scope == "full-dev-local8-guard":
        return (
            _full_dev_records(),
            (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_8,),
            "FULL_DEV_LOCAL8_GUARD_120",
        )
    raise CandidateEvaluationError("unsupported Extraction prompt screen scope")


def _canary_digest(records: dict[str, dict[str, Any]]) -> str:
    return evaluator._canonical_payload_digest(  # pyright: ignore[reportPrivateUsage]
        tuple(
            {
                "record_id_hash": record_hash,
                "record_digest": evaluator._canonical_payload_digest(  # pyright: ignore[reportPrivateUsage]
                    record
                ),
            }
            for record_hash, record in sorted(records.items())
        )
    )


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1)]


def _confusion_counts(
    observations: tuple[evaluator.ExtractionEvaluationObservation, ...],
) -> ConfusionCounts:
    return ConfusionCounts(
        true_positive=sum(item.text_ambiguity_tp for item in observations),
        false_positive=sum(item.text_ambiguity_fp for item in observations),
        false_negative=sum(item.text_ambiguity_fn for item in observations),
    )


def _label_confusion_counts(
    raw: tuple[evaluator.ExtractionRawObservation, ...],
    records: dict[str, dict[str, Any]],
) -> tuple[AmbiguityLabelConfusion, ...]:
    aggregate = {label: {"tp": 0, "fp": 0, "fn": 0} for label in TextAmbiguity}
    for item in raw:
        expected = {
            TextAmbiguity(str(value))
            for value in records[item.record_id_hash]["expected"]["text_ambiguities"]
        }
        actual = (
            set(item.provider_output.result.text_ambiguities)
            if item.provider_output is not None
            else set()
        )
        for label in TextAmbiguity:
            aggregate[label]["tp"] += int(label in expected and label in actual)
            aggregate[label]["fp"] += int(label not in expected and label in actual)
            aggregate[label]["fn"] += int(label in expected and label not in actual)
    return tuple(
        AmbiguityLabelConfusion(
            label=label,
            counts=ConfusionCounts(
                true_positive=counts["tp"],
                false_positive=counts["fp"],
                false_negative=counts["fn"],
            ),
        )
        for label, counts in aggregate.items()
        if any(counts.values())
    )


def _latency_breakdown(
    observations: tuple[evaluator.ExtractionEvaluationObservation, ...],
) -> LatencyBreakdown:
    end_to_end = [item.latency_ms for item in observations]
    with_provider = tuple(item for item in observations if item.provider_latency_ms is not None)
    provider = [float(item.provider_latency_ms or 0) for item in with_provider]
    overhead = [
        max(0.0, item.latency_ms - float(item.provider_latency_ms or 0)) for item in with_provider
    ]
    return LatencyBreakdown(
        end_to_end_p50_ms=round(statistics.median(end_to_end), 3),
        end_to_end_p95_ms=round(_percentile(end_to_end, 0.95), 3),
        provider_p50_ms=round(statistics.median(provider), 3) if provider else None,
        provider_p95_ms=round(_percentile(provider, 0.95), 3) if provider else None,
        adapter_overhead_p50_ms=round(statistics.median(overhead), 3) if overhead else None,
        adapter_overhead_p95_ms=round(_percentile(overhead, 0.95), 3) if overhead else None,
    )


def _score_raw(
    *,
    candidate: EvaluationCandidate,
    prompt: PromptManifest,
    records: dict[str, dict[str, Any]],
    record_set_digest: str,
    raw: tuple[evaluator.ExtractionRawObservation, ...],
    variant_id: str,
    postprocessor_version: str | None = None,
    postprocessor_content_hash: str | None = None,
) -> PromptScreenResult:
    profile = CandidateEvaluationProfile.create(
        candidate=candidate,
        task=CandidateTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
        prompt=prompt,
        dataset_digest=record_set_digest,
    )
    derived = tuple(
        evaluator._derive_extraction_observation(  # pyright: ignore[reportPrivateUsage]
            item,
            record=records[item.record_id_hash],
            candidate=candidate,
            prompt=prompt,
        )
        for item in raw
    )
    metrics = compute_extraction_metrics(derived)
    return PromptScreenResult(
        variant_id=variant_id,
        prompt_version=prompt.version,
        prompt_content_hash=prompt.content_hash,
        profile_digest=profile.profile_digest,
        scoring_profile_digest=evaluator._canonical_payload_digest(  # pyright: ignore[reportPrivateUsage]
            {
                "profile_digest": profile.profile_digest,
                "postprocessor_version": postprocessor_version,
                "postprocessor_content_hash": postprocessor_content_hash,
            }
        ),
        postprocessor_version=postprocessor_version,
        postprocessor_content_hash=postprocessor_content_hash,
        success_count=metrics.success_count,
        failure_code_counts=evaluator._failure_code_counts(raw),  # pyright: ignore[reportPrivateUsage]
        metrics=metrics,
        text_ambiguity_confusion=_confusion_counts(derived),
        text_ambiguity_label_confusion=_label_confusion_counts(raw, records),
        latency_breakdown=_latency_breakdown(derived),
        result_set_digest=evaluator._set_digest(  # pyright: ignore[reportPrivateUsage]
            raw,
            "result_digest",
        ),
    )


def _screen_prompt(
    *,
    provider: LLMProvider,
    candidate: EvaluationCandidate,
    prompt: PromptManifest,
    records: dict[str, dict[str, Any]],
    record_set_digest: str,
) -> PromptScreenResult:
    raw = evaluator.generate_extraction_raw_observations(
        provider,
        candidate=candidate,
        split=EvaluationSplit.DEV,
        prompt=prompt,
        records=records,
    )
    return _score_raw(
        candidate=candidate,
        prompt=prompt,
        records=records,
        record_set_digest=record_set_digest,
        raw=raw,
        variant_id=prompt.version,
    )


def _apply_guard_to_raw(
    raw: tuple[evaluator.ExtractionRawObservation, ...],
    records: dict[str, dict[str, Any]],
) -> tuple[evaluator.ExtractionRawObservation, ...]:
    guarded: list[evaluator.ExtractionRawObservation] = []
    for item in raw:
        if item.provider_output is None:
            guarded.append(item)
            continue
        result = apply_dev_ambiguity_guard(
            item.provider_output.result,
            customer_message=str(records[item.record_id_hash]["customer_message"]),
        )
        provider_output = item.provider_output.model_copy(update={"result": result})
        updated = item.model_copy(
            update={
                "provider_output": provider_output,
                "result_digest": "sha256:" + "0" * 64,
            }
        )
        guarded.append(
            updated.model_copy(
                update={
                    "result_digest": evaluator._extraction_result_digest(  # pyright: ignore[reportPrivateUsage]
                        updated
                    )
                }
            )
        )
    return tuple(guarded)


def _screen_guard_variants(
    *,
    provider: LLMProvider,
    candidate: EvaluationCandidate,
    prompt: PromptManifest,
    records: dict[str, dict[str, Any]],
    record_set_digest: str,
) -> tuple[PromptScreenResult, PromptScreenResult]:
    raw = evaluator.generate_extraction_raw_observations(
        provider,
        candidate=candidate,
        split=EvaluationSplit.DEV,
        prompt=prompt,
        records=records,
    )
    baseline = _score_raw(
        candidate=candidate,
        prompt=prompt,
        records=records,
        record_set_digest=record_set_digest,
        raw=raw,
        variant_id=prompt.version,
    )
    guarded = _score_raw(
        candidate=candidate,
        prompt=prompt,
        records=records,
        record_set_digest=record_set_digest,
        raw=_apply_guard_to_raw(raw, records),
        variant_id=f"{prompt.version}+{DEV_AMBIGUITY_GUARD_VERSION}",
        postprocessor_version=DEV_AMBIGUITY_GUARD_VERSION,
        postprocessor_content_hash=DEV_AMBIGUITY_GUARD_CONTENT_HASH,
    )
    return baseline, guarded


def _structural_leader(
    results: tuple[PromptScreenResult, ...],
) -> PromptScreenResult:
    safe = tuple(
        item
        for item in results
        if item.metrics.prompt_injection_violation_rate == 0
        and item.metrics.reasoning_leakage_rate == 0
        and item.metrics.forbidden_field_rate == 0
    )
    pool = safe or results
    return max(
        pool,
        key=lambda item: (
            item.success_count,
            item.metrics.exact_quote_rate,
            item.metrics.issue_type_f1,
            item.metrics.requested_action_set_f1,
            item.metrics.text_ambiguity_set_f1,
            -item.metrics.latency_p95_ms,
            item.prompt_version == PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.version,
        ),
    )


def main() -> int:
    arguments = _arguments()
    _require_private_file(arguments.env_file, label="runtime env")
    _prepare_output(arguments.output)
    candidate = evaluator.load_evaluation_candidate(arguments.matrix, arguments.candidate_id)
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    if settings.llm_provider != "llama_cpp":
        raise CandidateEvaluationError("prompt screen requires LLM_PROVIDER=llama_cpp")
    provider = build_llm_provider(
        settings,
        ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
    )
    evaluator.validate_provider_identity(candidate, provider.provider_metadata)
    records, prompts, scope = _scope_configuration(arguments.scope)
    record_set_digest = _canary_digest(records)
    started_at = datetime.now(UTC)
    if scope in {
        "CANARY_LOCAL5_GUARD_20",
        "CANARY_LOCAL7_GUARD_20",
        "CANARY_LOCAL8_GUARD_20",
        "FULL_DEV_LOCAL8_GUARD_120",
    }:
        results = _screen_guard_variants(
            provider=provider,
            candidate=candidate,
            prompt=prompts[0],
            records=records,
            record_set_digest=record_set_digest,
        )
    else:
        results = tuple(
            _screen_prompt(
                provider=provider,
                candidate=candidate,
                prompt=prompt,
                records=records,
                record_set_digest=record_set_digest,
            )
            for prompt in prompts
        )
    leader = _structural_leader(results)
    report = ExtractionPromptScreenReport(
        candidate_id=candidate.candidate_id,
        candidate_identity_digest=candidate.identity_digest,
        runtime_identity_digest=candidate.runtime_identity_digest,
        provider_metadata_digest=evaluator._canonical_payload_digest(  # pyright: ignore[reportPrivateUsage]
            provider.provider_metadata
        ),
        record_count=len(records),
        record_set_digest=record_set_digest,
        prompt_results=results,
        structural_leader_prompt_version=leader.prompt_version,
        structural_leader_variant_id=leader.variant_id,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        scope=scope,
    )
    arguments.output.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    os.chmod(arguments.output, 0o600)
    print(
        "EXTRACTION_PROMPT_SCREEN_COMPLETE "
        f"candidate={candidate.candidate_id} leader={report.structural_leader_variant_id} "
        f"output={arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
