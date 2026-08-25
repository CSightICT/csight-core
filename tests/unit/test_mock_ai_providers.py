"""Determinism tests for Sprint 0 AI provider fakes."""

import pytest

from app.adapters.llm import MockLLMProvider
from app.adapters.vision import MockVisionProvider
from app.platform.analysis import LLMAnalysisRequest, VisionAnalysisRequest

pytestmark = pytest.mark.unit


def test_mock_llm_output_is_deterministic() -> None:
    provider = MockLLMProvider()
    request = LLMAnalysisRequest(
        case_id="CASE-001",
        customer_message="용기 하단이 찌그러졌고 내용물이 샜습니다. 교환을 요청합니다.",
    )

    first = provider.extract_case(request)
    second = provider.extract_case(request)

    assert first == second
    assert first.model == provider.provider_metadata
    assert first.issue_type.value == "LEAKAGE"
    assert first.claimed_location.value == "BOTTOM"
    assert first.customer_request.value == "EXCHANGE"


def test_mock_vision_output_is_deterministic() -> None:
    provider = MockVisionProvider()
    request = VisionAnalysisRequest(
        case_id="CASE-001",
        image_reference="evidence/CASE-001/image-1.jpg",
    )

    first = provider.analyze_image(request)
    second = provider.analyze_image(request)

    assert first == second
    assert first.model == provider.provider_metadata
    assert first.image_reference == request.image_reference
    assert first.detections[0].label.value == "LEAKAGE"
