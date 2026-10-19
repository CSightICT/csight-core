from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.candidate_evaluation import hash_identifier
from app.platform.shadow_evidence import (
    Shadow100Evidence,
    ShadowEvidenceError,
    ShadowForbiddenEvents,
    ShadowTask,
    ShadowTaskObservation,
    ShadowTaskStatus,
    collect_shadow100_evidence,
)

DIGEST = "sha256:" + "a" * 64


def _observations() -> tuple[ShadowTaskObservation, ...]:
    return tuple(
        ShadowTaskObservation(
            case_id_hash=hash_identifier(f"synthetic-case-{case_index}"),
            task=task,
            status=ShadowTaskStatus.SUCCEEDED,
            terminal=True,
            candidate_id="qwen38-csight-q4km",
            release_manifest_digest=DIGEST,
            route_plan_digest=DIGEST,
            profile_digest=DIGEST,
            prompt_digest=DIGEST,
            schema_digest=DIGEST,
            runtime_identity_digest=DIGEST,
            baseline_result_digest=hash_identifier(f"baseline-{case_index}-{task.value}"),
            candidate_result_digest=hash_identifier(f"candidate-{case_index}-{task.value}"),
            baseline_contract_agreement=True,
            safety_contract_passed=True,
            latency_ms=10,
        )
        for case_index in range(100)
        for task in ShadowTask
    )


def _zero_events() -> ShadowForbiddenEvents:
    return ShadowForbiddenEvents(
        policy_decision_events=0,
        human_review_events=0,
        resolution_events=0,
        external_action_events=0,
    )


@pytest.mark.unit
def test_shadow100_requires_three_terminal_tasks_for_exactly_100_cases() -> None:
    evidence = collect_shadow100_evidence(
        observations=_observations(),
        forbidden_events=_zero_events(),
        primary_route_before_digest=DIGEST,
        primary_route_after_digest=DIGEST,
        collected_at=datetime(2026, 8, 31, tzinfo=UTC),
    )
    assert evidence.synthetic_case_count == 100
    assert evidence.complete_chain_count == 100
    assert tuple(item.requested_cases for item in evidence.task_summaries) == (100, 100, 100)
    assert evidence.forbidden_events.total == 0
    assert evidence.raw_customer_text_retained is False


@pytest.mark.unit
def test_shadow100_fails_on_forbidden_event_or_primary_route_change() -> None:
    events = _zero_events().model_copy(update={"human_review_events": 1})
    with pytest.raises(ShadowEvidenceError, match="decision-bearing"):
        collect_shadow100_evidence(
            observations=_observations(),
            forbidden_events=events,
            primary_route_before_digest=DIGEST,
            primary_route_after_digest=DIGEST,
            collected_at=datetime(2026, 8, 31, tzinfo=UTC),
        )
    with pytest.raises(ShadowEvidenceError, match="release contract"):
        collect_shadow100_evidence(
            observations=_observations(),
            forbidden_events=_zero_events(),
            primary_route_before_digest=DIGEST,
            primary_route_after_digest="sha256:" + "b" * 64,
            collected_at=datetime(2026, 8, 31, tzinfo=UTC),
        )


@pytest.mark.unit
def test_shadow100_fails_when_any_task_chain_is_missing() -> None:
    with pytest.raises(ShadowEvidenceError, match="complete task chain"):
        collect_shadow100_evidence(
            observations=_observations()[:-1],
            forbidden_events=_zero_events(),
            primary_route_before_digest=DIGEST,
            primary_route_after_digest=DIGEST,
            collected_at=datetime(2026, 8, 31, tzinfo=UTC),
        )


@pytest.mark.unit
def test_shadow100_rejects_all_failed_terminal_observations() -> None:
    failed = tuple(
        item.model_copy(
            update={
                "status": ShadowTaskStatus.FAILED,
                "baseline_contract_agreement": False,
                "safety_contract_passed": False,
            }
        )
        for item in _observations()
    )

    with pytest.raises(ShadowEvidenceError, match="release contract"):
        collect_shadow100_evidence(
            observations=failed,
            forbidden_events=_zero_events(),
            primary_route_before_digest=DIGEST,
            primary_route_after_digest=DIGEST,
            collected_at=datetime(2026, 8, 31, tzinfo=UTC),
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", ShadowTaskStatus.FAILED),
        ("baseline_contract_agreement", False),
        ("safety_contract_passed", False),
    ),
)
def test_shadow100_rejects_one_failed_or_unqualified_observation(
    field: str,
    value: object,
) -> None:
    observations = list(_observations())
    observations[0] = observations[0].model_copy(update={field: value})

    with pytest.raises(ShadowEvidenceError, match="release contract"):
        collect_shadow100_evidence(
            observations=tuple(observations),
            forbidden_events=_zero_events(),
            primary_route_before_digest=DIGEST,
            primary_route_after_digest=DIGEST,
            collected_at=datetime(2026, 8, 31, tzinfo=UTC),
        )


@pytest.mark.unit
def test_shadow100_recomputes_evidence_digest_on_load() -> None:
    evidence = collect_shadow100_evidence(
        observations=_observations(),
        forbidden_events=_zero_events(),
        primary_route_before_digest=DIGEST,
        primary_route_after_digest=DIGEST,
        collected_at=datetime(2026, 8, 31, tzinfo=UTC),
    )
    payload = evidence.model_dump(mode="json")
    payload["evidence_digest"] = "sha256:" + "b" * 64

    with pytest.raises(ValidationError, match="digest does not match"):
        Shadow100Evidence.model_validate(payload)
