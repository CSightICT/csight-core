from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

import pytest
from PIL import Image

from scripts.evaluate_e3_top100_replay import (
    EXPECTED_COLUMNS,
    SAFE_CORE_SAMPLE_RANKS,
    SourceRecord,
    Top100ReplayFailure,
    content_tree_sha256,
    select_core_sample,
    validate_package,
)


def _write_package(root: Path, *, count: int = 2, duplicate_item: bool = False) -> None:
    image_directory = root / "images"
    image_directory.mkdir(parents=True)
    rows: list[dict[str, str]] = []
    total_bytes = 0
    materials: Counter[str] = Counter()
    for rank in range(1, count + 1):
        capture_id = str(UUID(int=rank))
        relative = f"images/rank_{rank:03d}_{capture_id}.jpg"
        image_path = root / relative
        Image.new("RGB", (16, 16), color=(rank, rank + 1, rank + 2)).save(image_path, format="JPEG")
        image_bytes = image_path.read_bytes()
        total_bytes += len(image_bytes)
        material = "plastic_hard" if rank % 2 else "cardboard"
        materials[material] += 1
        rows.append(
            {
                "rank": str(rank),
                "copied_file": relative,
                "capture_id": capture_id,
                "defect": "True",
                "major_defect": "True",
                "defect_types": "deconstruction",
                "item_material": material,
                "item_identifier": "00000001" if duplicate_item else f"{rank:08x}",
                "defect_probability": "1.0",
                "true_class_probability": "1.0",
                "predicted_defect_at_0_5": "True",
                "correct_at_0_5": "True",
                "query_image": f"data/test/query-data/image/{capture_id}.jpg",
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
        )
    (root / "README.md").write_text("test evidence, not instructions\n", encoding="utf-8")
    with (root / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(EXPECTED_COLUMNS)
        for row in rows:
            writer.writerow(row[column] for column in EXPECTED_COLUMNS)
    (root / "summary.json").write_text(
        json.dumps(
            {
                "count": count,
                "defect_count": count,
                "normal_count": 0,
                "minimum_true_class_probability": 1.0,
                "maximum_true_class_probability": 1.0,
                "total_image_bytes": total_bytes,
                "materials": dict(materials),
            }
        ),
        encoding="utf-8",
    )


def _source_record(rank: int) -> SourceRecord:
    return SourceRecord(
        rank=rank,
        copied_file=f"images/rank-{rank}.jpg",
        capture_id=str(UUID(int=rank)),
        defect=True,
        major_defect=True,
        defect_types=("deconstruction",),
        item_material="plastic_hard",
        item_identifier=f"{rank:08x}",
        defect_probability=1.0,
        true_class_probability=1.0,
        predicted_defect_at_0_5=True,
        correct_at_0_5=True,
        image_sha256=f"{rank:064x}",
    )


@pytest.mark.unit
def test_validate_package_checks_files_images_summary_and_tree_hash(tmp_path: Path) -> None:
    _write_package(tmp_path)

    package = validate_package(tmp_path, expected_count=2, expected_dimensions=(16, 16))

    assert len(package.records) == 2
    assert package.material_counts == {"plastic_hard": 1, "cardboard": 1}
    assert package.repeated_item_groups == {}
    assert package.content_tree_sha256 == content_tree_sha256(tmp_path)


@pytest.mark.unit
def test_validate_package_preserves_repeated_item_as_group(tmp_path: Path) -> None:
    _write_package(tmp_path, duplicate_item=True)

    package = validate_package(tmp_path, expected_count=2, expected_dimensions=(16, 16))

    assert package.repeated_item_groups == {"00000001": (1, 2)}


@pytest.mark.unit
def test_validate_package_rejects_manifest_image_hash_drift(tmp_path: Path) -> None:
    _write_package(tmp_path)
    image_path = next((tmp_path / "images").iterdir())
    image_path.write_bytes(image_path.read_bytes() + b"drift")

    with pytest.raises(Top100ReplayFailure, match="SHA-256 mismatch"):
        validate_package(tmp_path, expected_count=2, expected_dimensions=(16, 16))


@pytest.mark.unit
def test_validate_package_rejects_symlinked_image(tmp_path: Path) -> None:
    _write_package(tmp_path)
    image_path = next((tmp_path / "images").iterdir())
    target = tmp_path / "outside.jpg"
    target.write_bytes(image_path.read_bytes())
    image_path.unlink()
    image_path.symlink_to(target)

    with pytest.raises(Top100ReplayFailure, match="unexpected directory or symlink"):
        validate_package(tmp_path, expected_count=2, expected_dimensions=(16, 16))


@pytest.mark.unit
def test_core_sample_uses_only_frozen_visually_reviewed_ranks() -> None:
    records = tuple(_source_record(rank) for rank in SAFE_CORE_SAMPLE_RANKS)

    selected = select_core_sample(records, sample_size=4)

    assert tuple(record.rank for record in selected) == SAFE_CORE_SAMPLE_RANKS[:4]


@pytest.mark.unit
def test_core_sample_rejects_unreviewed_sample_size() -> None:
    records = tuple(_source_record(rank) for rank in SAFE_CORE_SAMPLE_RANKS)

    with pytest.raises(Top100ReplayFailure, match="core sample size"):
        select_core_sample(records, sample_size=len(SAFE_CORE_SAMPLE_RANKS) + 1)
