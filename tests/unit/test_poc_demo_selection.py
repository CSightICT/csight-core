from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform.poc_demo_selection import (
    DefectGroup,
    PocClosedSetError,
    PocClosedSetRegistry,
    ProductClass,
    assess_poc_admission,
    load_poc_closed_set_registry,
)
from scripts.seed_realistic_poc_demo import (
    DEFAULT_MANIFEST_V2,
    ResolvedDemoSource,
    load_manifest,
    validate_closed_set_sources,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "evaluation/poc_closed_set_v1/registry.json"
EXPANSION_REGISTRY_PATH = ROOT / "evaluation/poc_closed_set_v2/registry.json"


@pytest.mark.unit
def test_committed_closed_set_freezes_four_product_and_three_defect_classes() -> None:
    registry = load_poc_closed_set_registry(REGISTRY_PATH)

    assert [item.code for item in registry.product_classes] == [item.value for item in ProductClass]
    assert [item.code for item in registry.defect_groups] == [item.value for item in DefectGroup]
    assert len(registry.assignments) == 10
    assert registry.e3_runtime_threshold == 0.8984375
    assert registry.defect_admission_min_score == 0.95
    assert registry.reference_admission_max_score == 0.1
    assert registry.below_threshold_means_normal is False
    assert registry.e3_predicts_defect_type is False
    assert registry.qwen_product_role == "CANDIDATE_ONLY_HUMAN_APPROVAL_REQUIRED"


@pytest.mark.unit
def test_expansion_registry_keeps_the_same_gates_and_adds_all_product_classes() -> None:
    registry = load_poc_closed_set_registry(EXPANSION_REGISTRY_PATH)

    assert registry.schema_version == "poc_closed_set/2.0.0"
    assert registry.dataset_id == "realistic-internal-demo-v3"
    assert len(registry.assignments) == 10
    assert {item.product_class for item in registry.assignments} == set(ProductClass)
    assert sum(bool(item.defect_groups) for item in registry.assignments) == 6
    assert sum(not item.defect_groups for item in registry.assignments) == 4


@pytest.mark.unit
def test_registry_is_bound_to_manifest_and_vetted_source_labels(tmp_path: Path) -> None:
    manifest = load_manifest(DEFAULT_MANIFEST_V2)
    registry = load_poc_closed_set_registry(REGISTRY_PATH)
    assignments = {item.demo_id: item for item in registry.assignments}
    sources = tuple(
        ResolvedDemoSource(
            definition=definition,
            path=tmp_path / f"{definition.demo_id}.jpg",
            capture_id=f"capture-{definition.source.rank}",
            image_sha256=definition.source.image_sha256,
            source_metadata={
                "defect_annotations_not_model_predictions": list(
                    assignments[definition.demo_id].source_defect_labels
                )
            },
        )
        for definition in manifest.cases
    )

    coverage = validate_closed_set_sources(manifest, sources, registry)

    assert coverage["represented_product_classes"] == [
        "KITCHEN_OR_STORAGE_ITEM",
        "PERSONAL_CARE_CONTAINER",
    ]
    assert coverage["unrepresented_product_classes"] == [
        "FOOD_OR_SUPPLEMENT_CONTAINER",
        "HOUSEHOLD_CHEMICAL_CONTAINER",
    ]
    assert coverage["unrepresented_defect_groups"] == []


@pytest.mark.unit
def test_admission_margin_is_separate_from_the_frozen_runtime_threshold() -> None:
    registry = load_poc_closed_set_registry(REGISTRY_PATH)
    defect = registry.assignments[0]
    reference = registry.assignments[-1]

    assert (
        assess_poc_admission(
            defect,
            score=0.95,
            outcome="HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        ).tier
        == "CURATED_DEFECT_CANDIDATE"
    )
    assert (
        assess_poc_admission(
            reference,
            score=0.1,
            outcome="BELOW_HIGH_CONFIDENCE_THRESHOLD",
        ).tier
        == "HUMAN_CONFIRMED_LOW_SCORE_REFERENCE"
    )
    with pytest.raises(PocClosedSetError, match="score margin"):
        assess_poc_admission(
            defect,
            score=0.94,
            outcome="HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        )
    with pytest.raises(PocClosedSetError, match="gray zone"):
        assess_poc_admission(
            reference,
            score=0.11,
            outcome="BELOW_HIGH_CONFIDENCE_THRESHOLD",
        )


@pytest.mark.unit
def test_registry_rejects_defect_groups_not_derived_from_source_annotations() -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload["assignments"][0]["defect_groups"] = ["SURFACE_DAMAGE_OR_LEAKAGE"]

    with pytest.raises(ValidationError, match="do not match source annotation mapping"):
        PocClosedSetRegistry.model_validate(payload)


@pytest.mark.unit
def test_registry_rejects_schema_dataset_cross_version() -> None:
    payload = json.loads(EXPANSION_REGISTRY_PATH.read_text(encoding="utf-8"))
    payload["dataset_id"] = "realistic-internal-demo-v2"

    with pytest.raises(ValidationError, match="schema and dataset version"):
        PocClosedSetRegistry.model_validate(payload)
