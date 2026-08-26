import pytest
from csight_cv.metrics import binary_metrics


def test_binary_metrics_perfect_ranking() -> None:
    metrics = binary_metrics(
        labels=[0.0, 0.0, 1.0, 1.0],
        major_labels=[0.0, 0.0, 0.0, 1.0],
        scores=[0.1, 0.2, 0.8, 0.9],
    )
    assert metrics["ap_any"] == pytest.approx(1.0)
    assert metrics["ap_major"] == pytest.approx(1.0)
    assert metrics["auroc"] == pytest.approx(1.0)
    assert metrics["recall_at_50_precision"] == pytest.approx(1.0)
    assert metrics["recall_at_1_fpr"] == pytest.approx(1.0)

