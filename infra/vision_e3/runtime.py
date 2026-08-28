"""Safe, offline E3 checkpoint loading and deterministic image inference."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import warnings
from contextlib import nullcontext
from dataclasses import dataclass
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from time import monotonic
from typing import Any, cast

import torch
from PIL import Image, UnidentifiedImageError
from torch import nn
from torchvision import transforms
from torchvision.transforms import InterpolationMode
from transformers import Dinov2Config, Dinov2Model

MODEL_PACKAGE_DIRECTORY = Path(__file__).with_name("model_package") / "e3_v1"
EXPECTED_ROOT_KEYS = frozenset(
    {
        "best_validation_ap_any",
        "config",
        "epoch",
        "global_step",
        "model_state_dict",
        "optimizer_state_dict",
        "scheduler_state_dict",
    }
)
EXPECTED_MODEL_TENSOR_COUNT = 225
EXPECTED_MODEL_ELEMENT_COUNT = 22_056_961
EXPECTED_TASK = "product_defect_any_defect_classification"
TAXONOMY_VERSION = "kaputt-any-defect-binary-v1"
POSTPROCESS_VERSION = "sigmoid-any-defect-v1"
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_IMAGE_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class VisionRuntimeConfigurationError(RuntimeError):
    """The versioned package or checkpoint failed a startup invariant."""


class VisionImageInputError(ValueError):
    """The request body is not an allowed, decodable image."""


@dataclass(frozen=True)
class ModelPackage:
    model_name: str
    model_version: str
    checkpoint_sha256: str
    checkpoint_size_bytes: int
    base_model: str
    preprocess_version: str
    threshold_version: str
    threshold: float
    image_size: int
    normalization_mean: tuple[float, float, float]
    normalization_std: tuple[float, float, float]


@dataclass(frozen=True)
class Prediction:
    score: float
    latency_ms: int
    image_width: int
    image_height: int
    image_sha256: str


class _Dinov2BinaryClassifier(nn.Module):
    def __init__(self, config: Dinov2Config) -> None:
        super().__init__()
        self.backbone = Dinov2Model(config)
        self.classifier = nn.Linear(int(config.hidden_size), 1)

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        output = self.backbone(pixel_values=pixel_values)
        return self.classifier(output.last_hidden_state[:, 0]).squeeze(-1)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VisionRuntimeConfigurationError(f"invalid model-package JSON: {path.name}") from error
    if not isinstance(value, dict):
        raise VisionRuntimeConfigurationError(f"model-package file is not an object: {path.name}")
    return cast(dict[str, Any], value)


def _mapping(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VisionRuntimeConfigurationError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _triple(value: object, *, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise VisionRuntimeConfigurationError(f"{label} must contain three numbers")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise VisionRuntimeConfigurationError(f"{label} must contain three numbers")
    return (float(value[0]), float(value[1]), float(value[2]))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise VisionRuntimeConfigurationError("checkpoint could not be read") from error
    return digest.hexdigest()


def validate_model_package(package_directory: Path = MODEL_PACKAGE_DIRECTORY) -> ModelPackage:
    manifest = _load_json(package_directory / "manifest.json")
    preprocess = _load_json(package_directory / "preprocess.json")
    thresholds = _load_json(package_directory / "thresholds.json")
    labels = _load_json(package_directory / "labels.json")
    checkpoint = _mapping(manifest.get("checkpoint"), label="manifest.checkpoint")
    resize = _mapping(preprocess.get("resize"), label="preprocess.resize")
    normalization = _mapping(preprocess.get("normalization"), label="preprocess.normalization")
    training = _mapping(manifest.get("training"), label="manifest.training")

    expected_values = {
        "manifest.schema_version": (manifest.get("schema_version"), "1.0"),
        "manifest.model_name": (
            manifest.get("model_name"),
            "csight-dinov2-vits14-kaputt-binary",
        ),
        "manifest.model_version": (manifest.get("model_version"), "e3-epoch10-20260827"),
        "manifest.base_model": (manifest.get("base_model"), "facebook/dinov2-small"),
        "manifest.task": (manifest.get("task"), "binary_any_defect_decision_support"),
        "manifest.training.experiment": (training.get("experiment"), "E3"),
        "manifest.training.selected_epoch_one_based": (
            training.get("selected_epoch_one_based"),
            10,
        ),
        "manifest.training.training_mode": (training.get("training_mode"), "full_finetune"),
        "preprocess.version": (preprocess.get("version"), manifest.get("preprocess_version")),
        "preprocess.color_mode": (preprocess.get("color_mode"), "RGB"),
        "preprocess.resize.type": (resize.get("type"), "resize"),
        "preprocess.resize.width": (resize.get("width"), 1024),
        "preprocess.resize.height": (resize.get("height"), 1024),
        "preprocess.resize.interpolation": (resize.get("interpolation"), "bicubic"),
        "preprocess.resize.preserve_aspect_ratio": (
            resize.get("preserve_aspect_ratio"),
            False,
        ),
        "thresholds.version": (thresholds.get("version"), manifest.get("threshold_version")),
        "thresholds.low_score_action": (
            thresholds.get("low_score_action"),
            "HUMAN_REVIEW_REQUIRED",
        ),
        "thresholds.normal_confirmation_supported": (
            thresholds.get("normal_confirmation_supported"),
            False,
        ),
        "thresholds.human_final_approval_required": (
            thresholds.get("human_final_approval_required"),
            True,
        ),
        "labels.version": (labels.get("version"), manifest.get("label_version")),
        "labels.output_logit_count": (labels.get("output_logit_count"), 1),
    }
    for label, (actual, expected) in expected_values.items():
        if actual != expected:
            raise VisionRuntimeConfigurationError(f"model-package invariant failed: {label}")

    checkpoint_sha256 = checkpoint.get("sha256")
    checkpoint_size_bytes = checkpoint.get("size_bytes")
    threshold = thresholds.get("high_confidence_defect_candidate")
    if not isinstance(checkpoint_sha256, str) or len(checkpoint_sha256) != 64:
        raise VisionRuntimeConfigurationError("checkpoint SHA-256 is invalid")
    if isinstance(checkpoint_size_bytes, bool) or not isinstance(checkpoint_size_bytes, int):
        raise VisionRuntimeConfigurationError("checkpoint size is invalid")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise VisionRuntimeConfigurationError("assessment threshold is invalid")
    normalized_threshold = float(threshold)
    if not 0.0 <= normalized_threshold <= 1.0:
        raise VisionRuntimeConfigurationError("assessment threshold is outside [0, 1]")

    return ModelPackage(
        model_name=str(manifest["model_name"]),
        model_version=str(manifest["model_version"]),
        checkpoint_sha256=checkpoint_sha256,
        checkpoint_size_bytes=checkpoint_size_bytes,
        base_model=str(manifest["base_model"]),
        preprocess_version=str(manifest["preprocess_version"]),
        threshold_version=str(manifest["threshold_version"]),
        threshold=normalized_threshold,
        image_size=int(resize["height"]),
        normalization_mean=_triple(normalization.get("mean"), label="normalization.mean"),
        normalization_std=_triple(normalization.get("std"), label="normalization.std"),
    )


def _select_device(requested: str) -> torch.device:
    if requested not in {"auto", "cpu", "mps", "cuda"}:
        raise VisionRuntimeConfigurationError("VISION_E3_DEVICE must be auto, cpu, mps, or cuda")
    selected = requested
    if selected == "auto":
        if torch.cuda.is_available():
            selected = "cuda"
        elif torch.backends.mps.is_available():
            selected = "mps"
        else:
            selected = "cpu"
    if selected == "cuda" and not torch.cuda.is_available():
        raise VisionRuntimeConfigurationError("CUDA was requested but is unavailable")
    if selected == "mps" and not torch.backends.mps.is_available():
        raise VisionRuntimeConfigurationError("MPS was requested but is unavailable")
    return torch.device(selected)


def _synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elif device.type == "mps":
        torch.mps.synchronize()


class E3VisionRuntime:
    """One-process, one-model E3 runtime with fenced identity and serialized inference."""

    def __init__(
        self,
        *,
        checkpoint_path: Path,
        package_directory: Path = MODEL_PACKAGE_DIRECTORY,
        device_name: str = "auto",
    ) -> None:
        self.package = validate_model_package(package_directory)
        if checkpoint_path.is_symlink():
            raise VisionRuntimeConfigurationError("checkpoint path must not be a symbolic link")
        self.checkpoint_path = checkpoint_path.resolve(strict=True)
        checkpoint_stat = self.checkpoint_path.stat()
        if not stat.S_ISREG(checkpoint_stat.st_mode):
            raise VisionRuntimeConfigurationError("checkpoint path is not a regular file")
        if checkpoint_stat.st_uid != os.getuid() or checkpoint_stat.st_mode & 0o022:
            raise VisionRuntimeConfigurationError("checkpoint ownership or mode is unsafe")
        if checkpoint_stat.st_size != self.package.checkpoint_size_bytes:
            raise VisionRuntimeConfigurationError("checkpoint size does not match the E3 manifest")
        if sha256_file(self.checkpoint_path) != self.package.checkpoint_sha256:
            raise VisionRuntimeConfigurationError(
                "checkpoint SHA-256 does not match the E3 manifest"
            )
        unsafe_globals = torch.serialization.get_unsafe_globals_in_checkpoint(self.checkpoint_path)
        if unsafe_globals:
            raise VisionRuntimeConfigurationError("checkpoint contains unsafe pickle globals")

        checkpoint = torch.load(
            self.checkpoint_path,
            map_location="cpu",
            weights_only=True,
            mmap=True,
        )
        if not isinstance(checkpoint, dict) or frozenset(checkpoint) != EXPECTED_ROOT_KEYS:
            raise VisionRuntimeConfigurationError("checkpoint root schema is invalid")
        config = _mapping(checkpoint.get("config"), label="checkpoint.config")
        checkpoint_invariants = {
            "model_name": self.package.base_model,
            "image_size": self.package.image_size,
            "training_mode": "full_finetune",
        }
        for key, expected in checkpoint_invariants.items():
            if config.get(key) != expected:
                raise VisionRuntimeConfigurationError(f"checkpoint config mismatch: {key}")
        if checkpoint.get("epoch") != 9 or checkpoint.get("global_step") != 53_330:
            raise VisionRuntimeConfigurationError("checkpoint training identity is invalid")
        state = checkpoint.get("model_state_dict")
        if not isinstance(state, dict):
            raise VisionRuntimeConfigurationError("checkpoint model_state_dict is invalid")
        if len(state) != EXPECTED_MODEL_TENSOR_COUNT or any(
            not isinstance(value, torch.Tensor) or value.dtype is not torch.float32
            for value in state.values()
        ):
            raise VisionRuntimeConfigurationError("checkpoint tensor schema is invalid")
        if sum(value.numel() for value in state.values()) != EXPECTED_MODEL_ELEMENT_COUNT:
            raise VisionRuntimeConfigurationError("checkpoint parameter count is invalid")
        if any(not bool(torch.isfinite(value).all()) for value in state.values()):
            raise VisionRuntimeConfigurationError("checkpoint contains non-finite model tensors")

        architecture = Dinov2Config.from_json_file(str(package_directory / "dinov2_config.json"))
        model = _Dinov2BinaryClassifier(architecture)
        incompatible = model.load_state_dict(state, strict=True, assign=True)
        if incompatible.missing_keys or incompatible.unexpected_keys:
            raise VisionRuntimeConfigurationError(
                "checkpoint keys do not match the E3 architecture"
            )
        del checkpoint

        self.device = _select_device(device_name)
        self.model = model.to(self.device).eval()
        self.precision = "bfloat16-autocast" if self._use_bf16() else "float32"
        self._inference_lock = threading.Lock()
        self._transform = transforms.Compose(
            [
                transforms.Resize(
                    (self.package.image_size, self.package.image_size),
                    interpolation=InterpolationMode.BICUBIC,
                    antialias=True,
                ),
                transforms.ToTensor(),
                transforms.Normalize(
                    self.package.normalization_mean,
                    self.package.normalization_std,
                ),
            ]
        )

    def _use_bf16(self) -> bool:
        return self.device.type == "cuda" and torch.cuda.is_bf16_supported()

    def predict(self, *, image_bytes: bytes, content_type: str) -> Prediction:
        expected_format = ALLOWED_IMAGE_FORMATS.get(content_type)
        if expected_format is None:
            raise VisionImageInputError("unsupported image content type")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(image_bytes)) as source:
                    width, height = source.size
                    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                        raise VisionImageInputError("image dimensions are invalid")
                    if int(getattr(source, "n_frames", 1)) != 1:
                        raise VisionImageInputError("multi-frame images are not supported")
                    source.load()
                    if source.format != expected_format:
                        raise VisionImageInputError(
                            "image bytes do not match the declared content type"
                        )
                    rgb_image = source.convert("RGB")
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            UnidentifiedImageError,
            OSError,
        ):
            raise VisionImageInputError("image could not be decoded safely") from None

        with self._inference_lock:
            pixel_values = self._transform(rgb_image).unsqueeze(0).to(self.device)
            _synchronize(self.device)
            started = monotonic()
            autocast = (
                torch.autocast(device_type="cuda", dtype=torch.bfloat16)
                if self._use_bf16()
                else nullcontext()
            )
            with torch.inference_mode(), autocast:
                score = float(torch.sigmoid(self.model(pixel_values)).float().cpu().item())
            _synchronize(self.device)
            latency_ms = max(0, round((monotonic() - started) * 1000))
        if not 0.0 <= score <= 1.0:
            raise RuntimeError("model output is outside [0, 1]")
        return Prediction(
            score=score,
            latency_ms=latency_ms,
            image_width=width,
            image_height=height,
            image_sha256=hashlib.sha256(image_bytes).hexdigest(),
        )

    def warmup(self) -> Prediction:
        stream = BytesIO()
        Image.new("RGB", (32, 32), color=(127, 127, 127)).save(stream, format="PNG")
        return self.predict(image_bytes=stream.getvalue(), content_type="image/png")

    def health(self) -> dict[str, object]:
        return {
            "status": "healthy",
            "schema_version": "1.0",
            "model_name": self.package.model_name,
            "model_version": self.package.model_version,
            "model_revision": self.package.checkpoint_sha256,
            "device": self.device.type,
            "precision": self.precision,
            "task": EXPECTED_TASK,
            "threshold": self.package.threshold,
            "human_final_approval_required": True,
            "normal_confirmation_supported": False,
        }


def canonical_response(runtime: E3VisionRuntime, prediction: Prediction) -> dict[str, object]:
    package = runtime.package
    return {
        "schema_version": "1.0",
        "provider": {
            "name": "remote_vision",
            "model_name": package.model_name,
            "model_version": package.model_version,
            "model_revision": package.checkpoint_sha256,
            "taxonomy_version": TAXONOMY_VERSION,
            "threshold_version": package.threshold_version,
            "preprocess_version": package.preprocess_version,
            "postprocess_version": POSTPROCESS_VERSION,
            "framework": f"torch-{torch.__version__}+transformers-{version('transformers')}",
            "runtime": runtime.device.type,
            "precision": runtime.precision,
        },
        "image_quality": {
            "usable": "NOT_EVALUATED",
            "score": None,
            "blurred": None,
            "dark": None,
            "overexposed": None,
            "product_visible": None,
            "defect_area_visible": None,
            "rejection_reasons": [],
        },
        "image_assessment": {
            "label": "defect",
            "score": prediction.score,
            "threshold": package.threshold,
        },
        "detections": [],
        "latency_ms": prediction.latency_ms,
    }
