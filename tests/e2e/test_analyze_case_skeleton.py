"""Network-free end-to-end application skeleton coverage."""

import pytest

from app.adapters.llm import MockLLMProvider
from app.adapters.vision import MockVisionProvider
from app.application.analyze_case import AnalyzeCase, AnalyzeCaseCommand, AnalyzeCaseResult
from app.platform.analysis import ProviderTimeoutError

pytestmark = pytest.mark.e2e


def test_application_orchestrates_mock_providers_through_common_contracts() -> None:
    use_case = AnalyzeCase(MockLLMProvider(), MockVisionProvider())
    command = AnalyzeCaseCommand(
        case_id="CASE-2026-0001",
        analysis_run_id="AR-2026-0001",
        customer_message="용기 하단에서 누액이 발생했습니다. 교환을 요청합니다.",
        image_references=(
            "evidence/CASE-2026-0001/front.jpg",
            "evidence/CASE-2026-0001/bottom.jpg",
        ),
        prompt_version="extraction-v1",
    )

    result = use_case.execute(command)

    assert isinstance(result, AnalyzeCaseResult)
    assert result.case_id == command.case_id
    assert result.analysis_run_id == command.analysis_run_id
    assert result.versions.prompt_version == "extraction-v1"
    assert result.versions.llm_model == result.llm.model
    assert result.versions.vision_model == result.vision[0].model
    assert result.versions.policy_version is None
    assert result.llm.model.name == "csight-mock-llm"
    assert tuple(item.image_reference for item in result.vision) == command.image_references
    assert all(item.model.name == "csight-mock-vision" for item in result.vision)
    assert "final_decision" not in result.model_dump(mode="json")


def test_application_preserves_typed_provider_failure() -> None:
    use_case = AnalyzeCase(MockLLMProvider(mode="timeout"), MockVisionProvider())
    command = AnalyzeCaseCommand(
        case_id="CASE-1",
        analysis_run_id="AR-1",
        customer_message="leakage",
        image_references=("evidence/image.jpg",),
    )

    with pytest.raises(ProviderTimeoutError, match="PROVIDER_TIMEOUT"):
        use_case.execute(command)
