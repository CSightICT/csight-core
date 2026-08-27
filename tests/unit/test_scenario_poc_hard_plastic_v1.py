from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from evaluation.scenario_poc_hard_plastic_v1.validate import (
    PackValidationError,
    validate_pack,
)

pytestmark = pytest.mark.unit

PACK_DIR = Path(__file__).resolve().parents[2] / "evaluation" / "scenario_poc_hard_plastic_v1"


def test_synthetic_hard_plastic_pack_is_complete_and_safe() -> None:
    result = validate_pack(PACK_DIR)

    assert result == {
        "verdict": "PASS_SYNTHETIC_SCENARIO_PACK",
        "record_count": 36,
        "demo_scenario_count": 5,
        "functional_still_image_boundary_count": 14,
        "source_type": "SYNTHETIC_REFERENCE",
        "product_domain_status": "NOT_EVALUATED",
        "actual_performance_or_roi_claimed": False,
    }


def test_validator_rejects_low_score_being_redefined_as_normal(tmp_path: Path) -> None:
    mutated = tmp_path / "pack"
    shutil.copytree(PACK_DIR, mutated)
    model_path = mutated / "model_manifest.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["decision_boundary"]["below_threshold"] = "NORMAL"
    model_path.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PackValidationError, match="low score cannot mean normal"):
        validate_pack(mutated)


def test_validator_rejects_case_without_one_to_one_gold(tmp_path: Path) -> None:
    mutated = tmp_path / "pack"
    shutil.copytree(PACK_DIR, mutated)
    gold_path = mutated / "gold.jsonl"
    rows = gold_path.read_text(encoding="utf-8").splitlines()
    gold_path.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")

    with pytest.raises(PackValidationError, match="Case and Gold IDs must match one-to-one"):
        validate_pack(mutated)


def test_validator_rejects_unsafe_manifest_claim_boundary(tmp_path: Path) -> None:
    mutated = tmp_path / "pack"
    shutil.copytree(PACK_DIR, mutated)
    manifest_path = mutated / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["claims_boundary"]["actual_customer_data_used"] = True
    manifest["claims_boundary"]["actual_performance_or_roi_claim_allowed"] = True
    manifest["claims_boundary"]["verdict"] = "LIMITED_POC"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PackValidationError, match="exact synthetic safety boundary"):
        validate_pack(mutated)
