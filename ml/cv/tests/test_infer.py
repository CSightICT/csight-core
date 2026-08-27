from __future__ import annotations

import json
from pathlib import Path

import pytest
from csight_cv.infer import build_result, decision_support_band, validate_package

PACKAGE_DIRECTORY = Path(__file__).resolve().parents[1] / "model_package" / "e3_v1"


def test_model_package_is_internally_consistent() -> None:
    manifest, preprocess, thresholds = validate_package(PACKAGE_DIRECTORY)

    assert manifest["model_version"] == "e3-epoch10-20260827"
    assert preprocess["resize"] == {
        "type": "resize",
        "width": 1024,
        "height": 1024,
        "interpolation": "bicubic",
        "antialias": True,
        "preserve_aspect_ratio": False,
    }
    assert thresholds["high_confidence_defect_candidate"] == pytest.approx(0.8984375)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.8984375, "HIGH_CONFIDENCE_DEFECT_CANDIDATE"),
        (0.99, "HIGH_CONFIDENCE_DEFECT_CANDIDATE"),
        (0.8984374, "HUMAN_REVIEW_REQUIRED"),
        (0.0, "HUMAN_REVIEW_REQUIRED"),
    ],
)
def test_decision_support_band_never_confirms_normal(score: float, expected: str) -> None:
    assert decision_support_band(score, 0.8984375) == expected


def test_result_contract_is_json_serializable_and_requires_human_approval() -> None:
    manifest, _, thresholds = validate_package(PACKAGE_DIRECTORY)
    payload = build_result(
        manifest=manifest,
        thresholds=thresholds,
        image_path=Path("sample.jpg"),
        image_sha256="a" * 64,
        image_width=2048,
        image_height=2048,
        defect_probability=0.91,
    )

    json.dumps(payload)
    assert payload["analysis"]["decision_support_band"] == ("HIGH_CONFIDENCE_DEFECT_CANDIDATE")
    assert payload["safety"]["human_final_approval_required"] is True
    assert payload["capabilities"]["defect_type"] is False
