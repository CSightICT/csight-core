"""Contract tests shared by the deterministic LLM and Vision adapters."""

import pytest

from app.adapters.llm import MockLLMProvider
from app.adapters.vision import MockVisionProvider
from app.platform.analysis import (
    AnalysisProviderError,
    LLMAnalysisRequest,
    LLMCaseExtraction,
    MockProviderMode,
    ProviderFailureError,
    ProviderSchemaError,
    ProviderTimeoutError,
    VisionAnalysisRequest,
    VisionAnalysisResult,
)
from app.ports.llm import LLMProvider
from app.ports.vision import VisionProvider

pytestmark = pytest.mark.contract


def test_mock_llm_implements_port_and_returns_common_schema() -> None:
    provider = MockLLMProvider(model_name="contract-llm", model_version="2026.08")

    assert isinstance(provider, LLMProvider)
    result = provider.extract_case(
        LLMAnalysisRequest(case_id="CASE-1", customer_message="bottom leakage, exchange")
    )
    assert isinstance(result, LLMCaseExtraction)
    assert result.schema_version == "1.0"
    assert result.model.name == "contract-llm"
    assert result.model.version == "2026.08"


def test_mock_vision_implements_port_and_returns_common_schema() -> None:
    provider = MockVisionProvider(model_name="contract-vision", model_version="2026.08")

    assert isinstance(provider, VisionProvider)
    result = provider.analyze_image(
        VisionAnalysisRequest(
            case_id="CASE-1",
            image_reference="evidence/CASE-1/image.jpg",
        )
    )
    assert isinstance(result, VisionAnalysisResult)
    assert result.schema_version == "1.0"
    assert result.model.name == "contract-vision"
    assert result.model.version == "2026.08"
    assert all(
        0.0 <= coordinate <= 1.0
        for finding in result.detections
        for coordinate in (
            finding.geometry.x1,
            finding.geometry.y1,
            finding.geometry.x2,
            finding.geometry.y2,
        )
    )


@pytest.mark.parametrize(
    ("mode", "expected_error"),
    [
        (MockProviderMode.TIMEOUT, ProviderTimeoutError),
        (MockProviderMode.FAILURE, ProviderFailureError),
        (MockProviderMode.SCHEMA_ERROR, ProviderSchemaError),
    ],
)
def test_llm_failure_modes_are_normalized(
    mode: MockProviderMode,
    expected_error: type[AnalysisProviderError],
) -> None:
    def invoke() -> LLMCaseExtraction:
        return MockLLMProvider(mode=mode).extract_case(
            LLMAnalysisRequest(case_id="CASE-1", customer_message="leakage")
        )

    with pytest.raises(expected_error) as error:
        invoke()

    assert error.value.provider == "mock"
    assert error.value.code.startswith("PROVIDER_")


@pytest.mark.parametrize(
    ("mode", "expected_error"),
    [
        (MockProviderMode.TIMEOUT, ProviderTimeoutError),
        (MockProviderMode.FAILURE, ProviderFailureError),
        (MockProviderMode.SCHEMA_ERROR, ProviderSchemaError),
    ],
)
def test_vision_failure_modes_are_normalized(
    mode: MockProviderMode,
    expected_error: type[AnalysisProviderError],
) -> None:
    def invoke() -> VisionAnalysisResult:
        return MockVisionProvider(mode=mode).analyze_image(
            VisionAnalysisRequest(case_id="CASE-1", image_reference="evidence/image.jpg")
        )

    with pytest.raises(expected_error) as error:
        invoke()

    assert error.value.provider == "mock"
    assert error.value.code.startswith(("PROVIDER_", "VISION_PROVIDER_"))
