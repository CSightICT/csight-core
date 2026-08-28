from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.seed_realistic_poc_demo import (
    DATASET_ID_V1,
    DATASET_ID_V2,
    DATASET_ID_V3,
    DEFAULT_MANIFEST_V1,
    DEFAULT_MANIFEST_V2,
    DEFAULT_MANIFEST_V3,
    DEFAULT_OUTPUT_V1,
    DEFAULT_OUTPUT_V2,
    DEFAULT_OUTPUT_V3,
    DemoManifest,
    RealisticDemoSeedFailure,
    ResolvedDemoSource,
    build_case_attributes,
    build_seed_idempotency_key,
    load_manifest,
    resolve_output_path,
)


@pytest.mark.unit
def test_v2_preserves_v1_sources_but_uses_an_independent_dataset_contract() -> None:
    v1 = load_manifest(DEFAULT_MANIFEST_V1)
    v2 = load_manifest(DEFAULT_MANIFEST_V2)

    assert v1.schema_version == "1.0.0"
    assert v1.dataset_id == DATASET_ID_V1
    assert v2.schema_version == "2.0.0"
    assert v2.dataset_id == DATASET_ID_V2
    assert v2.narrative_contract is not None
    assert v2.narrative_contract.display_label == "문의 내용"
    assert v2.narrative_contract.real_company_affiliation_claimed is False
    assert v2.narrative_contract.revision == "COMMERCE_CONTEXT_R2_E3"
    assert [
        (item.source.kind, item.source.rank, item.source.image_sha256) for item in v2.cases
    ] == [(item.source.kind, item.source.rank, item.source.image_sha256) for item in v1.cases]
    assert {item.demo_id for item in v1.cases}.isdisjoint(item.demo_id for item in v2.cases)
    assert {item.case_input.order_ref for item in v1.cases}.isdisjoint(
        item.case_input.order_ref for item in v2.cases
    )


@pytest.mark.unit
def test_v2_inquiries_are_long_fictional_ecommerce_messages_with_explicit_requests() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST_V2)
    messages = [item.case_input.customer_message for item in manifest.cases]

    assert len(messages) == 10
    assert len(set(messages)) == 10
    assert {item.case_input.requested_action for item in manifest.cases} == {
        "EXCHANGE",
        "REFUND",
        "RETURN",
        "REPAIR",
        "INFORMATION",
        "OTHER",
    }
    assert sum("다시 배송" in message for message in messages) == 2
    for message in messages:
        assert 3 <= sum(message.count(mark) for mark in (".", "?", "!")) <= 5
        assert len(message) >= 120
        assert "주문" in message
        assert "배송" in message
        assert "개봉" in message
        assert "사용" in message
        assert not re.search(r"쿠팡|아마존|coupang|amazon", message, re.IGNORECASE)
        assert not re.search(r"[\w.+-]+@[\w.-]+", message)
        assert not re.search(r"\b0\d{1,2}-\d{3,4}-\d{4}\b", message)
    for item in manifest.cases:
        commerce = item.case_input.attributes["synthetic_commerce_context"]
        assert isinstance(commerce, dict)
        assert commerce["data_classification"] == "SYNTHETIC_DEMO_ONLY"
        customer = commerce["customer"]
        delivery = commerce["delivery"]
        assert isinstance(customer, dict)
        assert isinstance(delivery, dict)
        assert re.fullmatch(r"010-\*{4}-\d{4}", str(customer["phone_masked"]))
        assert "데모" in str(delivery["address_line1"]) or "가상" in str(delivery["address_line1"])
        assert len(str(item.case_input.attributes["demo_image_observation"])) >= 20
        assert (
            item.case_input.attributes["demo_claim_boundary"]
            == "CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS"
        )


@pytest.mark.unit
def test_v2_schema_rejects_version_drift_short_messages_and_real_company_names() -> None:
    payload = json.loads(DEFAULT_MANIFEST_V2.read_text(encoding="utf-8"))
    payload["schema_version"] = "1.0.0"
    with pytest.raises(ValidationError, match="schema_version and dataset_id"):
        DemoManifest.model_validate(payload)

    payload = json.loads(DEFAULT_MANIFEST_V2.read_text(encoding="utf-8"))
    payload["cases"][0]["case_input"]["customer_message"] = (
        "배송 후 개봉했습니다. 사용하지 않았습니다. 교환해 주세요."
    )
    with pytest.raises(ValidationError, match="three to five substantive sentences"):
        DemoManifest.model_validate(payload)

    payload = json.loads(DEFAULT_MANIFEST_V2.read_text(encoding="utf-8"))
    payload["cases"][0]["case_input"]["customer_message"] += " 쿠팡 정책을 적용해 주세요."
    with pytest.raises(ValidationError, match="cannot name or impersonate"):
        DemoManifest.model_validate(payload)

    for pii in (" demo@example.com", " 010-1234-5678"):
        payload = json.loads(DEFAULT_MANIFEST_V2.read_text(encoding="utf-8"))
        payload["cases"][0]["case_input"]["customer_message"] += pii
        with pytest.raises(ValidationError, match="cannot contain email or phone PII"):
            DemoManifest.model_validate(payload)


