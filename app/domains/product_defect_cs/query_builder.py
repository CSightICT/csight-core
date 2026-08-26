"""Immutable deterministic policy-query rules for product-defect cases."""

from app.platform.analysis.enums import ExtractionIssueType
from app.platform.analysis.llm_v2 import SystemMissingInformation, TextAmbiguity
from app.platform.policy_reference import ClauseType
from app.platform.query_builder import (
    PolicyQuery,
    PolicyQueryBuilderInput,
    PolicyQueryPlan,
    PolicyQueryPurpose,
    QueryFilterHints,
)

RULE_NAME = "deterministic_policy_query"
RULE_VERSION = "1.0.0"

_POLICY_BY_DEFECT = {
    ExtractionIssueType.LEAKAGE: "LEAKAGE_CONTAMINATION",
    ExtractionIssueType.CONTAMINATION: "LEAKAGE_CONTAMINATION",
    ExtractionIssueType.MISSING_COMPONENT: "MISSING_COMPONENT",
    ExtractionIssueType.WRONG_ITEM: "WRONG_ITEM",
    ExtractionIssueType.FUNCTIONAL_FAILURE: "FUNCTIONAL_FAILURE",
    ExtractionIssueType.PACKAGING_DAMAGE: "PACKAGING_DAMAGE",
    ExtractionIssueType.BREAKAGE: "SHIPPING_DAMAGE",
}


def build_deterministic_query_plan(value: PolicyQueryBuilderInput) -> PolicyQueryPlan:
    issues = tuple(dict.fromkeys(value.extraction.issue_types))
    actions = tuple(dict.fromkeys(item.action.value for item in value.extraction.requested_actions))
    issue_text = " ".join(issue.value for issue in issues) or "UNKNOWN"
    action_text = " ".join(actions) or "요청 미지정"
    days = value.trusted_metadata.days_since_purchase
    days_text = f"구매 후 {days}일" if days is not None else "구매 시점 미상"
    queries = [
        PolicyQuery(
            query_id="Q1",
            purpose=PolicyQueryPurpose.PRIMARY_POLICY,
            text=(
                f"{value.trusted_metadata.product_category} {issue_text} {days_text} "
                f"{action_text} 처리 기준"
            ),
        )
    ]
    clause_types = [ClauseType.RULE]
    missing = set(value.completeness.system_missing_information)
    visual_issue = bool(
        set(issues)
        & {
            ExtractionIssueType.BREAKAGE,
            ExtractionIssueType.CRACK,
            ExtractionIssueType.DENT,
            ExtractionIssueType.LEAKAGE,
            ExtractionIssueType.PACKAGING_DAMAGE,
            ExtractionIssueType.CONTAMINATION,
        }
    )
    if SystemMissingInformation.IMAGE_EVIDENCE in missing or visual_issue:
        queries.append(
            PolicyQuery(
                query_id=f"Q{len(queries) + 1}",
                purpose=PolicyQueryPurpose.EVIDENCE_REQUIREMENT,
                text=f"{issue_text} 확인에 필요한 이미지 증거 제출 조건",
            )
        )
        clause_types.append(ClauseType.EVIDENCE_REQUIREMENT)
    ambiguities = set(value.extraction.text_ambiguities)
    exception_needed = value.trusted_metadata.exception_context or bool(
        ambiguities
        & {
            TextAmbiguity.MULTIPLE_CONFLICTING_REQUESTS,
            TextAmbiguity.CONTRADICTORY_STATEMENTS,
        }
    )
    if len(queries) < 3 and exception_needed:
        queries.append(
            PolicyQuery(
                query_id=f"Q{len(queries) + 1}",
                purpose=PolicyQueryPurpose.EXCEPTION,
                text=f"{issue_text} 복수 요청 또는 예외 조건과 검토 절차",
            )
        )
        clause_types.append(ClauseType.EXCEPTION)
    elif len(queries) < 3 and value.trusted_metadata.escalation_context:
        queries.append(
            PolicyQuery(
                query_id=f"Q{len(queries) + 1}",
                purpose=PolicyQueryPurpose.ESCALATION,
                text=f"{issue_text} 추가 검토 및 상향 절차",
            )
        )
        clause_types.append(ClauseType.ESCALATION)
    policy_types = tuple(
        dict.fromkeys(
            policy for issue in issues if (policy := _POLICY_BY_DEFECT.get(issue)) is not None
        )
    )
    if len(queries) > 1 and "EVIDENCE_REQUIREMENT" not in policy_types:
        policy_types += ("EVIDENCE_REQUIREMENT",)
    return PolicyQueryPlan(
        queries=tuple(queries),
        filter_hints=QueryFilterHints(
            policy_types=policy_types,
            product_categories=(value.trusted_metadata.product_category,),
            defect_types=issues,
            clause_types=tuple(dict.fromkeys(clause_types)),
        ),
    )


__all__ = ["RULE_NAME", "RULE_VERSION", "build_deterministic_query_plan"]
