#!/usr/bin/env python3
"""Fail-closed validator for the synthetic hard-plastic scenario PoC pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PACK_DIR = Path(__file__).resolve().parent
REQUIRED_HASHED_ARTIFACTS = (
    "cases.jsonl",
    "policy.json",
    "gold.jsonl",
    "demo_scenarios.json",
    "model_manifest.json",
)
EXPECTED_DEMO_BOUNDARIES = {
    "COMPLETE_VISIBLE_BREAKAGE_DRY_RUN_VALIDATED",
    "REFUND_INPUT_MISSING_NO_ATTEMPT",
    "FUNCTIONAL_FAILURE_STILL_UNCONFIRMED_REQUEST_EVIDENCE",
    "SAFETY_REVIEWER_BLOCKED_ADMIN_RESOLVE",
    "VISION_TIMEOUT_PARTIAL_SUCCESS_NO_ACTION",
}
FORBIDDEN_OUTCOMES = {
    "AUTOMATED_DECISION",
    "LIVE_EXTERNAL_ACTION",
    "VISION_CONFIRMED_DEFECT_TYPE",
    "VISION_CONFIRMED_DEFECT_LOCATION",
    "NORMAL_FROM_LOW_SCORE",
    "PARAMETER_INFERENCE",
}
DECISION_ACTION = {
    "APPROVE_REFUND": "REFUND",
    "APPROVE_EXCHANGE": "EXCHANGE",
    "APPROVE_REPAIR": "REPAIR",
}
ACTION_FIELDS = {
    "REFUND": {"amount", "currency"},
    "EXCHANGE": {"quantity", "shipping_address_ref"},
    "REPAIR": {"quantity"},
}
REFERENCE_REQUIREMENTS = {
    "REFUND": {"order_ref"},
    "EXCHANGE": {"order_ref", "product_ref"},
    "REPAIR": {"order_ref", "product_ref"},
}
KOREAN_TEXT = re.compile(r"[가-힣]")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
AMOUNT = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
SAFE_CLAIMS_BOUNDARY = {
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


class PackValidationError(ValueError):
    """The pack violates a structural, referential, or safety invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PackValidationError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackValidationError(f"cannot load {path.name}: {exc}") from exc
    _require(isinstance(value, dict), f"{path.name} must contain one JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PackValidationError(f"cannot load {path.name}: {exc}") from exc
    records: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        _require(bool(line.strip()), f"{path.name}:{number} must not be blank")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PackValidationError(f"{path.name}:{number}: {exc}") from exc
        _require(isinstance(value, dict), f"{path.name}:{number} must be an object")
        records.append(value)
    return records


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pack_hash(artifact_hashes: dict[str, str]) -> str:
    encoded = json.dumps(
        artifact_hashes,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string(value: Any, context: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{context} must be non-empty text")
    return value


def _validate_manifest(
    pack_dir: Path,
    manifest: dict[str, Any],
    cases: list[dict[str, Any]],
    demos: dict[str, Any],
) -> None:
    _require(manifest.get("schema_version") == "scenario_poc_pack/1.0.0", "bad schema")
    _require(manifest.get("source_type") == "SYNTHETIC_REFERENCE", "pack must be synthetic")
    _require(manifest.get("language") == "ko-KR", "pack language must be ko-KR")
    _require(manifest.get("record_count") == len(cases), "record_count mismatch")
    _require(len(cases) >= 30, "at least 30 cases are required")

    actual_splits = dict(sorted(Counter(record.get("split") for record in cases).items()))
    _require(manifest.get("split_counts") == actual_splits, "split_counts mismatch")
    demo_ids = [item.get("scenario_id") for item in demos.get("scenarios", [])]
    _require(manifest.get("demo_scenario_ids") == demo_ids, "demo_scenario_ids mismatch")

    scope = manifest.get("product_scope")
    _require(isinstance(scope, dict), "product_scope must be an object")
    _require(scope.get("material") == "plastic_hard", "material must be plastic_hard")
    _require(scope.get("product_type") == "MANUAL_PUMP_DISPENSER", "wrong product type")
    _require(scope.get("product_id") == "HDP-100", "wrong product id")
    _require(scope.get("product_is_synthetic") is True, "product must be explicitly synthetic")
    _require(scope.get("product_specific_model_performance") == "NOT_EVALUATED", "scope claim")
    _require(
        manifest.get("claims_boundary") == SAFE_CLAIMS_BOUNDARY,
        "manifest claims_boundary must retain the exact synthetic safety boundary",
    )

    reports = manifest.get("source_reports")
    _require(isinstance(reports, list) and len(reports) == 2, "two source reports required")
    for report in reports:
        _require(report.get("metrics_reproduced_by_csight") is False, "report must be supplied")
        _require(
            isinstance(report.get("sha256"), str) and len(report["sha256"]) == 64,
            "source report hash missing",
        )

    hashes = manifest.get("artifact_hashes")
    _require(isinstance(hashes, dict), "artifact_hashes must be an object")
    _require(set(hashes) == set(REQUIRED_HASHED_ARTIFACTS), "artifact hash file set mismatch")
    for filename in REQUIRED_HASHED_ARTIFACTS:
        _require(hashes[filename] == _sha256(pack_dir / filename), f"hash mismatch: {filename}")
    _require(manifest.get("pack_hash") == _pack_hash(hashes), "pack_hash mismatch")


def _validate_model(model: dict[str, Any]) -> float:
    _require(model.get("source_type") == "SUPPLIED_OFFLINE_REPORT", "model source boundary")
    _require(model.get("task") == "BINARY_ANY_DEFECT_CLASSIFICATION", "model must be binary")
    _require(model.get("product_domain_status") == "NOT_EVALUATED", "product domain claim")
    _require(model.get("report_metrics_reproduced_by_csight") is False, "metrics claim")
    _require(
        model.get("qualification_status") == "SUPPLIED_OFFLINE_REPORT_WITH_LIMITATIONS",
        "qualification claim",
    )
    candidate = model.get("candidate", {})
    _require(candidate.get("artifact_included_in_pack") is False, "checkpoint is not included")
    _require(candidate.get("serving_endpoint_included_in_pack") is False, "endpoint is absent")

    boundary = model.get("decision_boundary", {})
    threshold = boundary.get("threshold")
    _require(isinstance(threshold, (float, int)), "threshold must be numeric")
    _require(float(threshold) == 0.8984375, "supplied threshold changed")
    _require(boundary.get("below_threshold") == "NOT_NORMAL", "low score cannot mean normal")
    _require(boundary.get("advisory_only") is True, "Vision must remain advisory")
    _require(boundary.get("automatic_decision_allowed") is False, "automatic decision forbidden")
    _require(boundary.get("human_review_required") is True, "human review is required")

    capabilities = model.get("capabilities", {})
    for name in (
        "defect_type",
        "defect_location",
        "bounding_box",
        "segmentation_mask",
        "functional_operation_confirmation_from_still_image",
    ):
        _require(capabilities.get(name) is False, f"unsupported model capability claimed: {name}")
    return float(threshold)


def _validate_policy(policy: dict[str, Any]) -> set[str]:
    _require(policy.get("schema_version") == "synthetic_policy_bundle/1.0.0", "policy schema")
    _require(policy.get("source_type") == "SYNTHETIC_REFERENCE", "policy must be synthetic")
    document = policy.get("document", {})
    _require(document.get("fictional") is True, "policy document must be fictional")
    _require(document.get("legal_or_commercial_effect") is False, "policy effect claim")
    version = document.get("version")
    _require(isinstance(version, str) and SEMVER.fullmatch(version) is not None, "policy version")
    effective_from = document.get("effective_from")
    _require(isinstance(effective_from, str), "policy effective date missing")
    try:
        date.fromisoformat(effective_from)
    except ValueError as exc:
        raise PackValidationError("policy effective date is invalid") from exc

    clauses = policy.get("clauses")
    _require(isinstance(clauses, list) and len(clauses) >= 8, "policy clauses missing")
    clause_ids = {_string(item.get("clause_id"), "clause_id") for item in clauses}
    _require(len(clause_ids) == len(clauses), "duplicate clause id")
    for item in clauses:
        _require(item.get("version") == version, "clause version mismatch")
        _require(item.get("effective_from") == effective_from, "clause effective date mismatch")
        _string(item.get("text"), "clause text")

    rules = policy.get("rules")
    _require(isinstance(rules, list) and len(rules) >= 5, "policy rules missing")
    rule_ids = {_string(item.get("rule_id"), "rule_id") for item in rules}
    _require(len(rule_ids) == len(rules), "duplicate rule id")
    for rule in rules:
        _require(rule.get("version") == version, "rule version mismatch")
        sources = rule.get("source_clause_ids")
        _require(isinstance(sources, list) and bool(sources), "rule sources missing")
        _require(set(sources) <= clause_ids, "rule references unknown clause")

    guardrails = policy.get("global_guardrails", {})
    _require(guardrails.get("final_decision_owner") == "AUTHENTICATED_HUMAN", "decision owner")
    for name in (
        "automatic_approval_allowed",
        "parameter_inference_allowed",
        "live_external_action_allowed",
        "side_effects_performed",
        "actual_performance_or_roi_claim_allowed",
    ):
        _require(guardrails.get(name) is False, f"guardrail must be false: {name}")
    _require(guardrails.get("external_action_mode") == "DRY_RUN", "only DRY_RUN is allowed")
    return clause_ids


def _action_input_is_complete(case_input: dict[str, Any], action_type: str) -> bool:
    for reference in REFERENCE_REQUIREMENTS[action_type]:
        value = case_input.get(reference)
        if not isinstance(value, str) or not value.strip():
            return False

    attributes = case_input.get("attributes")
    if not isinstance(attributes, dict):
        return False
    external = attributes.get("external_action_input")
    if not isinstance(external, dict) or set(external) != ACTION_FIELDS[action_type]:
        return False
    if action_type == "REFUND":
        amount = external.get("amount")
        currency = external.get("currency")
        if not isinstance(amount, str) or AMOUNT.fullmatch(amount) is None:
            return False
        try:
            if Decimal(amount) <= 0:
                return False
        except InvalidOperation:
            return False
        return isinstance(currency, str) and CURRENCY.fullmatch(currency) is not None
    quantity = external.get("quantity")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 1000:
        return False
    if action_type == "EXCHANGE":
        address = external.get("shipping_address_ref")
        return isinstance(address, str) and bool(address.strip())
    return True


def _validate_case_gold(
    case: dict[str, Any],
    gold: dict[str, Any],
    *,
    threshold: float,
    clause_ids: set[str],
) -> None:
    record_id = _string(case.get("record_id"), "case record_id")
    _require(gold.get("record_id") == record_id, f"Gold id mismatch: {record_id}")
    case_input = case.get("case_input")
    _require(isinstance(case_input, dict), f"{record_id}: case_input missing")
    message = _string(case_input.get("customer_message"), f"{record_id}: message")
    _require(KOREAN_TEXT.search(message) is not None, f"{record_id}: Korean text missing")

    vision_fixture = case_input.get("vision_fixture")
    _require(isinstance(vision_fixture, dict), f"{record_id}: vision fixture missing")
    score_band = vision_fixture.get("score_band")
    score = vision_fixture.get("score")
    if score_band == "HIGH_CANDIDATE":
        _require(
            isinstance(score, (int, float)) and float(score) >= threshold,
            f"{record_id}: band",
        )
    elif score_band == "BELOW_THRESHOLD":
        _require(isinstance(score, (int, float)) and float(score) < threshold, f"{record_id}: band")
    elif score_band == "UNAVAILABLE":
        _require(score is None, f"{record_id}: unavailable score must be null")
    else:
        raise PackValidationError(f"{record_id}: unknown score band")

    expected = gold.get("expected")
    _require(isinstance(expected, dict), f"{record_id}: expected missing")
    vision = expected.get("vision")
    _require(isinstance(vision, dict), f"{record_id}: Vision Gold missing")
    _require(vision.get("score_band") == score_band, f"{record_id}: score band mismatch")
    _require(vision.get("type_or_location_claim_allowed") is False, f"{record_id}: type claim")
    if score_band == "BELOW_THRESHOLD":
        _require(vision.get("business_interpretation") == "NOT_NORMAL", f"{record_id}: normal")

    issue_types = expected.get("issue_types")
    _require(isinstance(issue_types, list), f"{record_id}: issue types missing")
    basis = _string(expected.get("issue_evidence_basis"), f"{record_id}: evidence basis")
    if "FUNCTIONAL_FAILURE" in issue_types:
        _require(
            "NOT_CONFIRMED_BY_STILL_IMAGE" in basis,
            f"{record_id}: functional failure must retain still-image boundary",
        )

    sources = expected.get("policy_clause_ids")
    _require(isinstance(sources, list) and bool(sources), f"{record_id}: policy refs missing")
    _require(set(sources) <= clause_ids, f"{record_id}: unknown policy ref")
    effects = expected.get("policy_effects")
    _require(isinstance(effects, list), f"{record_id}: effects missing")
    _require("REQUIRE_HUMAN_REVIEW" in effects, f"{record_id}: human review effect missing")
    _require("PROHIBIT_AUTOMATION" in effects, f"{record_id}: automation guard missing")

    review = expected.get("review")
    _require(isinstance(review, dict), f"{record_id}: review Gold missing")
    _require(review.get("decision_owner") == "AUTHENTICATED_HUMAN", f"{record_id}: owner")
    if case_input.get("declared_safety_risk") is True:
        _require(review.get("required_role") == "ADMIN", f"{record_id}: safety role")
        _require(review.get("reviewer_claim_allowed") is False, f"{record_id}: safety claim")

    forbidden = gold.get("forbidden_outcomes")
    _require(isinstance(forbidden, list), f"{record_id}: forbidden outputs missing")
    _require(set(forbidden) >= FORBIDDEN_OUTCOMES, f"{record_id}: safety forbid list incomplete")

    resolution = expected.get("resolution")
    _require(isinstance(resolution, dict), f"{record_id}: resolution Gold missing")
    _require(resolution.get("side_effects_performed") is False, f"{record_id}: side effect")
    counts = tuple(
        resolution.get(name) for name in ("intent_count", "attempt_count", "result_count")
    )
    status = resolution.get("status")
    decision = review.get("human_decision")
    action_type = resolution.get("action_type")
    if status == "ACTION_DRY_RUN_VALIDATED":
        _require(counts == (1, 1, 1), f"{record_id}: validated counts")
        _require(DECISION_ACTION.get(decision) == action_type, f"{record_id}: action mapping")
        _require(_action_input_is_complete(case_input, action_type), f"{record_id}: explicit input")
    elif status == "ACTION_NEEDS_INPUT":
        _require(counts == (0, 0, 0), f"{record_id}: needs-input counts")
        _require(DECISION_ACTION.get(decision) == action_type, f"{record_id}: action mapping")
        _require(
            not _action_input_is_complete(case_input, action_type),
            f"{record_id}: should hold",
        )
    else:
        _require(counts == (0, 0, 0), f"{record_id}: non-action counts")
        if status == "NOT_CREATED":
            _require(decision is None, f"{record_id}: unexpected decision")
        if status == "ACTION_NOT_REQUIRED":
            _require(
                decision in {"REJECT_REQUEST", "NO_ACTION"},
                f"{record_id}: no-action decision",
            )
        if status == "MANUAL_FOLLOW_UP_REQUIRED":
            _require(decision == "PROVIDE_INFORMATION", f"{record_id}: follow-up decision")


def _validate_demos(
    demos: dict[str, Any],
    cases_by_id: dict[str, dict[str, Any]],
    gold_by_id: dict[str, dict[str, Any]],
) -> None:
    scenarios = demos.get("scenarios")
    _require(demos.get("source_type") == "SYNTHETIC_REFERENCE", "demos must be synthetic")
    _require(isinstance(scenarios, list) and len(scenarios) == 5, "exactly five demos required")
    _require(demos.get("scenario_count") == 5, "scenario_count must be five")
    ids = [item.get("scenario_id") for item in scenarios]
    _require(len(set(ids)) == 5, "duplicate demo id")
    boundaries = {item.get("boundary") for item in scenarios}
    _require(boundaries == EXPECTED_DEMO_BOUNDARIES, "demo boundary set mismatch")
    for item in scenarios:
        scenario_id = item.get("scenario_id")
        record_id = item.get("case_record_id")
        _require(scenario_id == record_id, "demo and case id must be identical")
        _require(record_id in cases_by_id and record_id in gold_by_id, "demo reference missing")


def validate_pack(pack_dir: Path = PACK_DIR) -> dict[str, Any]:
    """Validate the complete pack and return a small non-performance summary."""

    manifest = _read_json(pack_dir / "manifest.json")
    model = _read_json(pack_dir / "model_manifest.json")
    policy = _read_json(pack_dir / "policy.json")
    demos = _read_json(pack_dir / "demo_scenarios.json")
    cases = _read_jsonl(pack_dir / "cases.jsonl")
    gold = _read_jsonl(pack_dir / "gold.jsonl")

    case_ids = [_string(item.get("record_id"), "case record_id") for item in cases]
    gold_ids = [_string(item.get("record_id"), "Gold record_id") for item in gold]
    _require(len(case_ids) == len(set(case_ids)), "duplicate case record_id")
    _require(len(gold_ids) == len(set(gold_ids)), "duplicate Gold record_id")
    _require(set(case_ids) == set(gold_ids), "Case and Gold IDs must match one-to-one")
    messages = [item["case_input"]["customer_message"] for item in cases]
    _require(len(messages) == len(set(messages)), "customer messages must be unique")

    threshold = _validate_model(model)
    clause_ids = _validate_policy(policy)
    gold_by_id = {item["record_id"]: item for item in gold}
    cases_by_id = {item["record_id"]: item for item in cases}
    for record_id, case in cases_by_id.items():
        _validate_case_gold(
            case,
            gold_by_id[record_id],
            threshold=threshold,
            clause_ids=clause_ids,
        )
    _validate_demos(demos, cases_by_id, gold_by_id)
    _validate_manifest(pack_dir, manifest, cases, demos)

    functional_count = sum("FUNCTIONAL_FAILURE" in item["expected"]["issue_types"] for item in gold)
    return {
        "verdict": "PASS_SYNTHETIC_SCENARIO_PACK",
        "record_count": len(cases),
        "demo_scenario_count": len(demos["scenarios"]),
        "functional_still_image_boundary_count": functional_count,
        "source_type": manifest["source_type"],
        "product_domain_status": model["product_domain_status"],
        "actual_performance_or_roi_claimed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", type=Path, default=PACK_DIR)
    args = parser.parse_args()
    try:
        result = validate_pack(args.pack_dir.resolve())
    except PackValidationError as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