@pytest.mark.unit
def test_v1_and_v2_idempotency_and_report_paths_cannot_collide() -> None:
    v1 = load_manifest(DEFAULT_MANIFEST_V1)
    v2 = load_manifest(DEFAULT_MANIFEST_V2)

    assert (
        build_seed_idempotency_key(
            v1,
            v1.cases[0],
            operation="case",
        )
        == "realistic-internal-demo-v1-case-real-demo-defect-01"
    )
    assert (
        build_seed_idempotency_key(
            v2,
            v2.cases[0],
            operation="case",
        )
        == "realistic-internal-demo-v2-commerce-context-r2-e3-case-real-demo-v2-defect-01"
    )
    assert {
        build_seed_idempotency_key(v1, item, operation=operation)
        for item in v1.cases
        for operation in ("case", "analysis", "analysis-retry-1", "analysis-retry-2")
    }.isdisjoint(
        build_seed_idempotency_key(v2, item, operation=operation)
        for item in v2.cases
        for operation in ("case", "analysis", "analysis-retry-1", "analysis-retry-2")
    )

    assert resolve_output_path(v1, None) == DEFAULT_OUTPUT_V1
    assert resolve_output_path(v2, None) == DEFAULT_OUTPUT_V2
    with pytest.raises(RealisticDemoSeedFailure, match="cannot overwrite"):
        resolve_output_path(v1, DEFAULT_OUTPUT_V2)
    with pytest.raises(RealisticDemoSeedFailure, match="cannot overwrite"):
        resolve_output_path(v2, DEFAULT_OUTPUT_V1)


@pytest.mark.unit
def test_v3_materializes_ten_new_cases_without_mutating_v2() -> None:
    v2 = load_manifest(DEFAULT_MANIFEST_V2)
    v3 = load_manifest(DEFAULT_MANIFEST_V3)

    assert v3.schema_version == "3.0.0"
    assert v3.dataset_id == DATASET_ID_V3
    assert len(v3.cases) == 10
    assert {item.source.rank for item in v3.cases if "DEFECT" in item.demo_id} == {
        1,
        9,
        22,
        31,
        73,
        79,
    }
    assert {item.source.rank for item in v3.cases if "NORMAL" in item.demo_id} == {
        1,
        20,
        65,
        67,
    }
    assert {item.demo_id for item in v2.cases}.isdisjoint(item.demo_id for item in v3.cases)
    assert {item.case_input.order_ref for item in v2.cases}.isdisjoint(
        item.case_input.order_ref for item in v3.cases
    )
    assert resolve_output_path(v3, None) == DEFAULT_OUTPUT_V3
    with pytest.raises(RealisticDemoSeedFailure, match="cannot overwrite"):
        resolve_output_path(v3, DEFAULT_OUTPUT_V2)


@pytest.mark.unit
def test_v3_expansion_inquiries_and_commerce_amounts_are_self_consistent() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST_V3)

    for item in manifest.cases:
        assert item.demo_id.startswith("REAL-DEMO-V3-")
        assert len(item.case_input.customer_message) >= 120
        context = item.case_input.attributes["synthetic_commerce_context"]
        assert isinstance(context, dict)
        order = context["order"]
        assert isinstance(order, dict)
        merchandise = int(str(order["merchandise_amount"]))
        shipping = int(str(order["shipping_fee"]))
        discount = int(str(order["discount_amount"]))
        paid = int(str(order["paid_amount"]))
        assert paid == merchandise + shipping - discount
        if item.case_input.requested_action == "REFUND":
            external = item.case_input.attributes["external_action_input"]
            assert isinstance(external, dict)
            assert int(str(external["amount"])) == paid
            assert external["currency"] == "KRW"


@pytest.mark.unit
def test_v2_provenance_is_versioned_without_changing_safety_boundaries(tmp_path: Path) -> None:
    manifest = load_manifest(DEFAULT_MANIFEST_V2)
    definition = manifest.cases[0]
    source = ResolvedDemoSource(
        definition=definition,
        path=tmp_path / "unused.jpg",
        capture_id="capture",
        image_sha256=definition.source.image_sha256,
        source_metadata={},
    )

    attributes = build_case_attributes(manifest, source)
    provenance = attributes["realistic_demo"]

    assert isinstance(provenance, dict)
    assert provenance["schema_version"] == "2.0"
    assert provenance["dataset_id"] == DATASET_ID_V2
    assert provenance["narrative_revision"] == "COMMERCE_CONTEXT_R2_E3"
    assert (
        provenance["scenario_scope"]
        == "INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD"
    )
    assert provenance["policy_input_linkage"] == "NOT_LINKED_TO_POLICY_INPUT"
    assert provenance["final_decision_owner"] == "AUTHENTICATED_HUMAN_ONLY"
    assert provenance["normal_confirmation_supported"] is False
