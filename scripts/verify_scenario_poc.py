"""Fail-closed acceptance gate for the synthetic hard-plastic scenario PoC pack.

This gate is deliberately separate from ``verify_poc_readiness.py``.  It can accept a
synthetic, offline scenario pack while continuing to report that an unavailable Vision
endpoint/checkpoint blocks runtime model integration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK_DIR = ROOT / "evaluation/scenario_poc_hard_plastic_v1"
DEFAULT_REPORT_NAME = "results/acceptance_report.json"
REPORT_SCHEMA_VERSION = "scenario_poc_acceptance_report/1.0.0"

REQUIRED_ARTIFACTS = (
    "cases.jsonl",
    "policy.json",
    "gold.jsonl",
    "demo_scenarios.json",
    "model_manifest.json",
)
MINIMUM_CASE_COUNT = 30
SAFE_CLAIMS_BOUNDARY: Mapping[str, object] = {
    "actual_company_data_used": False,
    "actual_customer_data_used": False,
    "actual_company_policy_used": False,
    "checkpoint_included": False,
    "vision_endpoint_included": False,
    "report_metrics_reproduced_by_csight": False,
    "automatic_final_decision_allowed": False,
    "live_external_action_allowed": False,
    "actual_performance_or_roi_claim_allowed": False,
    "verdict": "SYNTHETIC_SCENARIO_TECHNICAL_POC",
}


class ScenarioPocVerdict(StrEnum):
    READY = "SCENARIO_TECH_POC_READY"
    BLOCKED = "BLOCKED"


class OfflinePackStatus(StrEnum):
    READY = "OFFLINE_SCENARIO_PACK_READY"
    BLOCKED = "OFFLINE_SCENARIO_PACK_BLOCKED"


class RuntimeVisionStatus(StrEnum):
    READY = "RUNTIME_VISION_INTEGRATION_READY"
    BLOCKED = "RUNTIME_VISION_INTEGRATION_BLOCKED"


@dataclass(frozen=True, slots=True)
class AcceptanceCheck:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ScenarioPocAssessment:
    verdict: ScenarioPocVerdict
    offline_status: OfflinePackStatus
    runtime_status: RuntimeVisionStatus
    offline_checks: tuple[AcceptanceCheck, ...]
    runtime_blockers: tuple[str, ...]
    pack_dir: str

    @property
    def passed(self) -> bool:
        """Whether today's offline scenario-technology PoC pack is ready."""

        return self.verdict is ScenarioPocVerdict.READY

    @property
    def offline_failures(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.offline_checks if not check.passed)

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "passed": self.passed,
            "offline_scenario_pack": {
                "status": self.offline_status.value,
                "failures": list(self.offline_failures),
                "checks": [check.to_dict() for check in self.offline_checks],
            },
            "runtime_vision_integration": {
                "status": self.runtime_status.value,
                "blockers": list(self.runtime_blockers),
            },
            "claim_boundary": {
                "allowed": "SYNTHETIC_SCENARIO_TECH_POC",
                "forbidden": [
                    "LIMITED_POC",
                    "REAL_CUSTOMER_PERFORMANCE",
                    "REAL_COMPANY_POLICY_VALIDATION",
                    "ROI_OR_COST_REDUCTION",
                    "NORMAL_CLASSIFICATION_BELOW_THRESHOLD",
                ],
            },
            "pack_dir": self.pack_dir,
        }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _integer(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> tuple[object | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _load_jsonl(path: Path) -> tuple[list[Mapping[str, object]], str | None]:
    records: list[Mapping[str, object]] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, Mapping):
                return [], f"line {line_number} is not a JSON object"
            records.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    return records, None


def _check(name: str, passed: bool, detail: str) -> AcceptanceCheck:
    return AcceptanceCheck(name=name, passed=passed, detail=detail)


def _valid_iso_date(value: object) -> bool:
    text = _text(value)
    if text is None:
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _display_path(path: Path) -> str:
    """Avoid persisting host-specific absolute paths in acceptance evidence."""

    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _case_ids(records: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    return tuple(record_id for record in records if (record_id := _text(record.get("record_id"))))


def _validate_artifact_hashes(pack_dir: Path, manifest: Mapping[str, object]) -> tuple[bool, str]:
    raw_hashes = _mapping(manifest.get("artifact_hashes"))
    if set(raw_hashes) != set(REQUIRED_ARTIFACTS):
        return False, "artifact_hashes must contain exactly the five required artifacts"
    expected_hashes: dict[str, str] = {}
    actual_hashes: dict[str, str] = {}
    for filename in REQUIRED_ARTIFACTS:
        expected = _text(raw_hashes.get(filename))
        path = pack_dir / filename
        if expected is None or len(expected) != 64 or not path.is_file():
            return False, f"missing or invalid hash entry: {filename}"
        expected_hashes[filename] = expected
        actual_hashes[filename] = _sha256_file(path)
    mismatched = sorted(
        filename
        for filename in REQUIRED_ARTIFACTS
        if expected_hashes[filename] != actual_hashes[filename]
    )
    if mismatched:
        return False, "hash mismatch: " + ", ".join(mismatched)
    expected_pack_hash = _text(manifest.get("pack_hash"))
    actual_pack_hash = _canonical_hash(dict(sorted(expected_hashes.items())))
    if expected_pack_hash != actual_pack_hash:
        return False, "pack_hash does not seal artifact_hashes"
    return True, f"five artifacts sealed by pack_hash={actual_pack_hash}"


def _validate_case_records(
    records: Sequence[Mapping[str, object]], manifest: Mapping[str, object]
) -> tuple[bool, str]:
    record_count = _integer(manifest.get("record_count"))
    identifiers = _case_ids(records)
    structurally_complete = all(
        _text(record.get("split")) is not None
        and bool(_sequence(record.get("scenario_tags")))
        and _text(_mapping(record.get("case_input")).get("customer_message")) is not None
        for record in records
    )
    split_counts = _mapping(manifest.get("split_counts"))
    actual_splits: dict[str, int] = {}
    for record in records:
        split = _text(record.get("split"))
        if split is not None:
            actual_splits[split] = actual_splits.get(split, 0) + 1
    expected_splits = {
        key: count for key, value in split_counts.items() if (count := _integer(value)) is not None
    }
    passed = (
        len(records) >= MINIMUM_CASE_COUNT
        and record_count == len(records)
        and len(identifiers) == len(records)
        and len(set(identifiers)) == len(records)
        and structurally_complete
        and expected_splits == actual_splits
    )
    return (
        passed,
        f"records={len(records)} unique_ids={len(set(identifiers))} splits={actual_splits}",
    )


def _complete_gold_record(record: Mapping[str, object]) -> bool:
    expected = _mapping(record.get("expected"))
    vision = _mapping(expected.get("vision"))
    review = _mapping(expected.get("review"))
    resolution = _mapping(expected.get("resolution"))
    required_expected_keys = {
        "issue_types",
        "issue_evidence_basis",
        "vision",
        "policy_clause_ids",
        "policy_effects",
        "review",
        "resolution",
    }
    required_vision_keys = {
        "score_band",
        "business_interpretation",
        "type_or_location_claim_allowed",
    }
    required_review_keys = {"task_type", "required_role", "human_decision"}
    required_resolution_keys = {
        "status",
        "intent_count",
        "attempt_count",
        "result_count",
        "side_effects_performed",
    }
    counts = tuple(
        _integer(resolution.get(key)) for key in ("intent_count", "attempt_count", "result_count")
    )
    forbidden_outcomes = record.get("forbidden_outcomes", expected.get("forbidden_outcomes"))
    required_forbidden_outcomes = {
        "AUTOMATED_DECISION",
        "LIVE_EXTERNAL_ACTION",
        "VISION_CONFIRMED_DEFECT_TYPE",
        "VISION_CONFIRMED_DEFECT_LOCATION",
        "NORMAL_FROM_LOW_SCORE",
        "PARAMETER_INFERENCE",
    }
    actual_forbidden_outcomes = {
        outcome for item in _sequence(forbidden_outcomes) if (outcome := _text(item)) is not None
    }
    score_band = _text(vision.get("score_band"))
    business_interpretation = _text(vision.get("business_interpretation"))
    safe_interpretation = (
        (
            score_band == "HIGH_CANDIDATE"
            and business_interpretation == "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
        )
        or (score_band == "BELOW_THRESHOLD" and business_interpretation == "NOT_NORMAL")
        or (
            score_band == "UNAVAILABLE"
            and business_interpretation in {"VISION_TIMEOUT", "NO_VISION_EVIDENCE"}
        )
    )
    return (
        _text(record.get("record_id")) is not None
        and required_expected_keys <= set(expected)
        and required_vision_keys <= set(vision)
        and required_review_keys <= set(review)
        and required_resolution_keys <= set(resolution)
        and isinstance(vision.get("type_or_location_claim_allowed"), bool)
        and vision.get("type_or_location_claim_allowed") is False
        and safe_interpretation
        and all(count is not None and count >= 0 for count in counts)
        and resolution.get("side_effects_performed") is False
        and isinstance(expected.get("issue_types"), list)
        and isinstance(expected.get("policy_clause_ids"), list)
        and isinstance(expected.get("policy_effects"), list)
        and required_forbidden_outcomes <= actual_forbidden_outcomes
    )


def _validate_gold(
    gold: Sequence[Mapping[str, object]],
    cases: Sequence[Mapping[str, object]],
    policy: Mapping[str, object],
) -> tuple[bool, str]:
    case_ids = set(_case_ids(cases))
    gold_ids = _case_ids(gold)
    policy_clause_ids = {
        clause_id
        for item in _sequence(policy.get("clauses"))
        if (clause_id := _text(_mapping(item).get("clause_id"))) is not None
    }
    gold_clause_ids = tuple(
        clause_id
        for record in gold
        for item in _sequence(_mapping(record.get("expected")).get("policy_clause_ids"))
        if (clause_id := _text(item)) is not None
    )
    missing_clause_ids = set(gold_clause_ids) - policy_clause_ids
    passed = (
        len(gold) == len(cases)
        and len(gold_ids) == len(gold)
        and len(set(gold_ids)) == len(gold)
        and set(gold_ids) == case_ids
        and all(_complete_gold_record(record) for record in gold)
        and len(gold_clause_ids) >= len(gold)
        and not missing_clause_ids
    )
    return (
        passed,
        f"gold={len(gold)} linked_cases={len(set(gold_ids) & case_ids)} "
        f"missing_policy_clauses={len(missing_clause_ids)}",
    )


def _validate_policy(policy: Mapping[str, object]) -> tuple[bool, str]:
    document = _mapping(policy.get("document")) or policy
    version = _text(document.get("policy_version")) or _text(document.get("version"))
    effective_from = document.get("effective_from", document.get("effective_date"))
    effective_to = document.get("effective_to")
    clauses = _sequence(policy.get("clauses"))
    guardrails = _mapping(policy.get("global_guardrails"))
    clauses_complete = bool(clauses) and all(
        _text(_mapping(clause).get("clause_id")) is not None
        and _text(_mapping(clause).get("text")) is not None
        and _mapping(clause).get("version") == version
        and _mapping(clause).get("effective_from") == effective_from
        for clause in clauses
    )
    passed = (
        policy.get("source_type") == "SYNTHETIC_REFERENCE"
        and version is not None
        and _valid_iso_date(effective_from)
        and (effective_to is None or _valid_iso_date(effective_to))
        and document.get("status") == "ACTIVE"
        and document.get("fictional") is True
        and document.get("legal_or_commercial_effect") is False
        and clauses_complete
        and guardrails.get("final_decision_owner") == "AUTHENTICATED_HUMAN"
        and guardrails.get("automatic_approval_allowed") is False
        and guardrails.get("parameter_inference_allowed") is False
        and guardrails.get("external_action_mode") == "DRY_RUN"
        and guardrails.get("live_external_action_allowed") is False
        and guardrails.get("side_effects_performed") is False
        and guardrails.get("actual_performance_or_roi_claim_allowed") is False
    )
    return passed, f"version={version or 'MISSING'} clauses={len(clauses)}"


def _validate_demo_scenarios(
    payload: Mapping[str, object],
    manifest: Mapping[str, object],
    case_ids: set[str],
    gold: Sequence[Mapping[str, object]],
) -> tuple[bool, str]:
    required_assertions: dict[str, Mapping[str, object]] = {
        "COMPLETE_VISIBLE_BREAKAGE_DRY_RUN_VALIDATED": {
            "human_decision_required": True,
            "resolution_status": "ACTION_DRY_RUN_VALIDATED",
            "intent_count": 1,
            "attempt_count": 1,
            "result_count": 1,
            "side_effects_performed": False,
        },
        "REFUND_INPUT_MISSING_NO_ATTEMPT": {
            "human_decision_required": True,
            "resolution_status": "ACTION_NEEDS_INPUT",
            "intent_count": 0,
            "attempt_count": 0,
            "result_count": 0,
            "parameter_inference": False,
        },
        "FUNCTIONAL_FAILURE_STILL_UNCONFIRMED_REQUEST_EVIDENCE": {
            "functional_failure_source": "TEXT_CLAIM",
            "still_image_confirms_function": False,
            "review_task_type": "EVIDENCE_REVIEW",
            "human_decision_count": 0,
            "intent_count": 0,
            "attempt_count": 0,
            "result_count": 0,
        },
        "SAFETY_REVIEWER_BLOCKED_ADMIN_RESOLVE": {
            "required_role": "ADMIN",
            "reviewer_claim_allowed": False,
            "resolution_status": "ACTION_DRY_RUN_VALIDATED",
            "side_effects_performed": False,
            "live_external_action": False,
        },
        "VISION_TIMEOUT_PARTIAL_SUCCESS_NO_ACTION": {
            "analysis_outcome": "PARTIAL_SUCCESS",
            "vision_status": "TIMEOUT",
            "human_review_required": True,
            "human_decision_count": 0,
            "intent_count": 0,
            "attempt_count": 0,
            "result_count": 0,
        },
    }
    scenarios = tuple(_mapping(item) for item in _sequence(payload.get("scenarios")))
    manifest_ids = {
        scenario_id
        for item in _sequence(manifest.get("demo_scenario_ids"))
        if (scenario_id := _text(item)) is not None
    }
    scenario_ids = tuple(
        scenario_id
        for item in scenarios
        if (scenario_id := _text(item.get("scenario_id"))) is not None
    )
    boundaries = tuple(
        boundary for item in scenarios if (boundary := _text(item.get("boundary"))) is not None
    )
    linked_ids = tuple(
        case_id for item in scenarios if (case_id := _text(item.get("case_record_id"))) is not None
    )
    assertions_complete = all(
        (boundary := _text(item.get("boundary"))) in required_assertions
        and all(
            _mapping(item.get("expected_assertions")).get(key) == value
            for key, value in required_assertions[boundary].items()
        )
        for item in scenarios
    )
    gold_by_id = {
        record_id: record
        for record in gold
        if (record_id := _text(record.get("record_id"))) is not None
    }
    common_resolution_keys = ("intent_count", "attempt_count", "result_count")
    gold_aligned = True
    for scenario in scenarios:
        record_id = _text(scenario.get("case_record_id"))
        gold_record = gold_by_id.get(record_id or "", {})
        expected = _mapping(gold_record.get("expected"))
        resolution = _mapping(expected.get("resolution"))
        review = _mapping(expected.get("review"))
        assertions = _mapping(scenario.get("expected_assertions"))
        for key in common_resolution_keys:
            if key in assertions and assertions.get(key) != resolution.get(key):
                gold_aligned = False
        if "resolution_status" in assertions and assertions.get(
            "resolution_status"
        ) != resolution.get("status"):
            gold_aligned = False
        if "side_effects_performed" in assertions and assertions.get(
            "side_effects_performed"
        ) != resolution.get("side_effects_performed"):
            gold_aligned = False
        for assertion_key, review_key in (
            ("required_role", "required_role"),
            ("reviewer_claim_allowed", "reviewer_claim_allowed"),
            ("review_task_type", "task_type"),
        ):
            if assertion_key in assertions and assertions.get(assertion_key) != review.get(
                review_key
            ):
                gold_aligned = False
        if "human_decision_count" in assertions:
            decision_count = 0 if review.get("human_decision") is None else 1
            if assertions.get("human_decision_count") != decision_count:
                gold_aligned = False
    scenario_count = _integer(payload.get("scenario_count"))
    passed = (
        len(scenarios) == 5
        and scenario_count == 5
        and len(set(scenario_ids)) == 5
        and set(scenario_ids) == manifest_ids
        and set(boundaries) == set(required_assertions)
        and len(linked_ids) == 5
        and all(case_id in case_ids for case_id in linked_ids)
        and assertions_complete
        and gold_aligned
    )
    return passed, f"scenarios={len(scenarios)} boundaries={sorted(set(boundaries))}"


def _validate_model_manifest(
    model: Mapping[str, object], scenario_manifest: Mapping[str, object]
) -> tuple[bool, str]:
    decision = _mapping(model.get("decision_boundary"))
    capabilities = _mapping(model.get("capabilities"))
    threshold = _number(decision.get("threshold", model.get("threshold")))
    source_reports = _sequence(model.get("source_reports")) or _sequence(
        scenario_manifest.get("source_reports")
    )
    task = _text(model.get("task"))
    candidate = _mapping(model.get("candidate"))
    held_out = _mapping(model.get("held_out_test"))
    threshold_metrics = _mapping(held_out.get("threshold_metrics"))
    recommended_slice = _mapping(model.get("recommended_slice"))
    defect_slices = tuple(
        _mapping(item) for item in _sequence(recommended_slice.get("defect_slices"))
    )
    defect_slice_names = {
        label for item in defect_slices if (label := _text(item.get("kaputt_label"))) is not None
    }
    forbidden_claims = {
        claim
        for item in _sequence(model.get("forbidden_claims"))
        if (claim := _text(item)) is not None
    }
    required_forbidden_claims = {
        "PRODUCT_SPECIFIC_ACCURACY",
        "ACTUAL_CUSTOMER_PERFORMANCE",
        "AUTOMATED_NORMAL_DECISION",
        "AUTOMATED_REFUND_OR_EXCHANGE",
        "ROI_OR_COST_SAVINGS",
        "DEFECT_TYPE_OR_LOCATION_FROM_BINARY_SCORE",
    }
    safe_capabilities = all(
        capabilities.get(key) is False for key in ("defect_type", "defect_location", "bounding_box")
    )
    passed = (
        model.get("source_type") == "SUPPLIED_OFFLINE_REPORT"
        and task == "BINARY_ANY_DEFECT_CLASSIFICATION"
        and threshold == 0.8984375
        and decision.get("advisory_only") is True
        and decision.get("below_threshold") == "NOT_NORMAL"
        and safe_capabilities
        and decision.get("automatic_decision_allowed") is False
        and candidate.get("model_family") == "facebook/dinov2-small"
        and candidate.get("experiment") == "E3"
        and candidate.get("selected_epoch") == 10
        and candidate.get("artifact_included_in_pack") is False
        and candidate.get("serving_endpoint_included_in_pack") is False
        and held_out.get("image_count") == 10067
        and held_out.get("ap_any_defect") == 0.884863
        and held_out.get("auroc") == 0.931604
        and threshold_metrics.get("precision") == 0.954333
        and threshold_metrics.get("recall") == 0.508422
        and len(_text(held_out.get("prediction_sha256")) or "") == 64
        and recommended_slice.get("material") == "plastic_hard"
        and {"deconstruction", "actuation"} <= defect_slice_names
        and model.get("product_domain_status") == "NOT_EVALUATED"
        and model.get("report_metrics_reproduced_by_csight") is False
        and model.get("qualification_status") == "SUPPLIED_OFFLINE_REPORT_WITH_LIMITATIONS"
        and required_forbidden_claims <= forbidden_claims
        and len(source_reports) >= 2
    )
    return (
        passed,
        f"task={task or 'MISSING'} threshold={threshold} "
        f"candidate={candidate.get('experiment', 'MISSING')}",
    )


def _runtime_vision_status(
    model: Mapping[str, object],
) -> tuple[RuntimeVisionStatus, tuple[str, ...]]:
    blockers: list[str] = []
    candidate = _mapping(model.get("candidate"))
    integration_status = _text(model.get("runtime_integration_status"))
    checkpoint_status = _text(model.get("checkpoint_package_status"))
    endpoint = _text(model.get("endpoint")) or _text(model.get("endpoint_ref"))
    endpoint_included = candidate.get("serving_endpoint_included_in_pack") is True
    checkpoint_included = candidate.get("artifact_included_in_pack") is True
    if integration_status not in {"AVAILABLE", "READY", "QUALIFIED"} and not endpoint_included:
        blockers.append("VISION_ENDPOINT_NOT_AVAILABLE")
    if checkpoint_status not in {"AVAILABLE", "READY", "PACKAGED"} and not checkpoint_included:
        blockers.append("VISION_CHECKPOINT_PACKAGE_NOT_AVAILABLE")
    if endpoint is None:
        blockers.append("VISION_ENDPOINT_REFERENCE_MISSING")
    # This runner is intentionally offline. Manifest declarations can describe
    # discoverable artifacts, but cannot prove that a private endpoint is alive,
    # serves the declared checkpoint, and passes the canonical contract smoke.
    blockers.append("VISION_RUNTIME_PROBE_NOT_EXECUTED")
    return RuntimeVisionStatus.BLOCKED, tuple(blockers)


def assess_scenario_poc(pack_dir: Path) -> ScenarioPocAssessment:
    """Assess a checked-in synthetic scenario pack without contacting model services."""

    checks: list[AcceptanceCheck] = []
    required_paths = (pack_dir / "manifest.json", *(pack_dir / name for name in REQUIRED_ARTIFACTS))
    missing = [path.name for path in required_paths if not path.is_file()]
    checks.append(
        _check(
            "required_artifacts_exist",
            not missing,
            "all required artifacts exist" if not missing else "missing: " + ", ".join(missing),
        )
    )

    manifest_value, manifest_error = _load_json(pack_dir / "manifest.json")
    manifest = _mapping(manifest_value)
    checks.append(
        _check(
            "manifest_is_valid_json_object",
            manifest_error is None and bool(manifest),
            manifest_error or "manifest parsed",
        )
    )
    checks.append(
        _check(
            "synthetic_claim_boundary",
            manifest.get("source_type") == "SYNTHETIC_REFERENCE"
            and _mapping(manifest.get("claims_boundary")) == SAFE_CLAIMS_BOUNDARY,
            (
                "source_type=SYNTHETIC_REFERENCE and exact safe claims_boundary"
                if manifest.get("source_type") == "SYNTHETIC_REFERENCE"
                and _mapping(manifest.get("claims_boundary")) == SAFE_CLAIMS_BOUNDARY
                else "synthetic source or claims_boundary is unsafe"
            ),
        )
    )

    hashes_passed, hashes_detail = _validate_artifact_hashes(pack_dir, manifest)
    checks.append(_check("artifact_and_pack_hashes", hashes_passed, hashes_detail))

    cases, cases_error = _load_jsonl(pack_dir / "cases.jsonl")
    if cases_error is None:
        cases_passed, cases_detail = _validate_case_records(cases, manifest)
    else:
        cases_passed, cases_detail = False, cases_error
    checks.append(_check("minimum_30_unique_cases", cases_passed, cases_detail))

    policy_value, policy_error = _load_json(pack_dir / "policy.json")
    policy = _mapping(policy_value)
    if policy_error is None:
        policy_passed, policy_detail = _validate_policy(policy)
    else:
        policy_passed, policy_detail = False, policy_error
    checks.append(_check("versioned_effective_synthetic_policy", policy_passed, policy_detail))

    gold, gold_error = _load_jsonl(pack_dir / "gold.jsonl")
    if gold_error is None:
        gold_passed, gold_detail = _validate_gold(gold, cases, policy)
    else:
        gold_passed, gold_detail = False, gold_error
    checks.append(_check("gold_complete_and_case_linked", gold_passed, gold_detail))

    demos_value, demos_error = _load_json(pack_dir / "demo_scenarios.json")
    demos = _mapping(demos_value)
    if demos_error is None:
        demos_passed, demos_detail = _validate_demo_scenarios(
            demos, manifest, set(_case_ids(cases)), gold
        )
    else:
        demos_passed, demos_detail = False, demos_error
    checks.append(_check("five_demo_safety_boundaries", demos_passed, demos_detail))

    model_value, model_error = _load_json(pack_dir / "model_manifest.json")
    model = _mapping(model_value)
    if model_error is None:
        model_passed, model_detail = _validate_model_manifest(model, manifest)
    else:
        model_passed, model_detail = False, model_error
    checks.append(_check("report_based_binary_model_manifest", model_passed, model_detail))

    runtime_status, runtime_blockers = _runtime_vision_status(model)
    offline_status = OfflinePackStatus.READY
    if not all(check.passed for check in checks):
        offline_status = OfflinePackStatus.BLOCKED
    verdict = (
        ScenarioPocVerdict.READY
        if offline_status is OfflinePackStatus.READY
        else ScenarioPocVerdict.BLOCKED
    )
    return ScenarioPocAssessment(
        verdict=verdict,
        offline_status=offline_status,
        runtime_status=runtime_status,
        offline_checks=tuple(checks),
        runtime_blockers=runtime_blockers,
        pack_dir=_display_path(pack_dir),
    )


def build_acceptance_report(
    assessment: ScenarioPocAssessment,
    pack_dir: Path,
    *,
    evaluated_at: datetime | None = None,
) -> dict[str, object]:
    """Build a sealed report without recording endpoint URLs, tokens, or host paths."""

    manifest_value, _ = _load_json(pack_dir / "manifest.json")
    manifest = _mapping(manifest_value)
    cases, _ = _load_jsonl(pack_dir / "cases.jsonl")
    demos_value, _ = _load_json(pack_dir / "demo_scenarios.json")
    demos = _mapping(demos_value)
    model_value, _ = _load_json(pack_dir / "model_manifest.json")
    model = _mapping(model_value)
    candidate = _mapping(model.get("candidate"))
    timestamp = (evaluated_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    content: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "evaluated_at": timestamp,
        "verdict": assessment.verdict.value,
        "offline_status": assessment.offline_status.value,
        "runtime_status": assessment.runtime_status.value,
        "assessment": assessment.to_dict(),
        "evidence_summary": {
            "declared_record_count": _integer(manifest.get("record_count")),
            "observed_record_count": len(cases),
            "observed_demo_scenario_count": len(_sequence(demos.get("scenarios"))),
            "pack_hash": _text(manifest.get("pack_hash")),
            "artifact_hashes": dict(_mapping(manifest.get("artifact_hashes"))),
            "runtime_artifact_discovery": {
                "runtime_integration_status": _text(model.get("runtime_integration_status"))
                or "NOT_AVAILABLE",
                "checkpoint_package_status": _text(model.get("checkpoint_package_status"))
                or (
                    "AVAILABLE"
                    if candidate.get("artifact_included_in_pack") is True
                    else "NOT_AVAILABLE"
                ),
                "serving_endpoint_status": (
                    "AVAILABLE"
                    if candidate.get("serving_endpoint_included_in_pack") is True
                    else "NOT_AVAILABLE"
                ),
            },
        },
    }
    content["report_hash"] = _canonical_hash(content)
    return content


def validate_acceptance_report(report: Mapping[str, object]) -> tuple[bool, tuple[str, ...]]:
    """Validate report integrity and the minimum evidence envelope."""

    failures: list[str] = []
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        failures.append("REPORT_SCHEMA_VERSION_INVALID")
    timestamp = _text(report.get("evaluated_at"))
    try:
        if timestamp is None:
            raise ValueError
        datetime.fromisoformat(timestamp)
    except ValueError:
        failures.append("EVALUATED_AT_INVALID")
    expected_hash = _text(report.get("report_hash"))
    content = dict(report)
    content.pop("report_hash", None)
    if expected_hash != _canonical_hash(content):
        failures.append("REPORT_HASH_MISMATCH")
    assessment = _mapping(report.get("assessment"))
    offline = _mapping(assessment.get("offline_scenario_pack"))
    runtime = _mapping(assessment.get("runtime_vision_integration"))
    if assessment.get("verdict") not in {item.value for item in ScenarioPocVerdict}:
        failures.append("VERDICT_INVALID")
    if report.get("verdict") != assessment.get("verdict"):
        failures.append("TOP_LEVEL_VERDICT_MISMATCH")
    if offline.get("status") not in {item.value for item in OfflinePackStatus}:
        failures.append("OFFLINE_STATUS_INVALID")
    if report.get("offline_status") != offline.get("status"):
        failures.append("TOP_LEVEL_OFFLINE_STATUS_MISMATCH")
    if runtime.get("status") not in {item.value for item in RuntimeVisionStatus}:
        failures.append("RUNTIME_STATUS_INVALID")
    if report.get("runtime_status") != runtime.get("status"):
        failures.append("TOP_LEVEL_RUNTIME_STATUS_MISMATCH")
    evidence = _mapping(report.get("evidence_summary"))
    if _integer(evidence.get("observed_record_count")) is None:
        failures.append("RECORD_COUNT_EVIDENCE_MISSING")
    if _integer(evidence.get("observed_demo_scenario_count")) is None:
        failures.append("DEMO_COUNT_EVIDENCE_MISSING")
    if not _mapping(evidence.get("runtime_artifact_discovery")):
        failures.append("RUNTIME_ARTIFACT_DISCOVERY_MISSING")
    if assessment.get("verdict") == ScenarioPocVerdict.READY.value:
        if (_integer(evidence.get("observed_record_count")) or 0) < MINIMUM_CASE_COUNT:
            failures.append("READY_REPORT_CASE_COUNT_INVALID")
        if _integer(evidence.get("observed_demo_scenario_count")) != 5:
            failures.append("READY_REPORT_DEMO_COUNT_INVALID")
        if len(_text(evidence.get("pack_hash")) or "") != 64:
            failures.append("READY_REPORT_PACK_HASH_INVALID")
        if set(_mapping(evidence.get("artifact_hashes"))) != set(REQUIRED_ARTIFACTS):
            failures.append("READY_REPORT_ARTIFACT_EVIDENCE_INVALID")
    return not failures, tuple(failures)


def _write_report(path: Path, report: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the synthetic hard-plastic scenario PoC acceptance pack."
    )
    parser.add_argument("--pack-dir", type=Path, default=DEFAULT_PACK_DIR)
    parser.add_argument(
        "--report",
        type=Path,
        help=f"Report path (default: PACK_DIR/{DEFAULT_REPORT_NAME}).",
    )
    parser.add_argument(
        "--verify-report",
        type=Path,
        help="Validate a previously generated report instead of reassessing the pack.",
    )
    parser.add_argument(
        "--require-runtime-vision",
        action="store_true",
        help="Also fail when the real Vision endpoint/checkpoint package is unavailable.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.verify_report is not None:
        report_value, error = _load_json(args.verify_report)
        if error is not None:
            print(json.dumps({"valid": False, "failures": [error]}, indent=2))
            return 1
        valid, failures = validate_acceptance_report(_mapping(report_value))
        print(json.dumps({"valid": valid, "failures": list(failures)}, indent=2))
        return 0 if valid else 1
    assessment = assess_scenario_poc(args.pack_dir)
    report = build_acceptance_report(assessment, args.pack_dir)
    report_path = args.report or (args.pack_dir / DEFAULT_REPORT_NAME)
    _write_report(report_path, report)
    valid, report_failures = validate_acceptance_report(report)
    output = dict(report)
    output["report_validation"] = {"valid": valid, "failures": list(report_failures)}
    output["report_output"] = _display_path(report_path)
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    if not valid:
        return 1
    if not assessment.passed:
        return 1
    if args.require_runtime_vision and assessment.runtime_status is not RuntimeVisionStatus.READY:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
