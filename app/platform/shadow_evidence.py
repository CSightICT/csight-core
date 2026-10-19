"""Privacy-safe evidence contract for the 100-case advisory-only SHADOW gate."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"


class ShadowEvidenceError(ValueError):
    """Shadow evidence is incomplete, mixed, or contains a forbidden side effect."""


class ShadowTask(StrEnum):
    EXTRACTION = "PRODUCT_DEFECT_TEXT_EXTRACTION_V2"
    QUERY_BUILDER = "POLICY_QUERY_BUILDER_V1"
    GROUNDING = "GROUNDED_POLICY_EXPLANATION_V1"


class ShadowTaskStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ShadowTaskObservation(_Contract):
    schema_version: Literal["shadow_task_observation/1.0.0"] = "shadow_task_observation/1.0.0"
    case_id_hash: str = Field(pattern=_DIGEST_PATTERN)
    task: ShadowTask
    status: ShadowTaskStatus
    terminal: Literal[True]
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    release_manifest_digest: str = Field(pattern=_DIGEST_PATTERN)
    route_plan_digest: str = Field(pattern=_DIGEST_PATTERN)
    profile_digest: str = Field(pattern=_DIGEST_PATTERN)
    prompt_digest: str = Field(pattern=_DIGEST_PATTERN)
    schema_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    baseline_result_digest: str = Field(pattern=_DIGEST_PATTERN)
    candidate_result_digest: str = Field(pattern=_DIGEST_PATTERN)
    baseline_contract_agreement: bool
    safety_contract_passed: bool
    latency_ms: float = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    raw_customer_text_retained: Literal[False] = False
    raw_model_output_retained: Literal[False] = False


class ShadowForbiddenEvents(_Contract):
    policy_decision_events: int = Field(ge=0)
    human_review_events: int = Field(ge=0)
    resolution_events: int = Field(ge=0)
    external_action_events: int = Field(ge=0)

    @property
    def total(self) -> int:
        return (
            self.policy_decision_events
            + self.human_review_events
            + self.resolution_events
            + self.external_action_events
        )


class ShadowTaskSummary(_Contract):
    task: ShadowTask
    requested_cases: int = Field(ge=0)
    terminal_cases: int = Field(ge=0)
    succeeded_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    baseline_contract_agreement_rate: float = Field(ge=0, le=1)
    safety_contract_pass_rate: float = Field(ge=0, le=1)
    metadata_complete_rate: float = Field(ge=0, le=1)


class Shadow100Evidence(_Contract):
    schema_version: Literal["shadow100_evidence/1.0.0"] = "shadow100_evidence/1.0.0"
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    release_manifest_digest: str = Field(pattern=_DIGEST_PATTERN)
    route_plan_digest: str = Field(pattern=_DIGEST_PATTERN)
    profile_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    synthetic_case_count: Literal[100] = 100
    complete_chain_count: Literal[100] = 100
    task_summaries: tuple[ShadowTaskSummary, ...] = Field(min_length=3, max_length=3)
    forbidden_events: ShadowForbiddenEvents
    all_terminal: bool
    metadata_complete: bool
    primary_route_unchanged: bool
    raw_customer_text_retained: Literal[False] = False
    raw_model_output_retained: Literal[False] = False
    collected_at: datetime
    evidence_digest: str = Field(pattern=_DIGEST_PATTERN)

    @field_validator("collected_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_advisory_only_pass(self) -> Self:
        if tuple(item.task for item in self.task_summaries) != tuple(ShadowTask):
            raise ValueError("task summaries must use the canonical three-task order")
        for summary in self.task_summaries:
            if (
                summary.requested_cases != 100
                or summary.terminal_cases != 100
                or summary.succeeded_cases != 100
                or summary.failed_cases != 0
            ):
                raise ValueError(
                    "each SHADOW task requires exactly 100 successful terminal cases and zero "
                    "failures"
                )
            if (
                summary.baseline_contract_agreement_rate != 1.0
                or summary.safety_contract_pass_rate != 1.0
                or summary.metadata_complete_rate != 1.0
            ):
                raise ValueError(
                    "each SHADOW task requires complete baseline, safety, and metadata evidence"
                )
        if self.forbidden_events.total:
            raise ValueError("SHADOW evidence contains a forbidden downstream event")
        if not self.all_terminal or not self.metadata_complete or not self.primary_route_unchanged:
            raise ValueError("SHADOW evidence is not release-gate complete")
        expected_digest = _digest(self.model_dump(mode="python", exclude={"evidence_digest"}))
        if self.evidence_digest != expected_digest:
            raise ValueError("SHADOW evidence digest does not match its contents")
        return self


def collect_shadow100_evidence(
    *,
    observations: tuple[ShadowTaskObservation, ...],
    forbidden_events: ShadowForbiddenEvents,
    primary_route_before_digest: str,
    primary_route_after_digest: str,
    collected_at: datetime,
) -> Shadow100Evidence:
    """Aggregate exactly 100 complete synthetic chains without exposing operational UUIDs."""

    if forbidden_events.total:
        raise ShadowEvidenceError("SHADOW created decision-bearing or external events")
    if not observations:
        raise ShadowEvidenceError("SHADOW observations are missing")
    identity_fields = (
        "candidate_id",
        "release_manifest_digest",
        "route_plan_digest",
        "profile_digest",
        "runtime_identity_digest",
    )
    identities: dict[str, str] = {}
    for field in identity_fields:
        identity_values = {str(getattr(item, field)) for item in observations}
        if len(identity_values) != 1:
            raise ShadowEvidenceError(f"SHADOW observations mix {field}")
        identities[field] = next(iter(identity_values))
    by_case: dict[str, list[ShadowTaskObservation]] = defaultdict(list)
    for item in observations:
        by_case[item.case_id_hash].append(item)
    if len(by_case) != 100:
        raise ShadowEvidenceError("the SHADOW gate requires exactly 100 synthetic cases")
    for case_hash, items in by_case.items():
        tasks = tuple(item.task for item in items)
        if len(items) != 3 or set(tasks) != set(ShadowTask):
            raise ShadowEvidenceError(f"case {case_hash} does not contain one complete task chain")
    summaries: list[ShadowTaskSummary] = []
    for task in ShadowTask:
        items = tuple(item for item in observations if item.task is task)
        statuses = Counter(item.status for item in items)
        summaries.append(
            ShadowTaskSummary(
                task=task,
                requested_cases=len(items),
                terminal_cases=sum(item.terminal for item in items),
                succeeded_cases=statuses[ShadowTaskStatus.SUCCEEDED],
                failed_cases=statuses[ShadowTaskStatus.FAILED],
                baseline_contract_agreement_rate=_rate(
                    item.baseline_contract_agreement for item in items
                ),
                safety_contract_pass_rate=_rate(item.safety_contract_passed for item in items),
                metadata_complete_rate=_rate(_metadata_complete(item) for item in items),
            )
        )
    values: dict[str, object] = {
        "schema_version": "shadow100_evidence/1.0.0",
        **identities,
        "synthetic_case_count": 100,
        "complete_chain_count": 100,
        "task_summaries": tuple(summaries),
        "forbidden_events": forbidden_events,
        "all_terminal": all(item.terminal for item in observations),
        "metadata_complete": all(_metadata_complete(item) for item in observations),
        "primary_route_unchanged": primary_route_before_digest == primary_route_after_digest,
        "raw_customer_text_retained": False,
        "raw_model_output_retained": False,
        "collected_at": collected_at,
    }
    values["evidence_digest"] = _digest(values)
    try:
        return Shadow100Evidence.model_validate(values)
    except ValueError as error:
        raise ShadowEvidenceError("SHADOW evidence failed its release contract") from error


def _metadata_complete(item: ShadowTaskObservation) -> bool:
    return all(
        (
            item.release_manifest_digest,
            item.route_plan_digest,
            item.profile_digest,
            item.prompt_digest,
            item.schema_digest,
            item.runtime_identity_digest,
            item.baseline_result_digest,
            item.candidate_result_digest,
        )
    )


def _rate(values: Iterable[bool]) -> float:
    items = tuple(values)
    return round(sum(items) / len(items), 6) if items else 0.0


def _digest(value: dict[str, object]) -> str:
    encoded = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "Shadow100Evidence",
    "ShadowEvidenceError",
    "ShadowForbiddenEvents",
    "ShadowTask",
    "ShadowTaskObservation",
    "ShadowTaskStatus",
    "ShadowTaskSummary",
    "collect_shadow100_evidence",
]
