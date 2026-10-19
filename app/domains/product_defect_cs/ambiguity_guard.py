"""Dev-only deterministic validation for product-defect ambiguity labels.

This module does not make a policy decision and is not wired into the runtime
composition root. It exists only to test whether narrow, reviewable validation
can close the synthetic Dev ambiguity gate before considering QLoRA.
"""

import hashlib
import json

from app.platform.analysis.enums import ExtractionIssueType
from app.platform.analysis.llm_v2 import LLMTextExtractionResultV2, TextAmbiguity

DEV_AMBIGUITY_GUARD_VERSION = "product_defect_ambiguity_guard/1.0.0-dev"
_RULE_CONTRACT = (
    "location-unclear-requires-functional-failure",
    "description-vague-requires-no-concrete-issue",
    "contradiction-requires-rejected-action-and-positive-extracted-request",
    "vague-no-issue-implies-defect-type-unclear",
    "embedded-instruction-vague-does-not-imply-defect-type-unclear",
)
DEV_AMBIGUITY_GUARD_CONTENT_HASH = hashlib.sha256(
    json.dumps(_RULE_CONTRACT, separators=(",", ":")).encode()
).hexdigest()

_ACTION_REJECTION_MARKERS = (
    "싫",
    "원하지 않",
    "필요 없",
    "하지 말",
    "말고",
    "아니지만",
)
_EMBEDDED_INSTRUCTION_MARKERS = (
    "무시하고",
    "출력해",
    "시스템 지시",
    "관리자 지시",
    "assistant",
)


def apply_dev_ambiguity_guard(
    result: LLMTextExtractionResultV2,
    *,
    customer_message: str,
) -> LLMTextExtractionResultV2:
    """Return a copy with only bounded ambiguity-label corrections.

    Claims, issue types, requested actions, quotes, summary, and every other
    model field remain unchanged. The caller must bind the guard version and
    content hash into its diagnosis evidence.
    """

    ambiguities = set(result.text_ambiguities)
    if ExtractionIssueType.FUNCTIONAL_FAILURE not in result.issue_types:
        ambiguities.discard(TextAmbiguity.DEFECT_LOCATION_UNCLEAR)
    if result.issue_types:
        ambiguities.discard(TextAmbiguity.DESCRIPTION_TOO_VAGUE)
    if not (
        result.requested_actions
        and any(marker in customer_message for marker in _ACTION_REJECTION_MARKERS)
    ):
        ambiguities.discard(TextAmbiguity.CONTRADICTORY_STATEMENTS)
    embedded_instruction = any(
        marker in customer_message.casefold() for marker in _EMBEDDED_INSTRUCTION_MARKERS
    )
    if (
        TextAmbiguity.DESCRIPTION_TOO_VAGUE in ambiguities
        and not result.issue_types
        and not embedded_instruction
    ):
        ambiguities.add(TextAmbiguity.DEFECT_TYPE_UNCLEAR)
    ordered = tuple(label for label in TextAmbiguity if label in ambiguities)
    return result.model_copy(update={"text_ambiguities": ordered})


__all__ = [
    "DEV_AMBIGUITY_GUARD_CONTENT_HASH",
    "DEV_AMBIGUITY_GUARD_VERSION",
    "apply_dev_ambiguity_guard",
]
