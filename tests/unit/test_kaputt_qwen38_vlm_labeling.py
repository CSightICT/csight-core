from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.label_kaputt_qwen38_vlm import (
    PRODUCT_SCHEMA_VERSION,
    SCHEMA_VERSION,
    ProductMetadataEnrichment,
    VLMEnrichment,
    existing_success_keys,
    select_reference_rows,
    select_rows,
)


@pytest.mark.unit
def test_select_rows_is_deterministic_balanced_and_material_scoped() -> None:
    rows = [
        {"capture_id": "p2", "item_material": "plastic_hard", "defect": True},
        {"capture_id": "n2", "item_material": "plastic_hard", "defect": False},
        {"capture_id": "p1", "item_material": "plastic_hard", "defect": True},
        {"capture_id": "n1", "item_material": "plastic_hard", "defect": False},
        {"capture_id": "x1", "item_material": "cardboard", "defect": True},
    ]

    selected = select_rows(rows, material="plastic_hard", limit=4, positive_fraction=0.5)

    assert [row["capture_id"] for row in selected] == ["n1", "n2", "p1", "p2"]
    assert sum(bool(row["defect"]) for row in selected) == 2


@pytest.mark.unit
def test_enrichment_schema_requires_generic_identity_and_bounded_confidence() -> None:
    valid = {
        "schema_version": SCHEMA_VERSION,
        "comparison_basis": "QUERY_PLUS_REFERENCE",
        "reference_count": 1,
        "identity_specificity": "GENERIC_ONLY",
        "product_category": "CONTAINER_OR_BOTTLE",
        "generic_product_name_ko": "경질 플라스틱 용기",
        "product_visual_summary_ko": "투명한 원통형 경질 플라스틱 용기가 트레이에 놓여 있다.",
        "image_usable": True,
        "image_usability_reason_ko": "상품 외형을 확인할 수 있다.",
        "visible_condition": "POSSIBLE_DEFECT",
        "visible_defect_types": ["deformation"],
        "visible_defect_summary_ko": "측면이 눌린 것처럼 보인다.",
        "visible_defect_location_ko": "용기 측면 중앙",
        "brand_or_personal_text_visible": False,
        "evidence_observations_ko": ["측면 윤곽이 안쪽으로 굽어 보인다."],
        "confidence": 0.72,
    }
    assert VLMEnrichment.model_validate(valid).identity_specificity == "GENERIC_ONLY"

    invalid = {**valid, "identity_specificity": "EXACT_PRODUCT", "confidence": 1.2}
    with pytest.raises(ValidationError):
        VLMEnrichment.model_validate(invalid)


@pytest.mark.unit
def test_failed_record_remains_retryable_but_success_is_skipped(tmp_path: Path) -> None:
    output = tmp_path / "records.jsonl"
    output.write_text(
        "\n".join(
            (
                '{"idempotency_key":"retry-me","status":"FAILED"}',
                '{"idempotency_key":"done","status":"SUCCEEDED"}',
            )
        )
        + "\n",
        encoding="utf-8",
    )

    assert existing_success_keys(output) == {"done"}


@pytest.mark.unit
def test_enrichment_schema_deduplicates_visible_defect_types() -> None:
    enrichment = VLMEnrichment.model_validate(
        {
            "schema_version": SCHEMA_VERSION,
            "comparison_basis": "QUERY_PLUS_REFERENCE",
            "reference_count": 1,
            "identity_specificity": "GENERIC_ONLY",
            "product_category": "UNCERTAIN",
            "generic_product_name_ko": "식별 불확실한 경질 플라스틱 제품",
            "product_visual_summary_ko": "경질 플라스틱 제품 일부가 포장 안에 보인다.",
            "image_usable": True,
            "image_usability_reason_ko": "제품 일부를 확인할 수 있다.",
            "visible_condition": "POSSIBLE_DEFECT",
            "visible_defect_types": ["deformation", "deformation"],
            "visible_defect_summary_ko": "제품 일부가 휘어 보인다.",
            "visible_defect_location_ko": "제품 중앙",
            "brand_or_personal_text_visible": False,
            "evidence_observations_ko": ["제품 윤곽이 고르지 않다."],
            "confidence": 0.61,
        }
    )

    assert enrichment.visible_defect_types == ["deformation"]


@pytest.mark.unit
def test_reference_selection_uses_same_item_and_stable_source_order() -> None:
    rows = [
        {"item_identifier": "same", "__index_level_0__": 12, "reference_crop": "b.jpg"},
        {"item_identifier": "other", "__index_level_0__": 1, "reference_crop": "x.jpg"},
        {"item_identifier": "same", "__index_level_0__": 11, "reference_crop": "a.jpg"},
    ]

    selected = select_reference_rows(rows, item_identifier="same", count=1)

    assert [row["reference_crop"] for row in selected] == ["a.jpg"]


@pytest.mark.unit
def test_product_metadata_schema_excludes_defect_and_business_fields() -> None:
    metadata = ProductMetadataEnrichment.model_validate(
        {
            "schema_version": PRODUCT_SCHEMA_VERSION,
            "observation_basis": "QUERY_PLUS_REFERENCE",
            "reference_count": 1,
            "identity_specificity": "GENERIC_ONLY",
            "product_category": "TOOL_OR_HARDWARE",
            "generic_product_name_ko": "목공용 접착제 용기",
            "product_form_ko": "노즐이 달린 압착식 플라스틱 병",
            "likely_generic_use_ko": "접착제를 정량 도포하는 용도",
            "product_visual_summary_ko": "노즐과 검은색 마개가 있는 노란색 플라스틱 병이다.",
            "image_usable": True,
            "image_usability_reason_ko": "두 사진에서 제품 외형을 확인할 수 있다.",
            "brand_or_personal_text_visible": True,
            "evidence_observations_ko": ["가느다란 도포 노즐이 보인다."],
            "confidence": 0.81,
        }
    )

    assert metadata.generic_product_name_ko == "목공용 접착제 용기"
    dumped = metadata.model_dump()
    assert "visible_condition" not in dumped
    assert "price" not in dumped
