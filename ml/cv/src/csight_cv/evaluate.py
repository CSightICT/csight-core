from __future__ import annotations

import argparse
import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pandas as pd
import torch
import yaml
from torch.utils.data import DataLoader

from csight_cv.data import KaputtQueryDataset
from csight_cv.metrics import binary_metrics
from csight_cv.model import Dinov2BinaryClassifier


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--split", choices=("validation", "test"), default="validation")
    parser.add_argument("--allow-test", action="store_true")
    args = parser.parse_args()
    if args.split == "test" and not args.allow_test:
        raise SystemExit("Refusing test evaluation without --allow-test")
    with args.config.open("r", encoding="utf-8") as handle:
        config: dict[str, Any] = yaml.safe_load(handle)
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    mode = str(checkpoint["config"]["training_mode"])
    model = Dinov2BinaryClassifier(str(config["model_name"]), mode, gradient_checkpointing=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    dataset = KaputtQueryDataset(
        Path(config["dataset_root"]),
        args.split,
        int(checkpoint["config"]["image_size"]),
        False,
        str(config["train_augmentation"]["auto_augment"]),
    )
    loader = DataLoader(
        dataset,
        batch_size=int(config["batch_size"]),
        shuffle=False,
        num_workers=int(config["num_workers"]),
        pin_memory=torch.cuda.is_available(),
    )
    labels: list[float] = []
    major_labels: list[float] = []
    scores: list[float] = []
    rows: list[dict[str, Any]] = []
    use_bf16 = device.type == "cuda" and torch.cuda.is_bf16_supported()
    if use_bf16:
        autocast = torch.autocast(device_type="cuda", dtype=torch.bfloat16)
    else:
        autocast = nullcontext()
    with torch.inference_mode():
        for batch in loader:
            with autocast:
                logits = model(batch["pixel_values"].to(device, non_blocking=True))
            probabilities = torch.sigmoid(logits).float().cpu().tolist()
            batch_labels = batch["label"].tolist()
            batch_major = batch["major_label"].tolist()
            labels.extend(batch_labels)
            major_labels.extend(batch_major)
            scores.extend(probabilities)
            for index, score in enumerate(probabilities):
                rows.append(
                    {
                        "capture_id": batch["capture_id"][index],
                        "item_identifier": batch["item_identifier"][index],
                        "item_material": batch["item_material"][index],
                        "defect": bool(batch_labels[index]),
                        "major_defect": bool(batch_major[index]),
                        "defect_types": batch["defect_types"][index],
                        "defect_probability": score,
                    }
                )
    metrics = binary_metrics(labels, major_labels, scores)
    output_directory = args.checkpoint.parent / "evaluation"
    output_directory.mkdir(parents=True, exist_ok=True)
    with (output_directory / f"{args.split}-metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)
    pd.DataFrame(rows).to_parquet(output_directory / f"{args.split}-predictions.parquet")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
