"""Unit validation for common AI analysis contracts."""

import pytest
from pydantic import ValidationError

from app.platform.analysis import (
    AnalysisVersionReferences,
    BoundingBox,
    CustomerRequest,
    DefectLocation,
    DefectType,
    LLMCaseExtraction,
    ProviderMetadata,
)

pytestmark = pytest.mark.unit


def test_bounding_box_accepts_ordered_normalized_coordinates() -> None:
    box = BoundingBox(x1=0.1, y1=0.2, x2=0.8, y2=0.9)

    assert box.model_dump(mode="json") == {
        "type": "BOUNDING_BOX",
        "coordinate_system": "NORMALIZED",
        "x1": 0.1,
        "y1": 0.2,
        "x2": 0.8,
        "y2": 0.9,
    }


@pytest.mark.parametrize(
    ("coordinates", "error_fragment"),
    [
        ({"x1": -0.1, "y1": 0.2, "x2": 0.8, "y2": 0.9}, "greater than or equal"),
        ({"x1": 0.8, "y1": 0.2, "x2": 0.7, "y2": 0.9}, "x2 must be greater"),
        ({"x1": 0.1, "y1": 0.9, "x2": 0.8, "y2": 0.9}, "y2 must be greater"),
    ],
)
def test_bounding_box_rejects_invalid_geometry(
    coordinates: dict[str, float],
    error_fragment: str,
) -> None:
    with pytest.raises(ValidationError, match=error_fragment):
        BoundingBox.model_validate(coordinates)


def test_llm_contract_rejects_unknown_fields_and_schema_versions() -> None:
    payload: dict[str, object] = {
        "schema_version": "2.0",
        "model": {"provider": "mock", "name": "model", "version": "1"},
        "issue_type": "LEAKAGE",
        "claimed_location": "BOTTOM",
        "customer_request": "EXCHANGE",
        "claims": [],
        "missing_information": [],
        "summary": "A structured summary.",
        "provider_raw_class_id": 17,
    }

    with pytest.raises(ValidationError) as error:
        LLMCaseExtraction.model_validate(payload)

    messages = str(error.value)
    assert "schema_version" in messages
    assert "provider_raw_class_id" in messages


def test_llm_contract_contains_observation_but_no_final_decision() -> None:
    result = LLMCaseExtraction(
        model=ProviderMetadata(provider="mock", name="llm", version="1"),
        issue_type=DefectType.LEAKAGE,
        claimed_location=DefectLocation.BOTTOM,
        customer_request=CustomerRequest.EXCHANGE,
        summary="Leakage reported at the bottom.",
    )

    assert "final_decision" not in LLMCaseExtraction.model_fields
    assert result.customer_request is CustomerRequest.EXCHANGE


def test_analysis_version_references_are_immutable_and_future_ready() -> None:
    model = ProviderMetadata(provider="mock", name="model", version="1")
    versions = AnalysisVersionReferences(
        llm_model=model,
        vision_model=model,
        prompt_version="prompt-v1",
        policy_version="policy-v2",
        threshold_version="threshold-v3",
        embedding_model_version="embedding-v4",
        retrieval_index_version="retrieval-v5",
    )

    assert versions.retrieval_index_version == "retrieval-v5"
    assert AnalysisVersionReferences.model_config.get("frozen") is True
