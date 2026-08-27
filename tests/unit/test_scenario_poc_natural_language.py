"""Natural-language coverage for the five hard-plastic demo cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.llm import MockLLMProvider
from app.domains.product_defect_cs import PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
from app.platform.analysis import (
    ExtractedActionV2,
    ExtractionIssueType,
    LLMTextExtractionRequestV2,
)

pytestmark = pytest.mark.unit

PACK = Path(__file__).resolve().parents[2] / "evaluation/scenario_poc_hard_plastic_v1"

EXPECTED = {
    "DEMO-01": ((ExtractionIssueType.BREAKAGE,), (ExtractedActionV2.EXCHANGE,)),
    "DEMO-02": ((ExtractionIssueType.BREAKAGE,), (ExtractedActionV2.REFUND,)),
    "DEMO-03": ((ExtractionIssueType.FUNCTIONAL_FAILURE,), ()),
    "DEMO-04": (
        (ExtractionIssueType.BREAKAGE, ExtractionIssueType.LEAKAGE),
        (ExtractedActionV2.EXCHANGE,),
    ),
    "DEMO-05": ((ExtractionIssueType.FUNCTIONAL_FAILURE,), (ExtractedActionV2.EXCHANGE,)),
}


def _demo_cases() -> list[dict[str, object]]:
    records = [
        json.loads(line)
        for line in (PACK / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [record for record in records if record.get("record_id") in EXPECTED]


def test_mock_orchestration_extracts_the_five_demo_messages_without_model_claims() -> None:
    """Mock supports today's wiring demo; this is not semantic model qualification."""

    records = _demo_cases()
    assert len(records) == 5
    provider = MockLLMProvider()

    for record in records:
        record_id = str(record["record_id"])
        case_input = record["case_input"]
        assert isinstance(case_input, dict)
        result = provider.extract_text_v2(
            LLMTextExtractionRequestV2(
                customer_message=str(case_input["customer_message"]),
                order_ref=str(case_input["order_ref"]),
                product_ref=str(case_input["product_ref"]),
            ),
            PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
        ).result
        expected_issues, expected_actions = EXPECTED[record_id]
        assert result.issue_types == expected_issues
        assert tuple(item.action for item in result.requested_actions) == expected_actions
