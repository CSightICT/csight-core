from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from PIL import Image

from scripts.evaluate_e3_normal_reference import (
    NormalReferenceFailure,
    build_report,
    select_internal_demo_records,
    validate_normal_reference,
)


def _write_images(root: Path, *, count: int = 2) -> None:
    root.mkdir()
    for rank in range(1, count + 1):
        capture_id = str(UUID(int=rank))
        Image.new("RGB", (16, 16), color=(rank, rank + 1, rank + 2)).save(
            root / f"normal_rank_{rank:03d}_{capture_id}.jpg", format="JPEG"
        )


@pytest.mark.unit
def test_validate_normal_reference_freezes_files_without_copying(tmp_path: Path) -> None:
    source = tmp_path / "normal"
    _write_images(source)

    package = validate_normal_reference(source, expected_count=2, expected_dimensions=(16, 16))

    assert [image.rank for image in package.images] == [1, 2]
    assert all(image.path.parent == source.resolve() for image in package.images)
    assert len(package.content_tree_sha256) == 64
    assert package.total_image_bytes == sum(image.path.stat().st_size for image in package.images)


@pytest.mark.unit
def test_validate_normal_reference_rejects_duplicate_hash(tmp_path: Path) -> None:
    source = tmp_path / "normal"
    _write_images(source)
    paths = sorted(source.iterdir())
    paths[1].write_bytes(paths[0].read_bytes())

    with pytest.raises(NormalReferenceFailure, match="unique"):
        validate_normal_reference(source, expected_count=2, expected_dimensions=(16, 16))


@pytest.mark.unit
def test_select_internal_demo_records_prefers_lowest_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.evaluate_e3_normal_reference.SAFE_INTERNAL_DEMO_RANKS", (21, 26, 42)
    )
    records = (
        {"rank": 21, "replay_score": 0.4},
        {"rank": 26, "replay_score": 0.1},
        {"rank": 42, "replay_score": 0.2},
    )

    selected = select_internal_demo_records(records, sample_size=2)

    assert [record["rank"] for record in selected] == [26, 42]


@pytest.mark.unit
def test_report_keeps_normal_and_metric_claims_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("scripts.evaluate_e3_normal_reference.SAFE_INTERNAL_DEMO_RANKS", (1, 2))
    source = tmp_path / "normal"
    _write_images(source)
    package = validate_normal_reference(source, expected_count=2, expected_dimensions=(16, 16))
    records = (
        {"rank": 1, "replay_score": 0.1},
        {"rank": 2, "replay_score": 0.9},
    )

    report = build_report(
        package,
        {"summary": {"verdict": "NORMAL_REFERENCE_REPLAY_COMPLETED"}},
        records,
        demo_sample_size=1,
    )

    source_directory = cast(Mapping[str, object], report["source_directory"])
    safety = cast(Mapping[str, object], report["safety"])
    claim_boundary = cast(Mapping[str, object], report["claim_boundary"])
    not_supported = cast(Sequence[object], claim_boundary["not_supported"])
    assert source_directory["annotation_provenance_status"] == "USER_STATEMENT_ONLY"
    assert safety["below_threshold_means_normal"] is False
    assert "formal accuracy, specificity, false-positive rate, or calibration" in not_supported
    assert hashlib.sha256(b"normal").hexdigest() != report["report_sha256"]
