import pandas as pd
import pytest
from csight_cv.analyze_poc_groups import choose_threshold, material_metrics


def test_threshold_respects_validation_precision() -> None:
    frame = pd.DataFrame(
        {
            "defect": [False, False, True, True],
            "defect_probability": [0.1, 0.4, 0.8, 0.9],
        }
    )
    result = choose_threshold(frame, 0.90)
    assert result["validation_precision"] >= 0.90
    assert result["validation_recall"] == pytest.approx(1.0)


def test_material_metrics_keeps_support_and_detection_rate() -> None:
    frame = pd.DataFrame(
        {
            "item_material": ["cardboard"] * 4,
            "defect": [False, False, True, True],
            "defect_probability": [0.1, 0.7, 0.8, 0.9],
        }
    )
    result = material_metrics(frame, 0.75).iloc[0]
    assert result["samples"] == 4
    assert result["positives"] == 2
    assert result["recall_detection_rate"] == pytest.approx(1.0)
    assert result["false_positive_rate"] == pytest.approx(0.0)
