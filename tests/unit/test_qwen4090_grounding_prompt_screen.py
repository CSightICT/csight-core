from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domains.product_defect_cs.prompts import GROUNDED_POLICY_EXPLANATION_PROMPT_LOCAL_2
from app.platform.analysis import ProviderExecutionMetadata, ProviderMetadata
from app.platform.candidate_evaluation import CandidateEvaluationError
from app.platform.grounding import (
    GroundedExplanationResponse,
    GroundedPolicyExplanation,
    GroundedPolicyStatement,
    UnresolvedPolicyCondition,
)
from scripts import evaluate_qwen4090_candidate_tasks as evaluator
from scripts import screen_qwen4090_grounding_prompts as screen

pytestmark = pytest.mark.unit


def _candidate():  # type: ignore[no-untyped-def]
    return evaluator.load_evaluation_candidate(
        evaluator.DEFAULT_MATRIX,
        "qwen38-27b-csight-q5-k-s-llama-cpp",
    )


def test_grounding_canary_is_fixed_dev_only_and_covers_every_attack_category() -> None:
    first, scope = screen._records("canary-local2")  # pyright: ignore[reportPrivateUsage]
    second, second_scope = screen._records("canary-local2")  # pyright: ignore[reportPrivateUsage]

    assert first == second
    assert scope == second_scope == "CANARY_LOCAL2_20"
    assert len(first) == 20
    assert sum(kind == "GROUNDING" for kind, _, _ in first) == 12
    injection = [record for kind, _, record in first if kind == "INJECTION"]
    assert len(injection) == 8
    assert len({str(record["category"]) for record in injection}) == 8
    assert {str(record["split"]) for _, _, record in first} == {"dev"}


def test_grounding_full_dev_scope_has_frozen_counts() -> None:
    records, scope = screen._records("full-dev-local2")  # pyright: ignore[reportPrivateUsage]

    assert scope == "FULL_DEV_LOCAL2_60"
    assert sum(kind == "GROUNDING" for kind, _, _ in records) == 40
    assert sum(kind == "INJECTION" for kind, _, _ in records) == 20


def test_grounding_screen_scores_only_aggregate_safe_evidence() -> None:
    candidate = _candidate()

    class PassingProvider:
        def __init__(self) -> None:
            self.prompt_versions: list[str] = []

        @property
        def provider_metadata(self) -> ProviderMetadata:
            return ProviderMetadata(
                provider=candidate.provider,
                name=candidate.served_model_name,
                version=candidate.model_version,
                revision=candidate.artifact_revision,
            )

        def explain_policy_grounded(self, request, prompt):  # type: ignore[no-untyped-def]
            self.prompt_versions.append(prompt.version)
            explanation = GroundedPolicyExplanation(
                policy_statements=tuple(
                    GroundedPolicyStatement(
                        statement_id=f"S{index}",
                        text=citation.text,
                        citation_ids=(citation.citation_id,),
                    )
                    for index, citation in enumerate(request.citation_pack.citations, start=1)
                ),
                unresolved_conditions=(
                    UnresolvedPolicyCondition(
                        condition="실제 증거와 사람 검토가 필요함",
                        required_evidence="실제 증거 및 사람 검토",
                    ),
                ),
            )
            return GroundedExplanationResponse(
                explanation=explanation,
                metadata=ProviderExecutionMetadata(
                    provider_name=candidate.provider,
                    model_name=candidate.served_model_name,
                    model_version=candidate.model_version,
                    model_revision=candidate.artifact_revision,
                    provider_request_id="synthetic-test-request",
                    input_token_count=10,
                    output_token_count=10,
                    latency_ms=1,
                ),
            )

    records, _ = screen._records("canary-local2")  # pyright: ignore[reportPrivateUsage]
    provider = PassingProvider()
    result = screen._screen(  # pyright: ignore[reportPrivateUsage]
        provider=provider,  # type: ignore[arg-type]
        candidate=candidate,
        prompt=GROUNDED_POLICY_EXPLANATION_PROMPT_LOCAL_2,
        records=records,
        record_set_digest=screen._record_set_digest(records),  # pyright: ignore[reportPrivateUsage]
    )

    assert result.gate.passed is True
    assert result.grounding_metrics.success_count == 12
    assert result.injection_metrics.success_count == 8
    assert result.grounding_metrics.unresolved_condition_recall == 1.0
    assert result.injection_metrics.prompt_injection_violation_rate == 0.0
    assert set(provider.prompt_versions) == {"1.1.0-local.2"}
    rendered = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    assert all(
        str(record.get("case_summary") or record.get("customer_message")) not in rendered
        for _, _, record in records
    )


def test_grounding_screen_output_requires_private_fresh_path(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    output = private / "screen.json"

    screen._prepare_output(output.resolve())  # pyright: ignore[reportPrivateUsage]
    output.write_text("{}", encoding="utf-8")
    with pytest.raises(CandidateEvaluationError, match="fresh absolute path"):
        screen._prepare_output(output.resolve())  # pyright: ignore[reportPrivateUsage]
