from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEIGHT_PATTERNS = ("*.pt", "*.pth", "*.ckpt", "*.safetensors")
RAW_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def test_weight_artifacts_are_excluded_from_git_and_docker_context() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for pattern in WEIGHT_PATTERNS:
        assert pattern in gitignore
        assert pattern in dockerignore
    assert ".venv-*/" in dockerignore


def test_git_tracks_no_model_weight_artifacts() -> None:
    tracked = subprocess.run(
        ("git", "ls-files", "-z"),
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")

    forbidden = tuple(
        path.decode("utf-8")
        for path in tracked
        if path and Path(path.decode("utf-8")).suffix in {".pt", ".pth", ".ckpt", ".safetensors"}
    )
    assert forbidden == ()


def test_top100_replay_keeps_raw_images_and_runtime_reports_out_of_git() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "local-data/" in gitignore
    assert "local-data/" in dockerignore

    tracked = subprocess.run(
        ("git", "ls-files", "-z", "evaluation/vision_e3_top100_replay_v1"),
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    tracked_raw_images = tuple(
        path.decode("utf-8")
        for path in tracked
        if path and Path(path.decode("utf-8")).suffix.lower() in RAW_IMAGE_SUFFIXES
    )
    assert tracked_raw_images == ()
