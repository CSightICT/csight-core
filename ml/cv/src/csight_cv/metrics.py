from __future__ import annotations

import math

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve


def _recall_at_precision(labels: np.ndarray, scores: np.ndarray, minimum: float) -> float:
    order = np.argsort(-scores)
    sorted_labels = labels[order]
    true_positives = np.cumsum(sorted_labels)
    ranks = np.arange(1, len(labels) + 1)
    precision = true_positives / ranks
    positives = max(float(sorted_labels.sum()), 1.0)
    recall = true_positives / positives
    eligible = recall[precision >= minimum]
    return float(eligible.max()) if eligible.size else 0.0


def _recall_at_fpr(labels: np.ndarray, scores: np.ndarray, maximum: float) -> float:
    fpr, tpr, _ = roc_curve(labels, scores)
    eligible = tpr[fpr <= maximum]
    return float(eligible.max()) if eligible.size else 0.0


def binary_metrics(
    labels: list[float], major_labels: list[float], scores: list[float]
) -> dict[str, float]:
    y = np.asarray(labels, dtype=np.int64)
    y_major = np.asarray(major_labels, dtype=np.int64)
    p = np.asarray(scores, dtype=np.float64)
    if len(y) == 0 or np.unique(y).size < 2:
        raise ValueError("Both defect classes are required for evaluation")
    ap_major = (
        float(average_precision_score(y_major, p))
        if np.unique(y_major).size == 2
        else math.nan
    )
    return {
        "ap_any": float(average_precision_score(y, p)),
        "ap_major": ap_major,
        "auroc": float(roc_auc_score(y, p)),
        "recall_at_50_precision": _recall_at_precision(y, p, 0.50),
        "recall_at_1_fpr": _recall_at_fpr(y, p, 0.01),
    }

