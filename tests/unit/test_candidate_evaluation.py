from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Never

import pytest
from pydantic import ValidationError

from app.domains.product_defect_cs.prompts import (
    GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1,
    POLICY_QUERY_BUILDER_PROMPT_V1_1,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
)
from app.platform.analysis import ProviderMetadata
from app.platform.analysis.enums import ExtractionIssueType
from app.platform.analysis.llm_v2 import (
    ExtractedActionV2,
    LLMTextClaimV2,
    LLMTextExtractionResultV2,
    RequestedActionItemV2,
)
from app.platform.candidate_evaluation import (
    CandidateEvaluationError,
    CandidateEvaluationProfile,
    CandidatePublicationState,
    CandidateQuantizationVariant,
    CandidateSelectionStatus,
    CandidateTask,
    EvaluationCandidate,
    EvaluationSplit,
    ExtractionEvaluationMetrics,
    GroundingEvaluationObservation,
    QueryEvaluationMetrics,
    QueryEvaluationObservation,
    QueryRetrievalDiagnostics,
    ThreeTaskDevResult,
    assess_grounding_candidate,
    assess_query_candidate,
    authorize_sealed_test,
    canonical_digest,
    compute_grounding_metrics,
    compute_query_metrics,
    compute_query_retrieval_diagnostics,
    freeze_evaluation_profile,
    hash_identifier,
    require_complete_record_coverage,
    select_three_task_dev_winner,
    validate_frozen_evaluation_evidence,
    validate_provider_identity,
)
from app.platform.grounding import (
    CitationAllowlistViolationError,
    GroundedExplanationInvalidOutputError,
    GroundedPolicyExplanation,
    GroundedPolicyStatement,
    UnresolvedPolicyCondition,
)
from app.platform.policy_reference import ClauseType
from app.platform.query_builder import (
    PolicyQuery,
    PolicyQueryBuilderInvalidOutputError,
    PolicyQueryPlan,
    PolicyQueryPurpose,
    QueryFilterHints,
)
from scripts import evaluate_qwen4090_candidate_tasks as candidate_task_evaluator

DIGEST = "sha256:" + "a" * 64
REVISION = "1" * 40


def _candidate() -> EvaluationCandidate:
    return EvaluationCandidate(
        candidate_id="qwen38-csight-q4km",
        provider="llama_cpp",
        artifact="local/Qwen3.8-27B-GGUF",
        publication_state=CandidatePublicationState.PUBLISHED,
        artifact_revision=REVISION,
        artifact_content_digest=DIGEST,
        artifact_weight_bytes=1_000_000,
        quantization_recipe_digest=DIGEST,
        quantization_variant=CandidateQuantizationVariant.MIXED_Q4_Q6,
        candidate_matrix_digest=DIGEST,
        comparison_contract_digest=DIGEST,
        served_model_name="csight-qwen38-q4km",
        model_version="Qwen3.8-27B-CSight-Q4KM",
        runtime_identity_digest=DIGEST,
        tokenizer_config_digest=DIGEST,
        chat_template_digest=DIGEST,
        max_context_tokens=4096,
        max_output_tokens=512,
    )


def _provider_metadata(candidate: EvaluationCandidate) -> ProviderMetadata:
    return ProviderMetadata(
        provider=candidate.provider,
        name=candidate.served_model_name,
        version=candidate.model_version,
        revision=candidate.artifact_revision,
    )


def _query_gold(record_id: str, relevant_clause_id: str) -> dict[str, object]:
    return {
        "record_id": record_id,
        "split": "dev",
        "tenant_id": "csight-demo-brand",
        "as_of_date": "2026-02-01",
        "customer_message": "합성 문의",
        "gold_extraction_v2": {
            "issue_types": ["BREAKAGE"],
            "requested_actions": [],
            "text_ambiguities": [],
        },
        "expected_completeness": {
            "system_missing_information": [],
            "action_consistency": "BOTH_UNSPECIFIED",
        },
        "case_context": {
            "product_category": "GENERAL",
            "days_since_purchase": 3,
            "available_image_count": 1,
            "exception_context": False,
            "escalation_context": False,
        },
        "expected_query_purposes": ["PRIMARY_POLICY"],
        "expected_filter_hints": {
            "policy_types": ["RETURN_EXCHANGE"],
            "product_categories": ["GENERAL"],
            "defect_types": ["BREAKAGE"],
            "clause_types": ["RULE"],
        },
        "relevant_clause_ids": [relevant_clause_id],
        "hard_negative_clause_ids": ["POLICY-BRD-002:2.0.0:C1"],
        "forbidden_clause_ids": ["POLICY-RTL-001:2.0.0:C1"],
        "forbidden_query_fields": ["tenant_id"],
        "scenario_tags": ["STANDARD"],
    }


def _query_profile(candidate: EvaluationCandidate) -> CandidateEvaluationProfile:
    return CandidateEvaluationProfile.create(
        candidate=candidate,
        task=CandidateTask.POLICY_QUERY_BUILDER_V1,
        prompt=POLICY_QUERY_BUILDER_PROMPT_V1_1,
        dataset_digest=DIGEST,
        retrieval_corpus_digest=DIGEST,
    )


