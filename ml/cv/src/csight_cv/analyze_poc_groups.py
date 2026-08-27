from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
)

REQUIRED_COLUMNS = {
    "capture_id",
    "item_identifier",
    "item_material",
    "defect",
    "major_defect",
    "defect_types",
    "defect_probability",
}


def load_predictions(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Missing prediction columns: {sorted(missing)}")
    if frame["capture_id"].duplicated().any():
        raise ValueError(f"Duplicate capture_id values in {path}")
    return frame


def choose_threshold(frame: pd.DataFrame, target_precision: float) -> dict[str, float]:
    labels = frame["defect"].astype(int).to_numpy()
    scores = frame["defect_probability"].astype(float).to_numpy()
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    candidates = np.flatnonzero(precision[:-1] >= target_precision)
    if candidates.size == 0:
        raise ValueError(f"No validation threshold reaches precision {target_precision:.3f}")
    best = max(
        candidates.tolist(),
        key=lambda index: (recall[index], precision[index], thresholds[index]),
    )
    return {
        "threshold": float(thresholds[best]),
        "validation_precision": float(precision[best]),
        "validation_recall": float(recall[best]),
        "target_validation_precision": target_precision,
    }


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    if total == 0:
        return math.nan, math.nan
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    variance = proportion * (1 - proportion) / total + z**2 / (4 * total**2)
    margin = z * math.sqrt(variance) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def classification_metrics(frame: pd.DataFrame, threshold: float) -> dict[str, float | int]:
    labels = frame["defect"].astype(bool).to_numpy()
    scores = frame["defect_probability"].astype(float).to_numpy()
    predicted = scores >= threshold
    true_positive = int(np.sum(predicted & labels))
    false_positive = int(np.sum(predicted & ~labels))
    true_negative = int(np.sum(~predicted & ~labels))
    false_negative = int(np.sum(~predicted & labels))
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    specificity = true_negative / max(true_negative + false_positive, 1)
    return {
        "samples": len(frame),
        "positives": int(labels.sum()),
        "negatives": int((~labels).sum()),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "true_negative": true_negative,
        "false_negative": false_negative,
        "precision": precision,
        "recall_detection_rate": recall,
        "specificity": specificity,
        "false_positive_rate": 1 - specificity,
        "f1": 2 * precision * recall / max(precision + recall, np.finfo(float).eps),
        "average_precision": float(average_precision_score(labels, scores)),
        "auroc": float(roc_auc_score(labels, scores)),
    }


def material_metrics(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for material, group in frame.groupby("item_material", sort=True):
        labels = group["defect"].astype(bool).to_numpy()
        scores = group["defect_probability"].astype(float).to_numpy()
        predicted = scores >= threshold
        true_positive = int(np.sum(predicted & labels))
        false_positive = int(np.sum(predicted & ~labels))
        true_negative = int(np.sum(~predicted & ~labels))
        positives = int(labels.sum())
        negatives = int((~labels).sum())
        recall_low, recall_high = wilson_interval(true_positive, positives)
        rows.append(
            {
                "item_material": material,
                "samples": len(group),
                "positives": positives,
                "negatives": negatives,
                "average_precision": (
                    float(average_precision_score(labels, scores))
                    if positives and negatives
                    else math.nan
                ),
                "auroc": (
                    float(roc_auc_score(labels, scores)) if positives and negatives else math.nan
                ),
                "recall_detection_rate": true_positive / max(positives, 1),
                "recall_ci95_low": recall_low,
                "recall_ci95_high": recall_high,
                "precision": true_positive / max(true_positive + false_positive, 1),
                "false_positive_rate": false_positive / max(false_positive + true_negative, 1),
            }
        )
    return pd.DataFrame(rows)


def explode_defect_types(frame: pd.DataFrame) -> pd.DataFrame:
    positives = frame.loc[frame["defect"].astype(bool)].copy()
    positives["defect_type"] = positives["defect_types"].fillna("").str.split(",")
    positives = positives.explode("defect_type")
    return positives.loc[positives["defect_type"].astype(bool)].copy()


def defect_type_metrics(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    exploded = explode_defect_types(frame)
    rows: list[dict[str, Any]] = []
    for defect_type, group in exploded.groupby("defect_type", sort=True):
        detected = group["defect_probability"].astype(float).to_numpy() >= threshold
        successes = int(detected.sum())
        total = len(group)
        low, high = wilson_interval(successes, total)
        rows.append(
            {
                "defect_type": defect_type,
                "positive_samples": total,
                "detected_samples": successes,
                "recall_detection_rate": successes / total,
                "recall_ci95_low": low,
                "recall_ci95_high": high,
                "major_defect_rate": float(group["major_defect"].astype(bool).mean()),
            }
        )
    return pd.DataFrame(rows)


def material_defect_metrics(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    exploded = explode_defect_types(frame)
    rows: list[dict[str, Any]] = []
    for (material, defect_type), group in exploded.groupby(
        ["item_material", "defect_type"], sort=True
    ):
        detected = group["defect_probability"].astype(float).to_numpy() >= threshold
        successes = int(detected.sum())
        total = len(group)
        low, high = wilson_interval(successes, total)
        rows.append(
            {
                "item_material": material,
                "defect_type": defect_type,
                "positive_samples": total,
                "detected_samples": successes,
                "recall_detection_rate": successes / total,
                "recall_ci95_low": low,
                "recall_ci95_high": high,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-predictions", type=Path, required=True)
    parser.add_argument("--test-predictions", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--target-validation-precision", type=float, default=0.90)
    parser.add_argument("--minimum-positive-support", type=int, default=30)
    args = parser.parse_args()

    validation = load_predictions(args.validation_predictions)
    test = load_predictions(args.test_predictions)
    threshold = choose_threshold(validation, args.target_validation_precision)
    threshold_value = threshold["threshold"]
    overall = classification_metrics(test, threshold_value)
    materials = material_metrics(test, threshold_value)
    defect_types = defect_type_metrics(test, threshold_value)
    combinations = material_defect_metrics(test, threshold_value)
    eligible_materials = materials.loc[
        (materials["positives"] >= args.minimum_positive_support)
        & (materials["negatives"] >= args.minimum_positive_support)
    ].sort_values(
        ["recall_detection_rate", "average_precision", "positives"],
        ascending=False,
    )
    eligible_defects = defect_types.loc[
        defect_types["positive_samples"] >= args.minimum_positive_support
    ].sort_values(["recall_detection_rate", "positive_samples"], ascending=False)
    eligible_combinations = combinations.loc[
        combinations["positive_samples"] >= args.minimum_positive_support
    ].sort_values(["recall_detection_rate", "positive_samples"], ascending=False)
    item_support = test.groupby("item_identifier").agg(
        samples=("capture_id", "size"), positives=("defect", "sum")
    )
    item_support["negatives"] = item_support["samples"] - item_support["positives"]

    args.output_directory.mkdir(parents=True, exist_ok=True)
    materials.to_csv(args.output_directory / "test-by-material.csv", index=False)
    defect_types.to_csv(args.output_directory / "test-by-defect-type.csv", index=False)
    combinations.to_csv(args.output_directory / "test-by-material-defect-type.csv", index=False)
    result = {
        "protocol": {
            "threshold_selected_on": "validation",
            "group_metrics_evaluated_on": "test",
            "target_validation_precision": args.target_validation_precision,
            "minimum_positive_support": args.minimum_positive_support,
        },
        "threshold": threshold,
        "test_overall": overall,
        "best_eligible_material": eligible_materials.iloc[0].to_dict(),
        "best_eligible_defect_type": eligible_defects.iloc[0].to_dict(),
        "best_eligible_material_defect_combination": (eligible_combinations.iloc[0].to_dict()),
        "item_identifier_support": {
            "identifiers": len(item_support),
            "median_samples": float(item_support["samples"].median()),
            "maximum_samples": int(item_support["samples"].max()),
            "both_classes_at_least_5": int(
                ((item_support["positives"] >= 5) & (item_support["negatives"] >= 5)).sum()
            ),
            "both_classes_at_least_10": int(
                ((item_support["positives"] >= 10) & (item_support["negatives"] >= 10)).sum()
            ),
        },
        "item_identifier_note": (
            "Opaque identifiers have too few samples per item for stable PoC ranking; "
            "material categories are used instead."
        ),
    }
    with (args.output_directory / "poc-analysis.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
