"""Pure promotion gate for distinguishing a Limited PoC from a simulation demo."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class PocVerdict(StrEnum):
    LIMITED_POC = "LIMITED_POC"
    SYNTHETIC_MOCK_SIMULATION_DEMO = "SYNTHETIC_MOCK_SIMULATION_DEMO"


@dataclass(frozen=True, slots=True)
class PocGateCheck:
    name: str
    passed: bool
    evidence_ref: str | None


@dataclass(frozen=True, slots=True)
class PocGateAssessment:
    verdict: PocVerdict
    checks: tuple[PocGateCheck, ...]

    @property
    def passed(self) -> bool:
        return self.verdict is PocVerdict.LIMITED_POC

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if not check.passed)

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "passed": self.passed,
            "failures": list(self.failures),
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "evidence_ref": check.evidence_ref,
                }
                for check in self.checks
            ],
        }


_SAFETY_ZERO_KEYS = (
    "cross_tenant",
    "unauthorized_decision",
    "duplicate_intent",
    "duplicate_result",
    "live_execution",
    "parameter_inference",
    "premature_closure",
    "decision_mutation",
)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _is_zero_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _evidence(section: Mapping[str, object]) -> str | None:
    return _text(section.get("evidence_ref"))


def _check(name: str, condition: bool, section: Mapping[str, object]) -> PocGateCheck:
    evidence_ref = _evidence(section)
    return PocGateCheck(
        name=name,
        passed=condition and evidence_ref is not None,
        evidence_ref=evidence_ref,
    )


def assess_poc_readiness(manifest: Mapping[str, object]) -> PocGateAssessment:
    """Evaluate every non-negotiable promotion condition without optimistic defaults."""

    scope = _mapping(manifest.get("customer_scope"))
    defect_types = _texts(scope.get("defect_types"))
    cases = _mapping(manifest.get("real_case_dataset"))
    policies = _mapping(manifest.get("real_policy_corpus"))
    privacy = _mapping(manifest.get("privacy_and_access"))
    vision = _mapping(manifest.get("vision_scope"))
    qwen = _mapping(manifest.get("qwen_re_evaluation"))
    distribution = _mapping(manifest.get("real_distribution_evaluation"))
    shadow = _mapping(manifest.get("shadow_mode"))
    safety = _mapping(manifest.get("safety_regression"))
    regression = _mapping(manifest.get("clean_environment_regression"))

    vision_qualified = (
        vision.get("status") == "QUALIFIED"
        and vision.get("manifest_complete") is True
        and vision.get("per_defect_evaluation_complete") is True
    )
    vision_excluded = (
        vision.get("status") == "EXPLICITLY_EXCLUDED"
        and vision.get("exclusion_scope_documented") is True
    )
    allowed_qwen_results = {"QUALIFIED", "QUALIFIED_WITH_LIMITATIONS"}

    checks = (
        _check(
            "customer_product_defect_scope",
            scope.get("customer_candidate_confirmed") is True
            and _text(scope.get("product_category")) is not None
            and 2 <= len(set(defect_types)) <= 3,
            scope,
        ),
        _check(
            "deidentified_real_cases_and_gold",
            cases.get("deidentified") is True
            and _integer(cases.get("case_count")) >= 30
            and _integer(cases.get("gold_reviewed_count")) >= 30,
            cases,
        ),
        _check(
            "versioned_effective_real_policy",
            policies.get("actual_company_policy") is True
            and policies.get("versioned") is True
            and policies.get("effective_dates_present") is True,
            policies,
        ),
        _check(
            "privacy_retention_exif_access_approval",
            all(
                privacy.get(key) is True
                for key in (
                    "retention_approved",
                    "deletion_approved",
                    "exif_removal_approved",
                    "access_control_approved",
                )
            ),
            privacy,
        ),
        _check(
            "vision_qualification_or_explicit_exclusion",
            vision_qualified or vision_excluded,
            vision,
        ),
        _check(
            "qwen_extraction_and_grounding_re_evaluated",
            qwen.get("extraction_status") in allowed_qwen_results
            and qwen.get("grounding_status") in allowed_qwen_results,
            qwen,
        ),
        _check(
            "real_policy_case_query_distribution_evaluated",
            all(distribution.get(key) is True for key in ("policy", "cases", "user_queries")),
            distribution,
        ),
        _check(
            "shadow_mode_human_comparison",
            shadow.get("completed") is True
            and shadow.get("human_gold_present") is True
            and _integer(shadow.get("comparable_decision_count")) > 0,
            shadow,
        ),
        _check(
            "zero_safety_violations",
            all(_is_zero_integer(safety.get(key)) for key in _SAFETY_ZERO_KEYS),
            safety,
        ),
        _check(
            "backend_frontend_clean_environment_regression",
            all(
                regression.get(key) == "PASS"
                for key in ("backend", "frontend", "clean_environment_demo")
            ),
            regression,
        ),
    )
    verdict = (
        PocVerdict.LIMITED_POC
        if all(check.passed for check in checks)
        else PocVerdict.SYNTHETIC_MOCK_SIMULATION_DEMO
    )
    return PocGateAssessment(verdict=verdict, checks=checks)


__all__ = ["PocGateAssessment", "PocGateCheck", "PocVerdict", "assess_poc_readiness"]