def _raw_query_observation(
    *,
    candidate: EvaluationCandidate,
    profile: CandidateEvaluationProfile,
    record: dict[str, object],
    hit_clause_id: str,
    hit_row_digest: str,
) -> candidate_task_evaluator.QueryRawObservation:
    plan = PolicyQueryPlan(
        queries=(
            PolicyQuery(
                query_id="Q1",
                purpose=PolicyQueryPurpose.PRIMARY_POLICY,
                text=f"BREAKAGE policy {record['record_id']}",
            ),
        ),
        filter_hints=QueryFilterHints(
            policy_types=("RETURN_EXCHANGE",),
            product_categories=("GENERAL",),
            defect_types=(ExtractionIssueType.BREAKAGE,),
            clause_types=(ClauseType.RULE,),
        ),
    )
    provider_output = candidate_task_evaluator.QueryProviderOutput(
        plan=plan,
        metadata=candidate_task_evaluator.PrivacySafeProviderExecutionMetadata(
            provider_name=candidate.provider,
            model_name=candidate.served_model_name,
            model_version=candidate.model_version,
            model_revision=candidate.artifact_revision,
            input_token_count=10,
            output_token_count=5,
            latency_ms=8,
        ),
    )
    query = plan.queries[0]
    retrieval = candidate_task_evaluator.RetrievalResultOutput(
        query_id=query.query_id,
        request_digest=candidate_task_evaluator._retrieval_request_digest(  # pyright: ignore[reportPrivateUsage]
            record=record,
            query_id=query.query_id,
            query_text=query.text,
            retrieval_corpus_digest=profile.retrieval_corpus_digest or "",
        ),
        result_digest=DIGEST,
        hits=(
            candidate_task_evaluator.RetrievalHitOutput(
                rank=1,
                clause_id_hash=hash_identifier(hit_clause_id),
                clause_record_digest=hit_row_digest,
            ),
        ),
    )
    retrieval = retrieval.model_copy(
        update={
            "result_digest": candidate_task_evaluator._retrieval_result_digest(  # pyright: ignore[reportPrivateUsage]
                retrieval
            )
        }
    )
    raw = candidate_task_evaluator.QueryRawObservation(
        record_id_hash=hash_identifier(str(record["record_id"])),
        split=EvaluationSplit.DEV,
        status="SUCCEEDED",
        request_digest=candidate_task_evaluator._provider_request_digest(  # pyright: ignore[reportPrivateUsage]
            task=CandidateTask.POLICY_QUERY_BUILDER_V1,
            request=candidate_task_evaluator._query_input(record),  # pyright: ignore[reportPrivateUsage]
            prompt=POLICY_QUERY_BUILDER_PROMPT_V1_1,
        ),
        result_digest=DIGEST,
        latency_ms=10,
        provider_output=provider_output,
        retrieval_results=(retrieval,),
        fused_hits=retrieval.hits,
    )
    return raw.model_copy(
        update={
            "result_digest": candidate_task_evaluator._query_result_digest(  # pyright: ignore[reportPrivateUsage]
                raw
            )
        }
    )


def _write_observation_set(
    path: Path,
    *,
    candidate: EvaluationCandidate,
    profile: CandidateEvaluationProfile,
    observations: tuple[candidate_task_evaluator.QueryRawObservation, ...],
) -> None:
    metadata = _provider_metadata(candidate)
    manifest = candidate_task_evaluator.CandidateObservationSetManifest(
        task=CandidateTask.POLICY_QUERY_BUILDER_V1,
        split=EvaluationSplit.DEV,
        candidate_identity_digest=candidate.identity_digest,
        profile_digest=profile.profile_digest,
        runtime_identity_digest=candidate.runtime_identity_digest,
        provider_metadata=metadata,
        provider_metadata_digest=candidate_task_evaluator._canonical_payload_digest(  # pyright: ignore[reportPrivateUsage]
            metadata
        ),
        record_count=len(observations),
        request_set_digest=candidate_task_evaluator._set_digest(  # pyright: ignore[reportPrivateUsage]
            observations, "request_digest"
        ),
        result_set_digest=candidate_task_evaluator._set_digest(  # pyright: ignore[reportPrivateUsage]
            observations, "result_digest"
        ),
        capture_origin="LIVE_PROVIDER",
    )
    path.write_text(
        "\n".join((manifest.model_dump_json(), *(item.model_dump_json() for item in observations)))
        + "\n",
        encoding="utf-8",
    )


def _query_observation(split: EvaluationSplit = EvaluationSplit.DEV) -> QueryEvaluationObservation:
    relevant = hash_identifier("POLICY:1:C1")
    return QueryEvaluationObservation(
        record_id_hash=hash_identifier("query-1"),
        split=split,
        success=True,
        latency_ms=10,
        provider_latency_ms=8,
        input_tokens=10,
        output_tokens=5,
        relevant_clause_ids_hashes=(relevant,),
        hard_negative_clause_ids_hashes=(hash_identifier("POLICY:1:C9"),),
        hit_clause_ids_hashes=(relevant,),
        schema_valid=True,
        pydantic_valid=True,
        query_purpose_tp=1,
        query_purpose_fp=0,
        query_purpose_fn=0,
        filter_hint_tp=1,
        filter_hint_fp=0,
        filter_hint_fn=0,
        empty_query=False,
        duplicate_query=False,
        forbidden_field=False,
        prompt_injection_violation=False,
        reasoning_leakage=False,
    )


def _grounding_observations() -> tuple[GroundingEvaluationObservation, ...]:
    return (
        GroundingEvaluationObservation(
            record_id_hash=hash_identifier("ground-1"),
            split=EvaluationSplit.DEV,
            kind="GROUNDING",
            success=True,
            latency_ms=20,
            schema_valid=True,
            pydantic_valid=True,
            citation_tp=1,
            citation_fp=0,
            citation_fn=0,
            statement_count=1,
            cited_statement_count=1,
            required_fact_coverage=1,
            unresolved_condition_recall=1,
            deterministic_replay=True,
        ),
        GroundingEvaluationObservation(
            record_id_hash=hash_identifier("inject-1"),
            split=EvaluationSplit.DEV,
            kind="INJECTION",
            success=True,
            latency_ms=10,
            schema_valid=True,
            pydantic_valid=True,
        ),
    )


