from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import torch

from infra.vision_e3.runtime import (
    MODEL_PACKAGE_DIRECTORY,
    E3VisionRuntime,
    VisionRuntimeConfigurationError,
    validate_model_package,
)


def test_frozen_model_package_contract() -> None:
    package = validate_model_package()

    assert package.model_name == "csight-dinov2-vits14-kaputt-binary"
    assert package.model_version == "e3-epoch10-20260827"
    assert package.checkpoint_sha256 == (
        "49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e"
    )
    assert package.checkpoint_size_bytes == 264_918_248
    assert package.image_size == 1024
    assert package.threshold == 0.8984375


def test_package_fails_closed_when_normal_confirmation_is_enabled(tmp_path: Path) -> None:
    package_directory = tmp_path / "e3_v1"
    shutil.copytree(MODEL_PACKAGE_DIRECTORY, package_directory)
    threshold_path = package_directory / "thresholds.json"
    thresholds = json.loads(threshold_path.read_text(encoding="utf-8"))
    thresholds["normal_confirmation_supported"] = True
    threshold_path.write_text(json.dumps(thresholds), encoding="utf-8")

    with pytest.raises(
        VisionRuntimeConfigurationError,
        match=r"thresholds\.normal_confirmation_supported",
    ):
        validate_model_package(package_directory)


def test_package_validates_label_version(tmp_path: Path) -> None:
    package_directory = tmp_path / "e3_v1"
    shutil.copytree(MODEL_PACKAGE_DIRECTORY, package_directory)
    labels_path = package_directory / "labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    labels["version"] = "drifted"
    labels_path.write_text(json.dumps(labels), encoding="utf-8")

    with pytest.raises(VisionRuntimeConfigurationError, match=r"labels\.version"):
        validate_model_package(package_directory)


def test_checkpoint_hash_fails_before_torch_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_path = tmp_path / "wrong-e3.pt"
    with checkpoint_path.open("wb") as handle:
        handle.truncate(264_918_248)
    load_called = False

    def forbidden_load(*args: object, **kwargs: object) -> object:
        nonlocal load_called
        load_called = True
        raise AssertionError("torch.load must not run before the hash gate")

    monkeypatch.setattr(torch, "load", forbidden_load)

    with pytest.raises(VisionRuntimeConfigurationError, match="checkpoint SHA-256"):
        E3VisionRuntime(checkpoint_path=checkpoint_path)
    assert load_called is False


def test_checkpoint_symbolic_link_is_rejected_before_read(tmp_path: Path) -> None:
    source = tmp_path / "source.pt"
    source.touch()
    link = tmp_path / "link.pt"
    link.symlink_to(source)

    with pytest.raises(VisionRuntimeConfigurationError, match="symbolic link"):
        E3VisionRuntime(checkpoint_path=link)
