"""Screen one Grounding prompt on fixed synthetic Q5 Dev records.

This smoke-first diagnostic cannot open sealed Test, freeze or activate a
profile, select a release, or route Core traffic.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from app.bootstrap.dependencies import build_llm_provider
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs.prompts import GROUNDED_POLICY_EXPLANATION_PROMPT_LOCAL_2
from app.platform.analysis.prompts import PromptManifest
from app.platform.candidate_evaluation import (
    CandidateEvaluationError,
    CandidateEvaluationProfile,
    CandidateTask,
    EvaluationCandidate,
    EvaluationGateResult,
    EvaluationSplit,
    GroundingEvaluationMetrics,
    InjectionEvaluationMetrics,
    assess_grounding_candidate,
    compute_grounding_metrics,
)
from app.platform.model_activation import ModelReleaseTask
from app.ports.llm import LLMProvider
from scripts import evaluate_qwen4090_candidate_tasks as evaluator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "evaluation/llm/qwen4090_candidate_matrix_v2.json"
_CANARY_GROUNDING_COUNT = 12
_CANARY_INJECTION_COUNT = 8
_FULL_GROUNDING_COUNT = 40
_FULL_INJECTION_COUNT = 20
_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
type ReportScope = Literal["CANARY_LOCAL2_20", "FULL_DEV_LOCAL2_60"]
type SelectedRecord = tuple[Literal["GROUNDING", "INJECTION"], str, dict[str, Any]]


class _StrictReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class GroundingPromptScreenResult(_StrictReport):
    prompt_version: str
    prompt_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_digest: str = Field(pattern=_DIGEST_PATTERN)
    grounding_metrics: GroundingEvaluationMetrics
    injection_metrics: InjectionEvaluationMetrics
    gate: EvaluationGateResult
    failure_code_counts: tuple[evaluator.FailureCodeCount, ...]
    result_set_digest: str = Field(pattern=_DIGEST_PATTERN)
    raw_provider_response_retained: Literal[False] = False
    provider_request_id_retained: Literal[False] = False
    typed_prediction_retained: Literal[False] = False


class GroundingPromptScreenReport(_StrictReport):
    schema_version: Literal["qwen4090_grounding_prompt_screen/1.0.0"] = (
        "qwen4090_grounding_prompt_screen/1.0.0"
    )
    status: Literal["COMPLETE"] = "COMPLETE"
    candidate_id: str
    candidate_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    provider_metadata_digest: str = Field(pattern=_DIGEST_PATTERN)
    grounding_record_count: int = Field(ge=_CANARY_GROUNDING_COUNT, le=_FULL_GROUNDING_COUNT)
    injection_record_count: int = Field(ge=_CANARY_INJECTION_COUNT, le=_FULL_INJECTION_COUNT)
    record_set_digest: str = Field(pattern=_DIGEST_PATTERN)
    result: GroundingPromptScreenResult
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
        choices=("canary-local2", "full-dev-local2"),
        default="canary-local2",
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


def _ordered_records(path: Path) -> tuple[tuple[str, dict[str, Any]], ...]:
    records = evaluator._load_gold_records(  # pyright: ignore[reportPrivateUsage]
        path,
        EvaluationSplit.DEV,
    )
    return tuple(sorted(records.items(), key=lambda item: str(item[1]["record_id"])))


def _records(scope: str) -> tuple[tuple[SelectedRecord, ...], ReportScope]:
    grounding = _ordered_records(evaluator.GROUNDING_DATASET)
    injection = _ordered_records(evaluator.INJECTION_DATASET)
    if len(grounding) != _FULL_GROUNDING_COUNT or len(injection) != _FULL_INJECTION_COUNT:
        raise CandidateEvaluationError("the frozen Grounding Dev split has unexpected counts")
    if scope == "full-dev-local2":
        full_records = tuple(
            cast(SelectedRecord, ("GROUNDING", key, value)) for key, value in grounding
        ) + tuple(cast(SelectedRecord, ("INJECTION", key, value)) for key, value in injection)
        return (
            full_records,
            "FULL_DEV_LOCAL2_60",
        )
    selected_injection: list[tuple[str, dict[str, Any]]] = []
    seen_categories: set[str] = set()
    for item in injection:
        category = str(item[1]["category"])
        if category in seen_categories:
            continue
        seen_categories.add(category)
        selected_injection.append(item)
    if len(selected_injection) != _CANARY_INJECTION_COUNT:
        raise CandidateEvaluationError("the frozen injection Dev split lacks eight categories")
    canary_records = tuple(
        cast(SelectedRecord, ("GROUNDING", key, value))
        for key, value in grounding[:_CANARY_GROUNDING_COUNT]
    ) + tuple(cast(SelectedRecord, ("INJECTION", key, value)) for key, value in selected_injection)
    return canary_records, "CANARY_LOCAL2_20"


def _record_set_digest(records: tuple[SelectedRecord, ...]) -> str:
    return evaluator._canonical_payload_digest(  # pyright: ignore[reportPrivateUsage]
        tuple(
            {
                "kind": kind,
                "record_id_hash": record_hash,
                "record_digest": evaluator._canonical_payload_digest(  # pyright: ignore[reportPrivateUsage]
                    record
                ),
            }
            for kind, record_hash, record in records
        )
    )


def _screen(
    *,
    provider: LLMProvider,
    candidate: EvaluationCandidate,
    prompt: PromptManifest,
    records: tuple[SelectedRecord, ...],
    record_set_digest: str,
) -> GroundingPromptScreenResult:
    profile = CandidateEvaluationProfile.create(
        candidate=candidate,
        task=CandidateTask.GROUNDED_POLICY_EXPLANATION_V1,
        prompt=prompt,
        dataset_digest=record_set_digest,
    )
    raw = evaluator.generate_grounding_raw_observations(
        provider,
        candidate=candidate,
        split=EvaluationSplit.DEV,
        prompt=prompt,
        records=records,
    )
    clause_registry = evaluator._load_clause_registry()  # pyright: ignore[reportPrivateUsage]
    selected = {(kind, key): record for kind, key, record in records}
    derived = tuple(
        evaluator._derive_grounding_observation(  # pyright: ignore[reportPrivateUsage]
            item,
            record=selected[(item.kind, item.record_id_hash)],
            candidate=candidate,
            clause_registry=clause_registry,
            prompt=prompt,
        )
        for item in raw
    )
    grounding_metrics, injection_metrics = compute_grounding_metrics(derived)
    return GroundingPromptScreenResult(
        prompt_version=prompt.version,
        prompt_content_hash=prompt.content_hash,
        profile_digest=profile.profile_digest,
        grounding_metrics=grounding_metrics,
        injection_metrics=injection_metrics,
        gate=assess_grounding_candidate(grounding_metrics, injection_metrics),
        failure_code_counts=evaluator._failure_code_counts(raw),  # pyright: ignore[reportPrivateUsage]
        result_set_digest=evaluator._set_digest(  # pyright: ignore[reportPrivateUsage]
            raw,
            "result_digest",
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
    provider = build_llm_provider(settings, ModelReleaseTask.GROUNDED_POLICY_EXPLANATION_V1)
    evaluator.validate_provider_identity(candidate, provider.provider_metadata)
    records, scope = _records(arguments.scope)
    record_set_digest = _record_set_digest(records)
    started_at = datetime.now(UTC)
    result = _screen(
        provider=provider,
        candidate=candidate,
        prompt=GROUNDED_POLICY_EXPLANATION_PROMPT_LOCAL_2,
        records=records,
        record_set_digest=record_set_digest,
    )
    report = GroundingPromptScreenReport(
        candidate_id=candidate.candidate_id,
        candidate_identity_digest=candidate.identity_digest,
        runtime_identity_digest=candidate.runtime_identity_digest,
        provider_metadata_digest=evaluator._canonical_payload_digest(  # pyright: ignore[reportPrivateUsage]
            provider.provider_metadata
        ),
        grounding_record_count=result.grounding_metrics.record_count,
        injection_record_count=result.injection_metrics.record_count,
        record_set_digest=record_set_digest,
        result=result,
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
        "GROUNDING_PROMPT_SCREEN_COMPLETE "
        f"candidate={candidate.candidate_id} passed={result.gate.passed} "
        f"output={arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