@pytest.mark.unit
def test_provider_identity_is_implementation_neutral_but_exact() -> None:
    candidate = _candidate()
    validate_provider_identity(
        candidate,
        ProviderMetadata(
            provider="llama_cpp",
            name=candidate.served_model_name,
            version=candidate.model_version,
            revision=candidate.artifact_revision,
        ),
    )
    with pytest.raises(CandidateEvaluationError, match="identity"):
        validate_provider_identity(
            candidate,
            ProviderMetadata(
                provider="vllm",
                name=candidate.served_model_name,
                version=candidate.model_version,
                revision=candidate.artifact_revision,
            ),
        )


@pytest.mark.unit
def test_query_candidate_must_meet_the_frozen_raw_baseline() -> None:
    metrics = compute_query_metrics((_query_observation(),))
    gate = assess_query_candidate(metrics)
    assert gate.passed is True
    limits = {item.name: item.limit for item in gate.checks}
    assert limits["recall_at_10"] == ">=0.975"
    assert limits["exact_gold_coverage_at_10"] == ">=0.85"
    assert limits["mrr_at_10"] == ">=0.739236"
    assert limits["ndcg_at_10"] == ">=0.741392"


@pytest.mark.unit
def test_candidate_gates_require_every_record_to_succeed() -> None:
    failed_query = _query_observation().model_copy(update={"success": False})
    query_gate = assess_query_candidate(compute_query_metrics((failed_query,)))
    assert query_gate.passed is False
    assert {item.name: item.status.value for item in query_gate.checks}[
        "successful_records"
    ] == "FAIL"

    grounding, injection = _grounding_observations()
    failed_injection = injection.model_copy(update={"success": False})
    grounding_metrics, injection_metrics = compute_grounding_metrics((grounding, failed_injection))
    grounding_gate = assess_grounding_candidate(grounding_metrics, injection_metrics)
    assert grounding_gate.passed is False
    assert {item.name: item.status.value for item in grounding_gate.checks}[
        "successful_injection_records"
    ] == "FAIL"


@pytest.mark.unit
def test_observations_require_unique_hashes_and_complete_expected_coverage() -> None:
    observation = _query_observation()
    with pytest.raises(CandidateEvaluationError, match="unique"):
        compute_query_metrics((observation, observation))
    with pytest.raises(CandidateEvaluationError, match="complete expected split"):
        require_complete_record_coverage(
            (observation,),
            expected_record_hashes=frozenset(
                {observation.record_id_hash, hash_identifier("query-2")}
            ),
        )


@pytest.mark.unit
def test_grounding_freeze_requires_all_semantic_and_injection_gates() -> None:
    grounding, injection = compute_grounding_metrics(_grounding_observations())
    gate = assess_grounding_candidate(grounding, injection)
    assert gate.passed is True
    assert all(item.actual in {0.0, 1.0} for item in gate.checks)
    bad = grounding.model_copy(update={"required_fact_coverage": 0.99})
    assert assess_grounding_candidate(bad, injection).passed is False


@pytest.mark.unit
def test_candidate_scoped_freeze_and_one_shot_test_authorization() -> None:
    profile = CandidateEvaluationProfile.create(
        candidate=_candidate(),
        task=CandidateTask.POLICY_QUERY_BUILDER_V1,
        prompt=POLICY_QUERY_BUILDER_PROMPT_V1_1,
        dataset_digest=DIGEST,
        retrieval_corpus_digest=DIGEST,
    )
    metrics = compute_query_metrics((_query_observation(),))
    gate = assess_query_candidate(metrics)
    frozen = freeze_evaluation_profile(
        profile=profile,
        dev_result=metrics,
        gate=gate,
        frozen_at=datetime(2026, 8, 31, tzinfo=UTC),
    )
    validate_frozen_evaluation_evidence(
        frozen=frozen,
        dev_result=metrics,
        gate=gate,
    )
    authorize_sealed_test(
        current_profile=profile,
        frozen=frozen,
        allow_sealed_test=True,
        test_result_exists=False,
    )
    with pytest.raises(CandidateEvaluationError, match="already exists"):
        authorize_sealed_test(
            current_profile=profile,
            frozen=frozen,
            allow_sealed_test=True,
            test_result_exists=True,
        )


