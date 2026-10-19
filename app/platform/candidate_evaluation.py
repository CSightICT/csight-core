"""Provider-neutral, candidate-aware model evaluation and sealed-Test contracts."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.analysis import ProviderMetadata
from app.platform.analysis.prompts import PromptManifest
from app.platform.retrieval_evaluation import (
    RetrievalEvaluationMetrics,
    RetrievalEvaluationObservation,
    compute_retrieval_metrics,
)

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_REVISION_PATTERN = r"^[0-9a-f]{40}$"


class CandidateEvaluationError(ValueError):
    """Evaluation identity, gate, or sealed-split state is invalid."""


class CandidateTask(StrEnum):
    PRODUCT_DEFECT_TEXT_EXTRACTION_V2 = "PRODUCT_DEFECT_TEXT_EXTRACTION_V2"
    POLICY_QUERY_BUILDER_V1 = "POLICY_QUERY_BUILDER_V1"
    GROUNDED_POLICY_EXPLANATION_V1 = "GROUNDED_POLICY_EXPLANATION_V1"


class EvaluationSplit(StrEnum):
    DEV = "dev"
    TEST = "test"


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class CandidateQuantizationVariant(StrEnum):
    """Human-readable recipe identity; never infer mixed tensors from a Q4 label."""

    MIXED_Q4_Q6 = "MIXED_Q4_Q6"
    IMATRIX_Q5_K_S = "IMATRIX_Q5_K_S"


class CandidatePublicationState(StrEnum):
    LOCAL_UNPUBLISHED = "LOCAL_UNPUBLISHED"
    PUBLISHED = "PUBLISHED"


class CandidateSelectionStatus(StrEnum):
    WINNER_SELECTED = "WINNER_SELECTED"
    NO_WINNER = "NO_WINNER"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EvaluationCandidate(_Contract):
    schema_version: Literal["evaluation_candidate/1.0.0"] = "evaluation_candidate/1.0.0"
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    provider: str = Field(min_length=2, max_length=64)
    artifact: str = Field(min_length=3, max_length=512)
    publication_state: CandidatePublicationState
    artifact_revision: str | None = Field(default=None, pattern=_REVISION_PATTERN)
    artifact_content_digest: str = Field(pattern=_DIGEST_PATTERN)
    artifact_weight_bytes: int = Field(gt=0)
    quantization_recipe_digest: str = Field(pattern=_DIGEST_PATTERN)
    quantization_variant: CandidateQuantizationVariant
    candidate_matrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    comparison_contract_digest: str = Field(pattern=_DIGEST_PATTERN)
    served_model_name: str = Field(min_length=2, max_length=255)
    model_version: str = Field(min_length=1, max_length=100)
    runtime_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    tokenizer_config_digest: str = Field(pattern=_DIGEST_PATTERN)
    chat_template_digest: str = Field(pattern=_DIGEST_PATTERN)
    max_context_tokens: int = Field(ge=1, le=1_000_000)
    max_output_tokens: int = Field(ge=1, le=16_384)
    temperature: float = Field(default=0.0, ge=0.0, le=0.0)
    concurrency: Literal[1] = 1
    thinking_enabled: Literal[False] = False
    automatic_cross_model_fallback: Literal[False] = False

    @model_validator(mode="after")
    def bind_publication_state_to_revision(self) -> EvaluationCandidate:
        published = self.artifact_revision is not None
        if published != (self.publication_state is CandidatePublicationState.PUBLISHED):
            raise ValueError("candidate publication state must match artifact revision presence")
        return self

    @property
    def identity_digest(self) -> str:
        return canonical_digest(self)


class CandidateEvaluationProfile(_Contract):
    schema_version: Literal["candidate_evaluation_profile/1.0.0"] = (
        "candidate_evaluation_profile/1.0.0"
    )
    candidate: EvaluationCandidate
    task: CandidateTask
    prompt_name: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    prompt_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_schema_version: str = Field(min_length=1, max_length=128)
    output_schema_version: str = Field(min_length=1, max_length=128)
    dataset_digest: str = Field(pattern=_DIGEST_PATTERN)
    retrieval_corpus_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    selection_split: Literal["dev"] = "dev"
    test_reconfiguration_allowed: Literal[False] = False
    raw_inputs_retained: Literal[False] = False
    raw_predictions_retained: Literal[False] = False
    provider_responses_retained: Literal[False] = False
    provider_request_ids_retained: Literal[False] = False

    @property
    def profile_digest(self) -> str:
        return canonical_digest(self)

    @classmethod
    def create(
        cls,
        *,
        candidate: EvaluationCandidate,
        task: CandidateTask,
        prompt: PromptManifest,
        dataset_digest: str,
        retrieval_corpus_digest: str | None = None,
    ) -> CandidateEvaluationProfile:
        return cls(
            candidate=candidate,
            task=task,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_content_hash=prompt.content_hash,
            input_schema_version=prompt.input_schema_version,
            output_schema_version=prompt.output_schema_version,
            dataset_digest=dataset_digest,
            retrieval_corpus_digest=retrieval_corpus_digest,
        )


class GateCheck(_Contract):
    name: str
    status: GateStatus
    actual: float
    limit: str


class EvaluationGateResult(_Contract):
    schema_version: Literal["candidate_evaluation_gate/1.0.0"] = "candidate_evaluation_gate/1.0.0"
    task: CandidateTask
    passed: bool
    checks: tuple[GateCheck, ...]


class QueryEvaluationObservation(_Contract):
    record_id_hash: str = Field(pattern=_DIGEST_PATTERN)
    split: EvaluationSplit
    success: bool
    latency_ms: float = Field(ge=0)
    provider_latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    relevant_clause_ids_hashes: tuple[str, ...]
    hard_negative_clause_ids_hashes: tuple[str, ...]
    hit_clause_ids_hashes: tuple[str, ...]
    schema_valid: bool
    pydantic_valid: bool
    query_purpose_tp: int = Field(ge=0)
    query_purpose_fp: int = Field(ge=0)
    query_purpose_fn: int = Field(ge=0)
    filter_hint_tp: int = Field(ge=0)
    filter_hint_fp: int = Field(ge=0)
    filter_hint_fn: int = Field(ge=0)
    empty_query: bool
    duplicate_query: bool
    forbidden_field: bool
    prompt_injection_violation: bool
    reasoning_leakage: bool
    cross_tenant_retrieval: bool = False
    wrong_version_retrieval: bool = False
    future_policy_retrieval: bool = False
    retired_policy_retrieval: bool = False
    error_code: str | None = Field(default=None, max_length=128)
    raw_text_retained: Literal[False] = False
    prediction_retained: Literal[False] = False

    @model_validator(mode="after")
    def require_valid_ranking_input(self) -> QueryEvaluationObservation:
        RetrievalEvaluationObservation(
            record_id=self.record_id_hash,
            relevant_clause_ids=self.relevant_clause_ids_hashes,
            hit_clause_ids=self.hit_clause_ids_hashes,
            success=self.success,
        )
        if any(not value.strip() for value in self.hard_negative_clause_ids_hashes):
            raise ValueError("hard-negative clause identifiers must be nonempty")
        if len(self.hard_negative_clause_ids_hashes) != len(
            set(self.hard_negative_clause_ids_hashes)
        ):
            raise ValueError("hard-negative clause identifiers must be unique")
        return self


class ExtractionEvaluationObservation(_Contract):
    record_id_hash: str = Field(pattern=_DIGEST_PATTERN)
    split: EvaluationSplit
    success: bool
    latency_ms: float = Field(ge=0)
    provider_latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    schema_valid: bool
    pydantic_valid: bool
    exact_source_quotes: bool
    issue_type_tp: int = Field(ge=0)
    issue_type_fp: int = Field(ge=0)
    issue_type_fn: int = Field(ge=0)
    requested_action_tp: int = Field(ge=0)
    requested_action_fp: int = Field(ge=0)
    requested_action_fn: int = Field(ge=0)
    text_ambiguity_tp: int = Field(ge=0)
    text_ambiguity_fp: int = Field(ge=0)
    text_ambiguity_fn: int = Field(ge=0)
    requested_actions_exact: bool
    system_missing_exact: bool
    action_consistency_exact: bool
    forbidden_field: bool
    prompt_injection_violation: bool
    reasoning_leakage: bool
    error_code: str | None = Field(default=None, max_length=128)
    raw_text_retained: Literal[False] = False
    prediction_retained: Literal[False] = False


class ExtractionEvaluationMetrics(_Contract):
    schema_version: Literal["extraction_candidate_metrics/1.0.0"] = (
        "extraction_candidate_metrics/1.0.0"
    )
    split: EvaluationSplit
    record_count: int = Field(gt=0)
    success_count: int = Field(ge=0)
    json_schema_valid_rate: float = Field(ge=0, le=1)
    pydantic_validation_rate: float = Field(ge=0, le=1)
    exact_quote_rate: float = Field(ge=0, le=1)
    issue_type_f1: float = Field(ge=0, le=1)
    requested_action_set_f1: float = Field(ge=0, le=1)
    requested_action_exact_accuracy: float = Field(ge=0, le=1)
    system_missing_exact_accuracy: float = Field(ge=0, le=1)
    action_consistency_accuracy: float = Field(ge=0, le=1)
    text_ambiguity_set_f1: float = Field(ge=0, le=1)
    forbidden_field_rate: float = Field(ge=0, le=1)
    prompt_injection_violation_rate: float = Field(ge=0, le=1)
    reasoning_leakage_rate: float = Field(ge=0, le=1)
    latency_p50_ms: float = Field(ge=0)
    latency_p95_ms: float = Field(ge=0)
    output_tokens_per_second: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_possible_success_count(self) -> ExtractionEvaluationMetrics:
        if self.success_count > self.record_count:
            raise ValueError("success_count cannot exceed record_count")
        return self


class QueryEvaluationMetrics(_Contract):
    """Historical v1 evidence: ``recall_at_10`` means case HitRate, not clause recall.

    Frozen v1 baselines, serialization and gates retain that historical meaning.
    Use the separately versioned query retrieval diagnostics for true clause recall;
    those diagnostics cannot inherit the frozen v1 release qualification.
    """

    schema_version: Literal["query_candidate_metrics/1.0.0"] = "query_candidate_metrics/1.0.0"
    split: EvaluationSplit
    record_count: int = Field(gt=0)
    success_count: int = Field(ge=0)
    json_schema_valid_rate: float = Field(ge=0, le=1)
    pydantic_validation_rate: float = Field(ge=0, le=1)
    query_purpose_f1: float = Field(ge=0, le=1)
    filter_hint_f1: float = Field(ge=0, le=1)
    empty_query_rate: float = Field(ge=0, le=1)
    duplicate_query_rate: float = Field(ge=0, le=1)
    forbidden_field_rate: float = Field(ge=0, le=1)
    prompt_injection_violation_rate: float = Field(ge=0, le=1)
    reasoning_leakage_rate: float = Field(ge=0, le=1)
    recall_at_10: float = Field(ge=0, le=1)
    exact_gold_coverage_at_10: float = Field(ge=0, le=1)
    mrr_at_10: float = Field(ge=0, le=1)
    ndcg_at_10: float = Field(ge=0, le=1)
    hard_negative_hit_rate_at_5: float = Field(ge=0, le=1)
    zero_result_rate: float = Field(ge=0, le=1)
    cross_tenant_retrieval_rate: float = Field(ge=0, le=1)
    wrong_version_retrieval_rate: float = Field(ge=0, le=1)
    future_policy_retrieval_rate: float = Field(ge=0, le=1)
    retired_policy_retrieval_rate: float = Field(ge=0, le=1)
    latency_p50_ms: float = Field(ge=0)
    latency_p95_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def require_possible_success_count(self) -> QueryEvaluationMetrics:
        if self.success_count > self.record_count:
            raise ValueError("success_count cannot exceed record_count")
        return self


class QueryRetrievalDiagnostics(_Contract):
    schema_version: Literal["query_retrieval_diagnostics/1.0.0"] = (
        "query_retrieval_diagnostics/1.0.0"
    )
    split: EvaluationSplit
    legacy_metric_schema: Literal["query_candidate_metrics/1.0.0"] = "query_candidate_metrics/1.0.0"
    legacy_recall_at_10_semantics: Literal["CASE_HIT_RATE"] = "CASE_HIT_RATE"
    ranking: RetrievalEvaluationMetrics
    release_eligible: Literal[False] = False


class GroundingEvaluationObservation(_Contract):
    record_id_hash: str = Field(pattern=_DIGEST_PATTERN)
    split: EvaluationSplit
    kind: Literal["GROUNDING", "INJECTION"]
    success: bool
    latency_ms: float = Field(ge=0)
    provider_latency_ms: int | None = Field(default=None, ge=0)
    schema_valid: bool
    pydantic_valid: bool
    citation_tp: int = Field(default=0, ge=0)
    citation_fp: int = Field(default=0, ge=0)
    citation_fn: int = Field(default=0, ge=0)
    statement_count: int = Field(default=0, ge=0)
    cited_statement_count: int = Field(default=0, ge=0)
    required_fact_coverage: float = Field(default=0, ge=0, le=1)
    unresolved_condition_recall: float = Field(default=0, ge=0, le=1)
    citation_allowlist_violation: bool = False
    unknown_citation: bool = False
    cross_tenant_citation: bool = False
    wrong_version_citation: bool = False
    duplicate_citation: bool = False
    forbidden_claim: bool = False
    policy_overstatement: bool = False
    forbidden_field: bool = False
    prompt_injection_violation: bool = False
    reasoning_leakage: bool = False
    deterministic_replay: bool = False
    error_code: str | None = Field(default=None, max_length=128)
    raw_text_retained: Literal[False] = False
    prediction_retained: Literal[False] = False


class GroundingEvaluationMetrics(_Contract):
    schema_version: Literal["grounding_candidate_metrics/1.0.0"] = (
        "grounding_candidate_metrics/1.0.0"
    )
    split: EvaluationSplit
    record_count: int = Field(gt=0)
    success_count: int = Field(ge=0)
    json_schema_valid_rate: float = Field(ge=0, le=1)
    pydantic_validation_rate: float = Field(ge=0, le=1)
    citation_id_valid_rate: float = Field(ge=0, le=1)
    citation_id_precision: float = Field(ge=0, le=1)
    citation_id_recall: float = Field(ge=0, le=1)
    citation_completeness: float = Field(ge=0, le=1)
    required_fact_coverage: float = Field(ge=0, le=1)
    unresolved_condition_recall: float = Field(ge=0, le=1)
    deterministic_replay_rate: float = Field(ge=0, le=1)
    citation_allowlist_violation_rate: float = Field(ge=0, le=1)
    unknown_citation_rate: float = Field(ge=0, le=1)
    cross_tenant_citation_rate: float = Field(ge=0, le=1)
    wrong_version_citation_rate: float = Field(ge=0, le=1)
    duplicate_citation_rate: float = Field(ge=0, le=1)
    forbidden_claim_rate: float = Field(ge=0, le=1)
    policy_overstatement_rate: float = Field(ge=0, le=1)
    forbidden_field_rate: float = Field(ge=0, le=1)
    reasoning_leakage_rate: float = Field(ge=0, le=1)
    latency_p50_ms: float = Field(ge=0)
    latency_p95_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def require_possible_success_count(self) -> GroundingEvaluationMetrics:
        if self.success_count > self.record_count:
            raise ValueError("success_count cannot exceed record_count")
        return self


class InjectionEvaluationMetrics(_Contract):
    schema_version: Literal["grounding_injection_candidate_metrics/1.0.0"] = (
        "grounding_injection_candidate_metrics/1.0.0"
    )
    split: EvaluationSplit
    record_count: int = Field(gt=0)
    success_count: int = Field(ge=0)
    json_schema_valid_rate: float = Field(ge=0, le=1)
    pydantic_validation_rate: float = Field(ge=0, le=1)
    prompt_injection_violation_rate: float = Field(ge=0, le=1)
    forbidden_field_rate: float = Field(ge=0, le=1)
    reasoning_leakage_rate: float = Field(ge=0, le=1)
    latency_p50_ms: float = Field(ge=0)
    latency_p95_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def require_possible_success_count(self) -> InjectionEvaluationMetrics:
        if self.success_count > self.record_count:
            raise ValueError("success_count cannot exceed record_count")
        return self


class ThreeTaskDevResult(_Contract):
    """Complete Dev-only evidence used to choose one quantized candidate."""

    schema_version: Literal["three_task_candidate_dev_result/1.0.0"] = (
        "three_task_candidate_dev_result/1.0.0"
    )
    candidate: EvaluationCandidate
    extraction: ExtractionEvaluationMetrics
    query: QueryEvaluationMetrics
    grounding: GroundingEvaluationMetrics
    injection: InjectionEvaluationMetrics

    @model_validator(mode="after")
    def require_dev_only(self) -> ThreeTaskDevResult:
        if {
            self.extraction.split,
            self.query.split,
            self.grounding.split,
            self.injection.split,
        } != {EvaluationSplit.DEV}:
            raise ValueError("candidate selection accepts Dev evidence only")
        return self


class CandidateSelectionEntry(_Contract):
    candidate_id: str
    quantization_variant: CandidateQuantizationVariant
    all_task_gates_passed: bool
    minimum_normalized_quality_margin: float | None = None
    maximum_task_p95_ms: float
    artifact_weight_bytes: int


class ThreeTaskWinnerDecision(_Contract):
    schema_version: Literal["three_task_candidate_winner/1.0.0"] = (
        "three_task_candidate_winner/1.0.0"
    )
    selection_rule_version: Literal["absolute-gates-then-maximin/1.0.0"] = (
        "absolute-gates-then-maximin/1.0.0"
    )
    status: CandidateSelectionStatus
    winner_candidate_id: str | None = None
    winner_quantization_variant: CandidateQuantizationVariant | None = None
    reason_codes: tuple[str, ...]
    candidates: tuple[CandidateSelectionEntry, ...]
    test_evidence_used: Literal[False] = False

    @model_validator(mode="after")
    def require_status_payload(self) -> ThreeTaskWinnerDecision:
        winner_present = self.winner_candidate_id is not None
        if winner_present != (self.status is CandidateSelectionStatus.WINNER_SELECTED):
            raise ValueError("winner identity must match selection status")
        if winner_present != (self.winner_quantization_variant is not None):
            raise ValueError("winner variant must accompany winner identity")
        return self


class FrozenEvaluationProfile(_Contract):
    schema_version: Literal["frozen_candidate_evaluation/1.0.0"] = (
        "frozen_candidate_evaluation/1.0.0"
    )
    profile: CandidateEvaluationProfile
    profile_digest: str = Field(pattern=_DIGEST_PATTERN)
    dev_result_digest: str = Field(pattern=_DIGEST_PATTERN)
    gate_result_digest: str = Field(pattern=_DIGEST_PATTERN)
    frozen_at: datetime

    @field_validator("frozen_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("frozen_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_embedded_profile_digest(self) -> FrozenEvaluationProfile:
        if self.profile_digest != self.profile.profile_digest:
            raise ValueError("frozen profile digest does not match its embedded profile")
        return self


def canonical_digest(value: BaseModel | dict[str, object]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def hash_identifier(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def validate_provider_identity(
    candidate: EvaluationCandidate,
    metadata: ProviderMetadata,
) -> None:
    """Bind evaluation to identity, never to one provider implementation."""

    if (
        metadata.provider != candidate.provider
        or metadata.name != candidate.served_model_name
        or metadata.version != candidate.model_version
        or metadata.revision != candidate.artifact_revision
    ):
        raise CandidateEvaluationError("provider runtime identity does not match the candidate")


def compute_extraction_metrics(
    observations: tuple[ExtractionEvaluationObservation, ...],
) -> ExtractionEvaluationMetrics:
    if not observations:
        raise CandidateEvaluationError("extraction evaluation requires observations")
    _require_unique_record_hashes(observations)
    split = _one_split(tuple(item.split for item in observations))
    count = len(observations)
    successful = tuple(item for item in observations if item.success)
    issue = Counter(tp=0, fp=0, fn=0)
    action = Counter(tp=0, fp=0, fn=0)
    ambiguity = Counter(tp=0, fp=0, fn=0)
    for item in observations:
        issue.update(tp=item.issue_type_tp, fp=item.issue_type_fp, fn=item.issue_type_fn)
        action.update(
            tp=item.requested_action_tp,
            fp=item.requested_action_fp,
            fn=item.requested_action_fn,
        )
        ambiguity.update(
            tp=item.text_ambiguity_tp,
            fp=item.text_ambiguity_fp,
            fn=item.text_ambiguity_fn,
        )
    provider_seconds = (
        sum(
            (item.provider_latency_ms or 0) for item in successful if item.output_tokens is not None
        )
        / 1000
    )
    output_tokens = sum(item.output_tokens or 0 for item in successful)
    latencies = [item.latency_ms for item in observations]
    return ExtractionEvaluationMetrics(
        split=split,
        record_count=count,
        success_count=len(successful),
        json_schema_valid_rate=_rate(item.schema_valid for item in observations),
        pydantic_validation_rate=_rate(item.pydantic_valid for item in observations),
        exact_quote_rate=_rate(item.exact_source_quotes for item in observations),
        issue_type_f1=_f1(issue),
        requested_action_set_f1=_f1(action),
        requested_action_exact_accuracy=_rate(
            item.requested_actions_exact for item in observations
        ),
        system_missing_exact_accuracy=_rate(item.system_missing_exact for item in observations),
        action_consistency_accuracy=_rate(item.action_consistency_exact for item in observations),
        text_ambiguity_set_f1=_f1(ambiguity),
        forbidden_field_rate=_rate(item.forbidden_field for item in observations),
        prompt_injection_violation_rate=_rate(
            item.prompt_injection_violation for item in observations
        ),
        reasoning_leakage_rate=_rate(item.reasoning_leakage for item in observations),
        latency_p50_ms=round(statistics.median(latencies), 3),
        latency_p95_ms=round(_percentile(latencies, 0.95), 3),
        output_tokens_per_second=(
            round(output_tokens / provider_seconds, 6)
            if provider_seconds > 0 and all(item.output_tokens is not None for item in successful)
            else None
        ),
    )


def compute_query_metrics(
    observations: tuple[QueryEvaluationObservation, ...],
) -> QueryEvaluationMetrics:
    """Reproduce v1 frozen metrics; its recall field is the historical HitRate.

    Never reinterpret the frozen 0.975 RAW threshold as true clause recall.
    New ranking diagnostics and a fresh versioned comparison are separate evidence.
    """
    if not observations:
        raise CandidateEvaluationError("query evaluation requires observations")
    _require_unique_record_hashes(observations)
    split = _one_split(tuple(item.split for item in observations))
    count = len(observations)
    successful = tuple(item for item in observations if item.success)
    purpose = Counter(tp=0, fp=0, fn=0)
    hints = Counter(tp=0, fp=0, fn=0)
    reciprocal: list[float] = []
    ndcg_values: list[float] = []
    exact: list[bool] = []
    recalls: list[bool] = []
    for item in observations:
        purpose.update(tp=item.query_purpose_tp, fp=item.query_purpose_fp, fn=item.query_purpose_fn)
        hints.update(tp=item.filter_hint_tp, fp=item.filter_hint_fp, fn=item.filter_hint_fn)
        relevant = set(item.relevant_clause_ids_hashes)
        hits = item.hit_clause_ids_hashes
        ranks = [index for index, hit in enumerate(hits[:10], start=1) if hit in relevant]
        reciprocal.append(1 / min(ranks) if ranks else 0.0)
        dcg = sum(1 / math.log2(rank + 1) for rank in ranks)
        ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(10, len(relevant)) + 1))
        ndcg_values.append(dcg / ideal if ideal else 0.0)
        exact.append(relevant <= set(hits[:10]))
        recalls.append(bool(relevant & set(hits[:10])))
    latencies = [item.latency_ms for item in observations]
    return QueryEvaluationMetrics(
        split=split,
        record_count=count,
        success_count=len(successful),
        json_schema_valid_rate=_rate(item.schema_valid for item in observations),
        pydantic_validation_rate=_rate(item.pydantic_valid for item in observations),
        query_purpose_f1=_f1(purpose),
        filter_hint_f1=_f1(hints),
        empty_query_rate=_rate(item.empty_query for item in observations),
        duplicate_query_rate=_rate(item.duplicate_query for item in observations),
        forbidden_field_rate=_rate(item.forbidden_field for item in observations),
        prompt_injection_violation_rate=_rate(
            item.prompt_injection_violation for item in observations
        ),
        reasoning_leakage_rate=_rate(item.reasoning_leakage for item in observations),
        recall_at_10=round(sum(recalls) / count, 6),
        exact_gold_coverage_at_10=round(sum(exact) / count, 6),
        mrr_at_10=round(statistics.fmean(reciprocal), 6),
        ndcg_at_10=round(statistics.fmean(ndcg_values), 6),
        hard_negative_hit_rate_at_5=_rate(
            bool(set(item.hard_negative_clause_ids_hashes) & set(item.hit_clause_ids_hashes[:5]))
            for item in observations
        ),
        zero_result_rate=_rate(not item.hit_clause_ids_hashes for item in observations),
        cross_tenant_retrieval_rate=_rate(item.cross_tenant_retrieval for item in observations),
        wrong_version_retrieval_rate=_rate(item.wrong_version_retrieval for item in observations),
        future_policy_retrieval_rate=_rate(item.future_policy_retrieval for item in observations),
        retired_policy_retrieval_rate=_rate(item.retired_policy_retrieval for item in observations),
        latency_p50_ms=round(statistics.median(latencies), 3),
        latency_p95_ms=round(_percentile(latencies, 0.95), 3),
    )


def compute_query_retrieval_diagnostics(
    observations: tuple[QueryEvaluationObservation, ...],
) -> QueryRetrievalDiagnostics:
    """Add corrected ranking meanings without rewriting v1 metrics or release gates."""
    if not observations:
        raise CandidateEvaluationError("query retrieval diagnostics require observations")
    _require_unique_record_hashes(observations)
    split = _one_split(tuple(item.split for item in observations))
    ranking = compute_retrieval_metrics(
        tuple(
            RetrievalEvaluationObservation(
                record_id=item.record_id_hash,
                relevant_clause_ids=item.relevant_clause_ids_hashes,
                hit_clause_ids=item.hit_clause_ids_hashes,
                success=item.success,
            )
            for item in observations
        )
    )
    return QueryRetrievalDiagnostics(split=split, ranking=ranking)


def compute_grounding_metrics(
    observations: tuple[GroundingEvaluationObservation, ...],
) -> tuple[GroundingEvaluationMetrics, InjectionEvaluationMetrics]:
    _require_unique_record_hashes(observations)
    grounding = tuple(item for item in observations if item.kind == "GROUNDING")
    injection = tuple(item for item in observations if item.kind == "INJECTION")
    if not grounding or not injection:
        raise CandidateEvaluationError("grounding and injection observations are both required")
    split = _one_split(tuple(item.split for item in observations))
    citations = Counter(tp=0, fp=0, fn=0)
    for item in grounding:
        citations.update(tp=item.citation_tp, fp=item.citation_fp, fn=item.citation_fn)
    citation_prf = _prf(citations)
    grounding_latencies = [item.latency_ms for item in grounding]
    injection_latencies = [item.latency_ms for item in injection]
    grounding_metrics = GroundingEvaluationMetrics(
        split=split,
        record_count=len(grounding),
        success_count=sum(item.success for item in grounding),
        json_schema_valid_rate=_rate(item.schema_valid for item in grounding),
        pydantic_validation_rate=_rate(item.pydantic_valid for item in grounding),
        citation_id_valid_rate=_rate(
            item.success and not item.unknown_citation for item in grounding
        ),
        citation_id_precision=citation_prf["precision"],
        citation_id_recall=citation_prf["recall"],
        citation_completeness=citation_prf["recall"],
        required_fact_coverage=round(
            statistics.fmean(item.required_fact_coverage for item in grounding), 6
        ),
        unresolved_condition_recall=round(
            statistics.fmean(item.unresolved_condition_recall for item in grounding), 6
        ),
        deterministic_replay_rate=_rate(item.deterministic_replay for item in grounding),
        citation_allowlist_violation_rate=_rate(
            item.citation_allowlist_violation for item in grounding
        ),
        unknown_citation_rate=_rate(item.unknown_citation for item in grounding),
        cross_tenant_citation_rate=_rate(item.cross_tenant_citation for item in grounding),
        wrong_version_citation_rate=_rate(item.wrong_version_citation for item in grounding),
        duplicate_citation_rate=_rate(item.duplicate_citation for item in grounding),
        forbidden_claim_rate=_rate(item.forbidden_claim for item in grounding),
        policy_overstatement_rate=_rate(item.policy_overstatement for item in grounding),
        forbidden_field_rate=_rate(item.forbidden_field for item in grounding),
        reasoning_leakage_rate=_rate(item.reasoning_leakage for item in grounding),
        latency_p50_ms=round(statistics.median(grounding_latencies), 3),
        latency_p95_ms=round(_percentile(grounding_latencies, 0.95), 3),
    )
    injection_metrics = InjectionEvaluationMetrics(
        split=split,
        record_count=len(injection),
        success_count=sum(item.success for item in injection),
        json_schema_valid_rate=_rate(item.schema_valid for item in injection),
        pydantic_validation_rate=_rate(item.pydantic_valid for item in injection),
        prompt_injection_violation_rate=_rate(
            item.prompt_injection_violation for item in injection
        ),
        forbidden_field_rate=_rate(item.forbidden_field for item in injection),
        reasoning_leakage_rate=_rate(item.reasoning_leakage for item in injection),
        latency_p50_ms=round(statistics.median(injection_latencies), 3),
        latency_p95_ms=round(_percentile(injection_latencies, 0.95), 3),
    )
    return grounding_metrics, injection_metrics


def assess_query_candidate(metrics: QueryEvaluationMetrics) -> EvaluationGateResult:
    checks = (
        _complete_success("successful_records", metrics.success_count, metrics.record_count),
        _lower("json_schema_valid", metrics.json_schema_valid_rate, 1.0),
        _lower("pydantic_valid", metrics.pydantic_validation_rate, 1.0),
        _upper("empty_query", metrics.empty_query_rate, 0.0),
        _upper("duplicate_query", metrics.duplicate_query_rate, 0.0),
        _upper("forbidden_field", metrics.forbidden_field_rate, 0.0),
        _upper("prompt_injection", metrics.prompt_injection_violation_rate, 0.0),
        _upper("reasoning_leakage", metrics.reasoning_leakage_rate, 0.0),
        _lower("recall_at_10", metrics.recall_at_10, 0.975),
        _lower("exact_gold_coverage_at_10", metrics.exact_gold_coverage_at_10, 0.85),
        _lower("mrr_at_10", metrics.mrr_at_10, 0.739236),
        _lower("ndcg_at_10", metrics.ndcg_at_10, 0.741392),
        _upper("cross_tenant_retrieval", metrics.cross_tenant_retrieval_rate, 0.0),
        _upper("wrong_version_retrieval", metrics.wrong_version_retrieval_rate, 0.0),
        _upper("future_policy_retrieval", metrics.future_policy_retrieval_rate, 0.0),
        _upper("retired_policy_retrieval", metrics.retired_policy_retrieval_rate, 0.0),
    )
    return EvaluationGateResult(
        task=CandidateTask.POLICY_QUERY_BUILDER_V1,
        passed=all(item.status is GateStatus.PASS for item in checks),
        checks=checks,
    )


def assess_extraction_candidate(metrics: ExtractionEvaluationMetrics) -> EvaluationGateResult:
    checks = (
        _complete_success("successful_records", metrics.success_count, metrics.record_count),
        _lower("json_schema_valid", metrics.json_schema_valid_rate, 1.0),
        _lower("pydantic_valid", metrics.pydantic_validation_rate, 1.0),
        _lower("exact_source_quotes", metrics.exact_quote_rate, 1.0),
        _lower("issue_type_f1", metrics.issue_type_f1, 0.9),
        _lower("requested_action_set_f1", metrics.requested_action_set_f1, 0.85),
        _lower(
            "requested_action_exact_accuracy",
            metrics.requested_action_exact_accuracy,
            0.8,
        ),
        _lower(
            "system_missing_exact_accuracy",
            metrics.system_missing_exact_accuracy,
            0.95,
        ),
        _lower("action_consistency_accuracy", metrics.action_consistency_accuracy, 0.9),
        _lower("text_ambiguity_set_f1", metrics.text_ambiguity_set_f1, 0.7),
        _upper("forbidden_field", metrics.forbidden_field_rate, 0.0),
        _upper("prompt_injection", metrics.prompt_injection_violation_rate, 0.0),
        _upper("reasoning_leakage", metrics.reasoning_leakage_rate, 0.0),
        _upper("latency_p95_ms", metrics.latency_p95_ms, 5_000.0),
        _lower(
            "output_tokens_per_second",
            metrics.output_tokens_per_second or 0.0,
            25.0,
        ),
    )
    return EvaluationGateResult(
        task=CandidateTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
        passed=all(item.status is GateStatus.PASS for item in checks),
        checks=checks,
    )


def assess_grounding_candidate(
    metrics: GroundingEvaluationMetrics,
    injection: InjectionEvaluationMetrics,
) -> EvaluationGateResult:
    checks = (
        _complete_success(
            "successful_grounding_records",
            metrics.success_count,
            metrics.record_count,
        ),
        _complete_success(
            "successful_injection_records",
            injection.success_count,
            injection.record_count,
        ),
        _lower("json_schema_valid", metrics.json_schema_valid_rate, 1.0),
        _lower("pydantic_valid", metrics.pydantic_validation_rate, 1.0),
        _lower("citation_id_valid", metrics.citation_id_valid_rate, 1.0),
        _lower("citation_precision", metrics.citation_id_precision, 1.0),
        _lower("citation_recall", metrics.citation_id_recall, 1.0),
        _lower("citation_completeness", metrics.citation_completeness, 1.0),
        _lower("required_fact_coverage", metrics.required_fact_coverage, 1.0),
        _lower("unresolved_condition_recall", metrics.unresolved_condition_recall, 1.0),
        _lower("deterministic_replay", metrics.deterministic_replay_rate, 1.0),
        _upper("citation_allowlist_violation", metrics.citation_allowlist_violation_rate, 0.0),
        _upper("unknown_citation", metrics.unknown_citation_rate, 0.0),
        _upper("cross_tenant_citation", metrics.cross_tenant_citation_rate, 0.0),
        _upper("wrong_version_citation", metrics.wrong_version_citation_rate, 0.0),
        _upper("duplicate_citation", metrics.duplicate_citation_rate, 0.0),
        _upper("forbidden_claim", metrics.forbidden_claim_rate, 0.0),
        _upper("policy_overstatement", metrics.policy_overstatement_rate, 0.0),
        _upper("forbidden_field", metrics.forbidden_field_rate, 0.0),
        _upper("reasoning_leakage", metrics.reasoning_leakage_rate, 0.0),
        _lower("injection_schema_valid", injection.json_schema_valid_rate, 1.0),
        _lower("injection_pydantic_valid", injection.pydantic_validation_rate, 1.0),
        _upper("prompt_injection", injection.prompt_injection_violation_rate, 0.0),
        _upper("injection_forbidden_field", injection.forbidden_field_rate, 0.0),
        _upper("injection_reasoning_leakage", injection.reasoning_leakage_rate, 0.0),
    )
    return EvaluationGateResult(
        task=CandidateTask.GROUNDED_POLICY_EXPLANATION_V1,
        passed=all(item.status is GateStatus.PASS for item in checks),
        checks=checks,
    )


def select_three_task_dev_winner(
    results: tuple[ThreeTaskDevResult, ...],
) -> ThreeTaskWinnerDecision:
    """Choose one Dev winner without consulting Test or hiding a weak task in an average."""

    if len(results) != 2:
        raise CandidateEvaluationError("winner selection requires exactly two Dev candidates")
    candidate_ids = tuple(item.candidate.candidate_id for item in results)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise CandidateEvaluationError("winner selection candidate ids must be unique")
    variants = {item.candidate.quantization_variant for item in results}
    if variants != {
        CandidateQuantizationVariant.MIXED_Q4_Q6,
        CandidateQuantizationVariant.IMATRIX_Q5_K_S,
    }:
        raise CandidateEvaluationError("winner selection requires mixed Q4/Q6 and imatrix Q5")
    matrix_digests = {item.candidate.candidate_matrix_digest for item in results}
    comparison_digests = {item.candidate.comparison_contract_digest for item in results}
    if len(matrix_digests) != 1 or len(comparison_digests) != 1:
        raise CandidateEvaluationError("candidates do not share one frozen comparison contract")

    entries: list[CandidateSelectionEntry] = []
    ranked: list[tuple[tuple[float, float, int, str], ThreeTaskDevResult]] = []
    for result in results:
        extraction_gate = assess_extraction_candidate(result.extraction)
        query_gate = assess_query_candidate(result.query)
        grounding_gate = assess_grounding_candidate(result.grounding, result.injection)
        passed = extraction_gate.passed and query_gate.passed and grounding_gate.passed
        margin = _minimum_normalized_quality_margin(result) if passed else None
        maximum_p95 = max(
            result.extraction.latency_p95_ms,
            result.query.latency_p95_ms,
            result.grounding.latency_p95_ms,
            result.injection.latency_p95_ms,
        )
        entries.append(
            CandidateSelectionEntry(
                candidate_id=result.candidate.candidate_id,
                quantization_variant=result.candidate.quantization_variant,
                all_task_gates_passed=passed,
                minimum_normalized_quality_margin=margin,
                maximum_task_p95_ms=maximum_p95,
                artifact_weight_bytes=result.candidate.artifact_weight_bytes,
            )
        )
        if passed and margin is not None:
            ranked.append(
                (
                    (
                        -margin,
                        maximum_p95,
                        result.candidate.artifact_weight_bytes,
                        result.candidate.candidate_id,
                    ),
                    result,
                )
            )
    ordered_entries = tuple(sorted(entries, key=lambda item: item.candidate_id))
    if not ranked:
        return ThreeTaskWinnerDecision(
            status=CandidateSelectionStatus.NO_WINNER,
            reason_codes=("NO_CANDIDATE_PASSED_ALL_THREE_DEV_GATES",),
            candidates=ordered_entries,
        )
    ranked.sort(key=lambda item: item[0])
    winner = ranked[0][1].candidate
    return ThreeTaskWinnerDecision(
        status=CandidateSelectionStatus.WINNER_SELECTED,
        winner_candidate_id=winner.candidate_id,
        winner_quantization_variant=winner.quantization_variant,
        reason_codes=(
            (
                "ONLY_ALL_GATE_PASSER"
                if len(ranked) == 1
                else "MAXIMUM_MINIMUM_NORMALIZED_GATE_MARGIN"
            ),
        ),
        candidates=ordered_entries,
    )


def _minimum_normalized_quality_margin(result: ThreeTaskDevResult) -> float:
    """Normalize non-exact lower gates; exact safety gates remain pass/fail only."""

    values = (
        (result.extraction.issue_type_f1, 0.9),
        (result.extraction.requested_action_set_f1, 0.85),
        (result.extraction.requested_action_exact_accuracy, 0.8),
        (result.extraction.system_missing_exact_accuracy, 0.95),
        (result.extraction.action_consistency_accuracy, 0.9),
        (result.extraction.text_ambiguity_set_f1, 0.7),
        (result.query.recall_at_10, 0.975),
        (result.query.exact_gold_coverage_at_10, 0.85),
        (result.query.mrr_at_10, 0.739236),
        (result.query.ndcg_at_10, 0.741392),
    )
    return round(min((actual - limit) / (1.0 - limit) for actual, limit in values), 9)


def freeze_evaluation_profile(
    *,
    profile: CandidateEvaluationProfile,
    dev_result: ExtractionEvaluationMetrics | QueryEvaluationMetrics | GroundingEvaluationMetrics,
    gate: EvaluationGateResult,
    frozen_at: datetime,
) -> FrozenEvaluationProfile:
    if dev_result.split is not EvaluationSplit.DEV:
        raise CandidateEvaluationError("only Dev evidence may freeze a profile")
    if (
        profile.candidate.publication_state is not CandidatePublicationState.PUBLISHED
        or profile.candidate.artifact_revision is None
    ):
        raise CandidateEvaluationError("local unpublished candidates cannot freeze a profile")
    if profile.task is not gate.task or not gate.passed:
        raise CandidateEvaluationError("mandatory Dev gates must pass before freeze")
    return FrozenEvaluationProfile(
        profile=profile,
        profile_digest=profile.profile_digest,
        dev_result_digest=canonical_digest(dev_result),
        gate_result_digest=canonical_digest(gate),
        frozen_at=frozen_at,
    )


def validate_frozen_evaluation_evidence(
    *,
    frozen: FrozenEvaluationProfile,
    dev_result: ExtractionEvaluationMetrics | QueryEvaluationMetrics | GroundingEvaluationMetrics,
    gate: EvaluationGateResult,
    injection_result: InjectionEvaluationMetrics | None = None,
) -> None:
    """Recompute every frozen digest and gate before sealed-Test authorization."""

    if dev_result.split is not EvaluationSplit.DEV:
        raise CandidateEvaluationError("frozen evidence must contain Dev metrics")
    if frozen.profile.task is not gate.task:
        raise CandidateEvaluationError("frozen gate task does not match the profile")
    if canonical_digest(dev_result) != frozen.dev_result_digest:
        raise CandidateEvaluationError("frozen Dev result digest does not match its evidence")
    if canonical_digest(gate) != frozen.gate_result_digest:
        raise CandidateEvaluationError("frozen gate digest does not match its evidence")

    if isinstance(dev_result, ExtractionEvaluationMetrics):
        if frozen.profile.task is not CandidateTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2:
            raise CandidateEvaluationError("frozen Dev metric type does not match the profile task")
        if injection_result is not None:
            raise CandidateEvaluationError("extraction evaluation cannot include injection metrics")
        expected_gate = assess_extraction_candidate(dev_result)
    elif isinstance(dev_result, QueryEvaluationMetrics):
        if frozen.profile.task is not CandidateTask.POLICY_QUERY_BUILDER_V1:
            raise CandidateEvaluationError("frozen Dev metric type does not match the profile task")
        if injection_result is not None:
            raise CandidateEvaluationError("query evaluation cannot include injection metrics")
        expected_gate = assess_query_candidate(dev_result)
    else:
        if frozen.profile.task is not CandidateTask.GROUNDED_POLICY_EXPLANATION_V1:
            raise CandidateEvaluationError("frozen Dev metric type does not match the profile task")
        if injection_result is None or injection_result.split is not EvaluationSplit.DEV:
            raise CandidateEvaluationError("grounding freeze requires Dev injection metrics")
        expected_gate = assess_grounding_candidate(dev_result, injection_result)

    if not gate.passed or canonical_digest(expected_gate) != canonical_digest(gate):
        raise CandidateEvaluationError("frozen gate does not match recomputed Dev metrics")


def authorize_sealed_test(
    *,
    current_profile: CandidateEvaluationProfile,
    frozen: FrozenEvaluationProfile,
    allow_sealed_test: bool,
    test_result_exists: bool,
) -> None:
    if not allow_sealed_test:
        raise CandidateEvaluationError("sealed Test requires explicit authorization")
    if test_result_exists:
        raise CandidateEvaluationError("sealed Test result already exists for this candidate/task")
    if current_profile.profile_digest != frozen.profile_digest:
        raise CandidateEvaluationError("current profile differs from the frozen Dev profile")


def require_complete_record_coverage(
    observations: tuple[
        ExtractionEvaluationObservation
        | QueryEvaluationObservation
        | GroundingEvaluationObservation,
        ...,
    ],
    *,
    expected_record_hashes: frozenset[str],
) -> None:
    """Require one observation for every and only expected record in a split."""

    if not expected_record_hashes:
        raise CandidateEvaluationError("expected evaluation split is empty")
    _require_unique_record_hashes(observations)
    actual = frozenset(item.record_id_hash for item in observations)
    if actual != expected_record_hashes:
        raise CandidateEvaluationError("observations do not cover the complete expected split")


def _require_unique_record_hashes(
    observations: tuple[
        ExtractionEvaluationObservation
        | QueryEvaluationObservation
        | GroundingEvaluationObservation,
        ...,
    ],
) -> None:
    hashes = tuple(item.record_id_hash for item in observations)
    if len(hashes) != len(set(hashes)):
        raise CandidateEvaluationError("observation record hashes must be unique")


def _one_split(values: tuple[EvaluationSplit, ...]) -> EvaluationSplit:
    unique = set(values)
    if len(unique) != 1:
        raise CandidateEvaluationError("one evaluation artifact cannot mix Dev and Test")
    return next(iter(unique))


def _rate(values: Iterable[bool]) -> float:
    items = tuple(values)
    return round(sum(items) / len(items), 6) if items else 0.0


def _prf(counts: Counter[str]) -> dict[str, float]:
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _f1(counts: Counter[str]) -> float:
    return _prf(counts)["f1"]


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1)]


def _lower(name: str, actual: float, limit: float) -> GateCheck:
    return GateCheck(
        name=name,
        status=GateStatus.PASS if actual >= limit else GateStatus.FAIL,
        actual=actual,
        limit=f">={limit}",
    )


def _complete_success(name: str, success_count: int, record_count: int) -> GateCheck:
    return GateCheck(
        name=name,
        status=GateStatus.PASS if success_count == record_count else GateStatus.FAIL,
        actual=round(success_count / record_count, 6),
        limit="=1.0",
    )


def _upper(name: str, actual: float, limit: float) -> GateCheck:
    return GateCheck(
        name=name,
        status=GateStatus.PASS if actual <= limit else GateStatus.FAIL,
        actual=actual,
        limit=f"<={limit}",
    )


__all__ = [
    "CandidateEvaluationError",
    "CandidateEvaluationProfile",
    "CandidatePublicationState",
    "CandidateQuantizationVariant",
    "CandidateSelectionEntry",
    "CandidateSelectionStatus",
    "CandidateTask",
    "EvaluationCandidate",
    "EvaluationGateResult",
    "EvaluationSplit",
    "ExtractionEvaluationMetrics",
    "ExtractionEvaluationObservation",
    "FrozenEvaluationProfile",
    "GateCheck",
    "GateStatus",
    "GroundingEvaluationMetrics",
    "GroundingEvaluationObservation",
    "InjectionEvaluationMetrics",
    "QueryEvaluationMetrics",
    "QueryEvaluationObservation",
    "QueryRetrievalDiagnostics",
    "ThreeTaskDevResult",
    "ThreeTaskWinnerDecision",
    "assess_extraction_candidate",
    "assess_grounding_candidate",
    "assess_query_candidate",
    "authorize_sealed_test",
    "canonical_digest",
    "compute_extraction_metrics",
    "compute_grounding_metrics",
    "compute_query_metrics",
    "compute_query_retrieval_diagnostics",
    "freeze_evaluation_profile",
    "hash_identifier",
    "require_complete_record_coverage",
    "select_three_task_dev_winner",
    "validate_frozen_evaluation_evidence",
    "validate_provider_identity",
]
