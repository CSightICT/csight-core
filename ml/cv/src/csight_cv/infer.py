from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import torch
from PIL import Image

from csight_cv.data import build_transform
from csight_cv.model import Dinov2BinaryClassifier

DEFAULT_PACKAGE_DIRECTORY = (
    Path(__file__).resolve().parents[2] / "model_package" / "e3_v1"
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_package(
    package_directory: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = _load_json(package_directory / "manifest.json")
    preprocess = _load_json(package_directory / "preprocess.json")
    thresholds = _load_json(package_directory / "thresholds.json")
    if manifest.get("schema_version") != "1.0":
        raise ValueError("Unsupported model-package schema version")
    if preprocess.get("version") != manifest.get("preprocess_version"):
        raise ValueError("Preprocess version does not match manifest")
    if thresholds.get("version") != manifest.get("threshold_version"):
        raise ValueError("Threshold version does not match manifest")
    if thresholds.get("low_score_action") != "HUMAN_REVIEW_REQUIRED":
        raise ValueError("Low-score cases must remain subject to human review")
    return manifest, preprocess, thresholds


def decision_support_band(score: float, threshold: float) -> str:
    if not 0.0 <= score <= 1.0:
        raise ValueError("Defect probability must be in [0, 1]")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("Threshold must be in [0, 1]")
    if score >= threshold:
        return "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
    return "HUMAN_REVIEW_REQUIRED"


def build_result(
    *,
    manifest: dict[str, Any],
    thresholds: dict[str, Any],
    image_path: Path,
    image_sha256: str,
    image_width: int,
    image_height: int,
    defect_probability: float,
) -> dict[str, Any]:
    threshold = float(thresholds["high_confidence_defect_candidate"])
    return {
        "schema_version": "1.0",
        "model": {
            "name": manifest["model_name"],
            "version": manifest["model_version"],
            "checkpoint_sha256": manifest["checkpoint"]["sha256"],
            "preprocess_version": manifest["preprocess_version"],
            "threshold_version": manifest["threshold_version"],
        },
        "input": {
            "file_name": image_path.name,
            "image_sha256": image_sha256,
            "width": image_width,
            "height": image_height,
        },
        "analysis": {
            "defect_probability": defect_probability,
            "threshold": threshold,
            "decision_support_band": decision_support_band(
                defect_probability, threshold
            ),
        },
        "capabilities": {
            "binary_defect_probability": True,
            "defect_type": False,
            "defect_location_or_mask": False,
            "severity": False,
        },
        "safety": {
            "human_final_approval_required": True,
            "low_score_is_not_normal_confirmation": True,
            "high_risk_cases_require_escalation": True,
        },
    }


def infer(
    image_path: Path,
    checkpoint_path: Path,
    package_directory: Path,
    device_name: str,
) -> dict[str, Any]:
    manifest, preprocess, thresholds = validate_package(package_directory)
    actual_checkpoint_sha256 = sha256_file(checkpoint_path)
    expected_checkpoint_sha256 = str(manifest["checkpoint"]["sha256"])
    if actual_checkpoint_sha256 != expected_checkpoint_sha256:
        raise ValueError(
            "Checkpoint SHA-256 does not match the model package: "
            f"expected {expected_checkpoint_sha256}, got {actual_checkpoint_sha256}"
        )

    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    device = torch.device(device_name)

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model_config = checkpoint["config"]
    if str(model_config["model_name"]) != str(manifest["base_model"]):
        raise ValueError("Checkpoint base model does not match the manifest")
    if int(model_config["image_size"]) != int(preprocess["resize"]["height"]):
        raise ValueError("Checkpoint image size does not match preprocess.json")

    model = Dinov2BinaryClassifier(
        str(model_config["model_name"]),
        str(model_config["training_mode"]),
        gradient_checkpointing=False,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device).eval()

    transform = build_transform(
        image_size=int(preprocess["resize"]["height"]),
        training=False,
        auto_augment="",
        resize_mode="full_frame",
        horizontal_flip=0.0,
        vertical_flip=0.0,
    )
    with Image.open(image_path) as image:
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        pixel_values = transform(rgb_image).unsqueeze(0).to(device)

    use_bf16 = device.type == "cuda" and torch.cuda.is_bf16_supported()
    autocast = (
        torch.autocast(device_type="cuda", dtype=torch.bfloat16)
        if use_bf16
        else nullcontext()
    )
    with torch.inference_mode(), autocast:
        defect_probability = float(
            torch.sigmoid(model(pixel_values)).float().cpu().item()
        )

    return build_result(
        manifest=manifest,
        thresholds=thresholds,
        image_path=image_path,
        image_sha256=sha256_file(image_path),
        image_width=width,
        image_height=height,
        defect_probability=defect_probability,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the versioned CSight E3 vision model"
    )
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--package-directory", type=Path, default=DEFAULT_PACKAGE_DIRECTORY
    )
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = infer(args.image, args.checkpoint, args.package_directory, args.device)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