@pytest.mark.unit
def test_frozen_profile_recomputes_embedded_and_referenced_digests() -> None:
    profile = CandidateEvaluationProfile.create(
        candidate=_candidate(),
        task=CandidateTask.POLICY_QUERY_BUILDER_V1,
        prompt=POLICY_QUERY_BUILDER_PROMPT_V1_1,
        dataset_digest=DIGEST,
        retrieval_corpus_digest=DIGEST,
    )
    metrics = compute_query_metrics((_query_observation(),))
    gate = assess_query_candidate(metrics)
    frozen = freeze_evaluation_profile(
        profile=profile,
        dev_result=metrics,
        gate=gate,
        frozen_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    tampered_profile = frozen.model_dump(mode="json")
    tampered_profile["profile_digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValidationError, match="embedded profile"):
        type(frozen).model_validate(tampered_profile)

    tampered_metrics = metrics.model_copy(update={"latency_p95_ms": 999.0})
    assert canonical_digest(tampered_metrics) != frozen.dev_result_digest
    with pytest.raises(CandidateEvaluationError, match="Dev result digest"):
        validate_frozen_evaluation_evidence(
            frozen=frozen,
            dev_result=tampered_metrics,
            gate=gate,
        )

    tampered_check = gate.checks[0].model_copy(update={"actual": 0.5})
    tampered_gate = gate.model_copy(update={"checks": (tampered_check, *gate.checks[1:])})
    digest_rewritten_frozen = frozen.model_copy(
        update={"gate_result_digest": canonical_digest(tampered_gate)}
    )
    with pytest.raises(CandidateEvaluationError, match="recomputed Dev metrics"):
        validate_frozen_evaluation_evidence(
            frozen=digest_rewritten_frozen,
            dev_result=metrics,
            gate=tampered_gate,
        )


@pytest.mark.unit
def test_candidate_cli_rejects_legacy_self_asserted_scores(tmp_path: Path) -> None:
    observations = tmp_path / "legacy.jsonl"
    fake = _query_observation().model_copy(
        update={
            "relevant_clause_ids_hashes": (DIGEST,),
            "hit_clause_ids_hashes": (DIGEST,),
        }
    )
    observations.write_text(
        fake.model_dump_json() + "\n" + fake.model_dump_json() + "\n",
        encoding="utf-8",
    )
    candidate = _candidate()
    with pytest.raises(CandidateEvaluationError, match="self-asserted observations are ineligible"):
        candidate_task_evaluator._load_observations(  # pyright: ignore[reportPrivateUsage]
            observations,
            "query-builder",
            EvaluationSplit.DEV,
            candidate=candidate,
            profile=_query_profile(candidate),
        )


@pytest.mark.unit
def test_failure_taxonomy_counts_only_stable_codes() -> None:
    failed = tuple(
        candidate_task_evaluator.ExtractionRawObservation(
            record_id_hash=hash_identifier(f"failure-{index}"),
            split=EvaluationSplit.DEV,
            status="FAILED",
            request_digest=DIGEST,
            result_digest=DIGEST,
            latency_ms=10,
            error_code=code,
        )
        for index, code in enumerate(
            (
                "LLM_STRUCTURED_MISSING_FIELD",
                "LLM_STRUCTURED_ENUM_INVALID",
                "LLM_STRUCTURED_MISSING_FIELD",
            )
        )
    )

    counts = candidate_task_evaluator._failure_code_counts(  # pyright: ignore[reportPrivateUsage]
        failed
    )

    assert [(item.code, item.count) for item in counts] == [
        ("LLM_STRUCTURED_ENUM_INVALID", 1),
        ("LLM_STRUCTURED_MISSING_FIELD", 2),
    ]
    rendered = json.dumps([item.model_dump(mode="json") for item in counts])
    assert "customer_message" not in rendered
    assert "record_id_hash" not in rendered


@pytest.mark.unit
def test_same_retrieval_hash_for_all_gold_records_cannot_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_clause = "POLICY-BRD-001:2.0.0:C1"
    second_clause = "POLICY-BRD-001:2.0.0:C2"
    records = (_query_gold("query-1", first_clause), _query_gold("query-2", second_clause))
    dataset = tmp_path / "gold.jsonl"
    dataset.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(candidate_task_evaluator, "QUERY_DATASET", dataset)
    registry = candidate_task_evaluator._load_clause_registry()  # pyright: ignore[reportPrivateUsage]
    first_row_digest = registry[hash_identifier(first_clause)][1]
    candidate = _candidate()
    profile = _query_profile(candidate)
    raw = tuple(
        _raw_query_observation(
            candidate=candidate,
            profile=profile,
            record=record,
            hit_clause_id=first_clause,
            hit_row_digest=first_row_digest,
        )
        for record in records
    )
    observations = tmp_path / "observations.jsonl"
    _write_observation_set(
        observations,
        candidate=candidate,
        profile=profile,
        observations=raw,
    )

    derived, evidence = candidate_task_evaluator._load_observations(  # pyright: ignore[reportPrivateUsage]
        observations,
        "query-builder",
        EvaluationSplit.DEV,
        candidate=candidate,
        profile=profile,
    )
    metrics = compute_query_metrics(
        tuple(item for item in derived if isinstance(item, QueryEvaluationObservation))
    )
    assert evidence.record_count == 2
    assert metrics.recall_at_10 == 0.5
    assert assess_query_candidate(metrics).passed is False


@pytest.mark.unit
@pytest.mark.parametrize("tamper", ("nonexistent", "wrong-row-digest"))
def test_raw_retrieval_clause_identity_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    clause_id = "POLICY-BRD-001:2.0.0:C1"
    record = _query_gold("query-1", clause_id)
    dataset = tmp_path / "gold.jsonl"
    dataset.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(candidate_task_evaluator, "QUERY_DATASET", dataset)
    registry = candidate_task_evaluator._load_clause_registry()  # pyright: ignore[reportPrivateUsage]
    row_digest = registry[hash_identifier(clause_id)][1]
    candidate = _candidate()
    profile = _query_profile(candidate)
    raw = _raw_query_observation(
        candidate=candidate,
        profile=profile,
        record=record,
        hit_clause_id="POLICY-NOT-FOUND:9.9.9:C1" if tamper == "nonexistent" else clause_id,
        hit_row_digest=DIGEST if tamper == "wrong-row-digest" else row_digest,
    )
    observations = tmp_path / "observations.jsonl"
    _write_observation_set(
        observations,
        candidate=candidate,
        profile=profile,
        observations=(raw,),
    )

    message = "nonexistent clause hash" if tamper == "nonexistent" else "frozen row"
    with pytest.raises(CandidateEvaluationError, match=message):
        candidate_task_evaluator._load_observations(  # pyright: ignore[reportPrivateUsage]
            observations,
            "query-builder",
            EvaluationSplit.DEV,
            candidate=candidate,
            profile=profile,
        )


@pytest.mark.unit
def test_observation_set_binding_rejects_another_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clause_id = "POLICY-BRD-001:2.0.0:C1"
    record = _query_gold("query-1", clause_id)
    dataset = tmp_path / "gold.jsonl"
    dataset.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(candidate_task_evaluator, "QUERY_DATASET", dataset)
    candidate = _candidate()
    profile = _query_profile(candidate)
    registry = candidate_task_evaluator._load_clause_registry()  # pyright: ignore[reportPrivateUsage]
    raw = _raw_query_observation(
        candidate=candidate,
        profile=profile,
        record=record,
        hit_clause_id=clause_id,
        hit_row_digest=registry[hash_identifier(clause_id)][1],
    )
    observations = (raw,)
    manifest = candidate_task_evaluator.CandidateObservationSetManifest(
        task=CandidateTask.POLICY_QUERY_BUILDER_V1,
        split=EvaluationSplit.DEV,
        candidate_identity_digest=candidate.identity_digest,
        profile_digest=profile.profile_digest,
        runtime_identity_digest="sha256:" + "b" * 64,
        provider_metadata=_provider_metadata(candidate),
        provider_metadata_digest=candidate_task_evaluator._canonical_payload_digest(  # pyright: ignore[reportPrivateUsage]
            _provider_metadata(candidate)
        ),
        record_count=len(observations),
        request_set_digest=candidate_task_evaluator._set_digest(  # pyright: ignore[reportPrivateUsage]
            observations, "request_digest"
        ),
        result_set_digest=candidate_task_evaluator._set_digest(  # pyright: ignore[reportPrivateUsage]
            observations, "result_digest"
        ),
        capture_origin="LIVE_PROVIDER",
    )
    bound = tmp_path / "bound.jsonl"
    bound.write_text(
        manifest.model_dump_json() + "\n" + raw.model_dump_json() + "\n",
        encoding="utf-8",
    )
    with pytest.raises(CandidateEvaluationError, match="runtime identity"):
        candidate_task_evaluator._load_observations(  # pyright: ignore[reportPrivateUsage]
            bound,
            "query-builder",
            EvaluationSplit.DEV,
            candidate=candidate,
            profile=profile,
        )


@pytest.mark.unit
def test_live_capture_writer_is_owner_only_non_overwriting_and_input_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clause_id = "POLICY-BRD-001:2.0.0:C1"
    record = _query_gold("query-secure-write", clause_id)
    dataset = tmp_path / "gold.jsonl"
    dataset.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(candidate_task_evaluator, "QUERY_DATASET", dataset)
    candidate = _candidate()
    profile = _query_profile(candidate)
    registry = candidate_task_evaluator._load_clause_registry()  # pyright: ignore[reportPrivateUsage]
    raw = _raw_query_observation(
        candidate=candidate,
        profile=profile,
        record=record,
        hit_clause_id=clause_id,
        hit_row_digest=registry[hash_identifier(clause_id)][1],
    )
    path = tmp_path / "private" / "capture.jsonl"
    candidate_task_evaluator.write_raw_observation_set(
        path,
        task=CandidateTask.POLICY_QUERY_BUILDER_V1,
        split=EvaluationSplit.DEV,
        candidate=candidate,
        profile=profile,
        provider_metadata=_provider_metadata(candidate),
        observations=(raw,),
    )

    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert str(record["customer_message"]) not in path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        candidate_task_evaluator.write_raw_observation_set(
            path,
            task=CandidateTask.POLICY_QUERY_BUILDER_V1,
            split=EvaluationSplit.DEV,
            candidate=candidate,
            profile=profile,
            provider_metadata=_provider_metadata(candidate),
            observations=(raw,),
        )


@pytest.mark.unit
def test_grounding_scores_citations_from_typed_output_not_claimed_counts() -> None:
    record: dict[str, object] = {
        "record_id": "ground-raw-1",
        "split": "dev",
        "tenant_id": "csight-demo-brand",
        "case_summary": "BREAKAGE 관련 합성 사례",
        "provided_clause_ids": ["POLICY-BRD-001:2.0.0:C1"],
        "required_citation_ids": ["POLICY-BRD-001:2.0.0:C1"],
        "required_facts": ["해당 조항은 검토 조건 또는 증거 요구를 설명함"],
        "unresolved_conditions": ["실제 증거와 사람 검토가 필요함"],
        "forbidden_claims": ["최종 승인되었다"],
    }
    candidate = _candidate()
    explanation = GroundedPolicyExplanation(
        policy_statements=(
            GroundedPolicyStatement(
                statement_id="S1",
                text="해당 조항은 검토 조건 또는 증거 요구를 설명함",
                citation_ids=("CIT-999",),
            ),
        ),
        unresolved_conditions=(
            UnresolvedPolicyCondition(
                condition="실제 증거와 사람 검토가 필요함",
                required_evidence="HUMAN_REVIEW",
            ),
        ),
    )
    output = candidate_task_evaluator.GroundingProviderOutput(
        explanation=explanation,
        metadata=candidate_task_evaluator.PrivacySafeProviderExecutionMetadata(
            provider_name=candidate.provider,
            model_name=candidate.served_model_name,
            model_version=candidate.model_version,
            model_revision=candidate.artifact_revision,
            latency_ms=12,
        ),
    )
    request = candidate_task_evaluator._grounding_input(  # pyright: ignore[reportPrivateUsage]
        record, kind="GROUNDING"
    )
    raw = candidate_task_evaluator.GroundingRawObservation(
        record_id_hash=hash_identifier("ground-raw-1"),
        split=EvaluationSplit.DEV,
        kind="GROUNDING",
        status="SUCCEEDED",
        request_digest=candidate_task_evaluator._provider_request_digest(  # pyright: ignore[reportPrivateUsage]
            task=CandidateTask.GROUNDED_POLICY_EXPLANATION_V1,
            request=request,
            prompt=GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1,
        ),
        result_digest=DIGEST,
        latency_ms=24,
        provider_output=output,
        replay_output=output,
    )
    raw = raw.model_copy(
        update={
            "result_digest": candidate_task_evaluator._grounding_result_digest(  # pyright: ignore[reportPrivateUsage]
                raw
            )
        }
    )
    derived = candidate_task_evaluator._derive_grounding_observation(  # pyright: ignore[reportPrivateUsage]
        raw,
        record=record,
        candidate=candidate,
        clause_registry=candidate_task_evaluator._load_clause_registry(),  # pyright: ignore[reportPrivateUsage]
    )
    assert derived.citation_tp == 0
    assert derived.citation_fn == 1
    assert derived.unknown_citation is True
    injection = _grounding_observations()[1]
    grounding_metrics, injection_metrics = compute_grounding_metrics((derived, injection))
    assert assess_grounding_candidate(grounding_metrics, injection_metrics).passed is False


@pytest.mark.unit
def test_grounding_profile_uses_production_prompt_identity() -> None:
    profile = CandidateEvaluationProfile.create(
        candidate=_candidate(),
        task=CandidateTask.GROUNDED_POLICY_EXPLANATION_V1,
        prompt=GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1,
        dataset_digest=DIGEST,
    )
    assert profile.prompt_version == "1.1.0"
    assert profile.raw_inputs_retained is False
    assert profile.raw_predictions_retained is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "failure",
    (GroundedExplanationInvalidOutputError(), CitationAllowlistViolationError()),
)
def test_grounding_generation_records_expected_output_failure_without_aborting(
    failure: GroundedExplanationInvalidOutputError | CitationAllowlistViolationError,
) -> None:
    candidate = _candidate()

    class FailingGroundingProvider:
        @property
        def provider_metadata(self) -> ProviderMetadata:
            return _provider_metadata(candidate)

        def explain_policy_grounded(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            raise failure

    observations = candidate_task_evaluator.generate_grounding_raw_observations(
        FailingGroundingProvider(),  # type: ignore[arg-type]
        candidate=candidate,
        split=EvaluationSplit.DEV,
    )

    expected_code = str(failure.code)
    assert observations
    assert {item.kind for item in observations} == {"GROUNDING", "INJECTION"}
    assert all(item.status == "FAILED" for item in observations)
    assert all(item.error_code == expected_code for item in observations)
    assert all(item.provider_output is None and item.replay_output is None for item in observations)
    assert all(item.raw_customer_data_retained is False for item in observations)


@pytest.mark.unit
def test_query_generation_records_expected_invalid_output_without_aborting() -> None:
    candidate = _candidate()

    class FailingQueryProvider:
        @property
        def provider_metadata(self) -> ProviderMetadata:
            return _provider_metadata(candidate)

        def build_policy_queries(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            raise PolicyQueryBuilderInvalidOutputError()

    def retrieval_must_not_run(*args: object) -> Never:
        raise AssertionError(args)

    observations = candidate_task_evaluator.generate_query_raw_observations(
        FailingQueryProvider(),  # type: ignore[arg-type]
        candidate=candidate,
        profile=_query_profile(candidate),
        split=EvaluationSplit.DEV,
        retrieval_executor=retrieval_must_not_run,
    )

    assert observations
    assert all(item.status == "FAILED" for item in observations)
    assert all(item.error_code == "POLICY_QUERY_BUILDER_INVALID_OUTPUT" for item in observations)
    assert all(item.provider_output is None and not item.retrieval_results for item in observations)
    assert all(item.raw_customer_data_retained is False for item in observations)


def _passing_extraction_metrics() -> ExtractionEvaluationMetrics:
    return ExtractionEvaluationMetrics(
        split=EvaluationSplit.DEV,
        record_count=1,
        success_count=1,
        json_schema_valid_rate=1.0,
        pydantic_validation_rate=1.0,
        exact_quote_rate=1.0,
        issue_type_f1=1.0,
        requested_action_set_f1=1.0,
        requested_action_exact_accuracy=1.0,
        system_missing_exact_accuracy=1.0,
        action_consistency_accuracy=1.0,
        text_ambiguity_set_f1=1.0,
        forbidden_field_rate=0.0,
        prompt_injection_violation_rate=0.0,
        reasoning_leakage_rate=0.0,
        latency_p50_ms=1_000,
        latency_p95_ms=1_000,
        output_tokens_per_second=30.0,
    )


def _three_task_result(
    candidate: EvaluationCandidate,
    *,
    extraction: ExtractionEvaluationMetrics | None = None,
) -> ThreeTaskDevResult:
    grounding, injection = compute_grounding_metrics(_grounding_observations())
    return ThreeTaskDevResult(
        candidate=candidate,
        extraction=extraction or _passing_extraction_metrics(),
        query=compute_query_metrics((_query_observation(),)),
        grounding=grounding,
        injection=injection,
    )


@pytest.mark.unit
def test_extraction_scores_are_derived_from_frozen_gold_not_claimed_counts() -> None:
    record: dict[str, object] = {
        "record_id": "extract-raw-1",
        "split": "dev",
        "customer_message": "용기가 깨져 교환해주세요.",
        "case_context": {
            "available_image_count": 0,
            "declared_requested_action": "UNSPECIFIED",
            "order_ref": None,
            "product_ref": None,
        },
        "categories": ["standard"],
        "expected": {
            "action_consistency": "ONLY_EXTRACTED",
            "issue_types": ["BREAKAGE"],
            "requested_actions": ["EXCHANGE"],
            "system_missing_information": [
                "ORDER_REFERENCE",
                "PRODUCT_REFERENCE",
                "IMAGE_EVIDENCE",
            ],
            "text_ambiguities": [],
        },
        "forbidden_outputs": ["FINAL_DECISION"],
    }
    candidate = _candidate()
    result = LLMTextExtractionResultV2(
        issue_types=(ExtractionIssueType.BREAKAGE,),
        claims=(
            LLMTextClaimV2(
                type=ExtractionIssueType.BREAKAGE,
                description="용기가 깨졌다고 보고함",
                source_quote="깨져",
            ),
        ),
        requested_actions=(
            RequestedActionItemV2(
                action=ExtractedActionV2.EXCHANGE,
                source_quote="교환",
            ),
        ),
        summary="파손 신고와 교환 요청",
    )
    output = candidate_task_evaluator.ExtractionProviderOutput(
        result=result,
        metadata=candidate_task_evaluator.PrivacySafeProviderExecutionMetadata(
            provider_name=candidate.provider,
            model_name=candidate.served_model_name,
            model_version=candidate.model_version,
            model_revision=candidate.artifact_revision,
            input_token_count=20,
            output_token_count=30,
            latency_ms=1_000,
        ),
    )
    raw = candidate_task_evaluator.ExtractionRawObservation(
        record_id_hash=hash_identifier("extract-raw-1"),
        split=EvaluationSplit.DEV,
        status="SUCCEEDED",
        request_digest=candidate_task_evaluator._provider_request_digest(  # pyright: ignore[reportPrivateUsage]
            task=CandidateTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
            request=candidate_task_evaluator._extraction_input(record),  # pyright: ignore[reportPrivateUsage]
            prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
        ),
        result_digest=DIGEST,
        latency_ms=1_000,
        provider_output=output,
    )
    raw = raw.model_copy(
        update={
            "result_digest": candidate_task_evaluator._extraction_result_digest(  # pyright: ignore[reportPrivateUsage]
                raw
            )
        }
    )

    derived = candidate_task_evaluator._derive_extraction_observation(  # pyright: ignore[reportPrivateUsage]
        raw,
        record=record,
        candidate=candidate,
    )
    assert derived.issue_type_tp == 1
    assert derived.requested_action_tp == 1

    altered = json.loads(json.dumps(record))
    altered["expected"]["issue_types"] = ["LEAKAGE"]
    rescored = candidate_task_evaluator._derive_extraction_observation(  # pyright: ignore[reportPrivateUsage]
        raw,
        record=altered,
        candidate=candidate,
    )
    assert rescored.issue_type_tp == 0
    assert rescored.issue_type_fp == 1
    assert rescored.issue_type_fn == 1

    with pytest.raises(CandidateEvaluationError, match="request digest"):
        candidate_task_evaluator._derive_extraction_observation(  # pyright: ignore[reportPrivateUsage]
            raw.model_copy(update={"request_digest": "sha256:" + "b" * 64}),
            record=record,
            candidate=candidate,
        )
    with pytest.raises(CandidateEvaluationError, match="result digest"):
        candidate_task_evaluator._derive_extraction_observation(  # pyright: ignore[reportPrivateUsage]
            raw.model_copy(update={"result_digest": "sha256:" + "b" * 64}),
            record=record,
            candidate=candidate,
        )


@pytest.mark.unit
def test_current_unpublished_matrix_identity_can_run_dev_but_cannot_freeze() -> None:
    matrix = candidate_task_evaluator.DEFAULT_MATRIX
    candidate = candidate_task_evaluator.load_evaluation_candidate(
        matrix,
        "qwen38-27b-csight-q4-k-m-llama-cpp",
    )
    assert candidate.publication_state is CandidatePublicationState.LOCAL_UNPUBLISHED
    assert candidate.artifact_revision is None
    assert candidate.quantization_variant is CandidateQuantizationVariant.MIXED_Q4_Q6

    profile = CandidateEvaluationProfile.create(
        candidate=candidate,
        task=CandidateTask.POLICY_QUERY_BUILDER_V1,
        prompt=POLICY_QUERY_BUILDER_PROMPT_V1_1,
        dataset_digest=DIGEST,
        retrieval_corpus_digest=DIGEST,
    )
    metrics = compute_query_metrics((_query_observation(),))
    with pytest.raises(CandidateEvaluationError, match="local unpublished"):
        freeze_evaluation_profile(
            profile=profile,
            dev_result=metrics,
            gate=assess_query_candidate(metrics),
            frozen_at=datetime(2026, 9, 1, tzinfo=UTC),
        )

    spoofed_state = candidate.model_copy(
        update={"publication_state": CandidatePublicationState.PUBLISHED}
    )
    spoofed_profile = profile.model_copy(update={"candidate": spoofed_state})
    with pytest.raises(CandidateEvaluationError, match="local unpublished"):
        freeze_evaluation_profile(
            profile=spoofed_profile,
            dev_result=metrics,
            gate=assess_query_candidate(metrics),
            frozen_at=datetime(2026, 9, 1, tzinfo=UTC),
        )


@pytest.mark.unit
def test_three_task_selection_names_mixed_variant_and_can_return_no_winner() -> None:
    mixed = _candidate()
    q5 = mixed.model_copy(
        update={
            "candidate_id": "qwen38-csight-q5ks",
            "quantization_variant": CandidateQuantizationVariant.IMATRIX_Q5_K_S,
            "artifact_weight_bytes": 900_000,
            "served_model_name": "csight-qwen38-q5ks",
            "model_version": "Qwen3.8-27B-CSight-Q5KS",
        }
    )
    q5_metrics = _passing_extraction_metrics().model_copy(update={"issue_type_f1": 0.91})
    selected = select_three_task_dev_winner(
        (_three_task_result(mixed), _three_task_result(q5, extraction=q5_metrics))
    )
    assert selected.status is CandidateSelectionStatus.WINNER_SELECTED
    assert selected.winner_candidate_id == mixed.candidate_id
    assert selected.winner_quantization_variant is CandidateQuantizationVariant.MIXED_Q4_Q6

    failed_performance = _passing_extraction_metrics().model_copy(
        update={"output_tokens_per_second": 24.9}
    )
    no_winner = select_three_task_dev_winner(
        (
            _three_task_result(mixed, extraction=failed_performance),
            _three_task_result(q5, extraction=failed_performance),
        )
    )
    assert no_winner.status is CandidateSelectionStatus.NO_WINNER
    assert no_winner.winner_candidate_id is None
    assert no_winner.reason_codes == ("NO_CANDIDATE_PASSED_ALL_THREE_DEV_GATES",)


@pytest.mark.unit
def test_query_ranking_diagnostics_separate_legacy_hit_rate_from_true_recall() -> None:
    observation = _query_observation()
    observation = observation.model_copy(
        update={
            "relevant_clause_ids_hashes": (
                observation.relevant_clause_ids_hashes[0],
                hash_identifier("POLICY:1:EXCEPTION"),
            )
        }
    )
    legacy_before = compute_query_metrics((observation,)).model_dump_json()
    diagnostic = compute_query_retrieval_diagnostics((observation,))
    top_ten = next(item for item in diagnostic.ranking.cutoffs if item.cutoff == 10)
    assert diagnostic.schema_version == "query_retrieval_diagnostics/1.0.0"
    assert diagnostic.legacy_metric_schema == "query_candidate_metrics/1.0.0"
    assert diagnostic.legacy_recall_at_10_semantics == "CASE_HIT_RATE"
    assert top_ten.hit_rate == compute_query_metrics((observation,)).recall_at_10 == 1.0
    assert top_ten.clause_recall == 0.5
    assert top_ten.exact_gold_coverage == 0.0
    assert compute_query_metrics((observation,)).model_dump_json() == legacy_before
    assert diagnostic.release_eligible is False
    with pytest.raises(ValidationError):
        QueryEvaluationMetrics.model_validate(diagnostic.model_dump())
    with pytest.raises(ValidationError):
        QueryRetrievalDiagnostics.model_validate(
            diagnostic.model_dump() | {"release_eligible": True}
        )


@pytest.mark.unit
def test_query_diagnostics_keep_failed_cases_in_denominator() -> None:
    first = _query_observation()
    failed = first.model_copy(
        update={
            "record_id_hash": hash_identifier("failed-query"),
            "success": False,
            "hit_clause_ids_hashes": (),
        }
    )
    diagnostic = compute_query_retrieval_diagnostics((first, failed))
    assert diagnostic.ranking.record_count == 2
    assert diagnostic.ranking.success_count == diagnostic.ranking.failed_count == 1
    assert all(
        item.hit_rate == item.clause_recall == item.exact_gold_coverage == 0.5
        for item in diagnostic.ranking.cutoffs
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "tamper",
    (
        "empty-gold",
        "duplicate-gold",
        "duplicate-hit",
        "empty-hit",
        "failed-hit",
        "empty-hard-negative",
    ),
)
def test_query_observation_rejects_malformed_ranking_evidence(tamper: str) -> None:
    payload = _query_observation().model_dump()
    if tamper == "empty-gold":
        payload["relevant_clause_ids_hashes"] = ()
    elif tamper == "duplicate-gold":
        payload["relevant_clause_ids_hashes"] *= 2
    elif tamper == "duplicate-hit":
        payload["hit_clause_ids_hashes"] *= 2
    elif tamper == "empty-hit":
        payload["hit_clause_ids_hashes"] = ("",)
    elif tamper == "failed-hit":
        payload["success"] = False
    else:
        payload["hard_negative_clause_ids_hashes"] = ("",)
    with pytest.raises(ValidationError):
        QueryEvaluationObservation.model_validate(payload)


@pytest.mark.unit
def test_query_diagnostics_reject_model_copy_bypass_and_split_mixing() -> None:
    observation = _query_observation()
    with pytest.raises(ValidationError):
        compute_query_retrieval_diagnostics(
            (observation.model_copy(update={"relevant_clause_ids_hashes": ()}),)
        )
    with pytest.raises(ValidationError):
        compute_query_retrieval_diagnostics((observation.model_copy(update={"success": False}),))
    with pytest.raises(CandidateEvaluationError):
        compute_query_retrieval_diagnostics(())
    with pytest.raises(CandidateEvaluationError):
        compute_query_retrieval_diagnostics((observation, observation))
    other_split = _query_observation(EvaluationSplit.TEST).model_copy(
        update={"record_id_hash": hash_identifier("test-record")}
    )
    with pytest.raises(CandidateEvaluationError):
        compute_query_retrieval_diagnostics((observation, other_split))
