from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

EXPECTED_ROWS = {"train": 85_326, "validation": 4_874, "test": 10_067}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--check-images", action="store_true")
    args = parser.parse_args()
    frames: dict[str, pd.DataFrame] = {}
    report: dict[str, object] = {"splits": {}, "item_overlap": {}}
    for split, expected_rows in EXPECTED_ROWS.items():
        frame = pd.read_parquet(args.dataset_root / f"query-{split}.parquet")
        frames[split] = frame
        missing_images = None
        if args.check_images:
            missing_images = sum(
                not (args.dataset_root / path).is_file()
                for path in frame["query_image"]
            )
        report["splits"][split] = {
            "rows": len(frame),
            "expected_rows": expected_rows,
            "row_count_matches": len(frame) == expected_rows,
            "unique_items": int(frame["item_identifier"].nunique()),
            "defect_rate": float(frame["defect"].mean()),
            "major_defect_rate": float(frame["major_defect"].mean()),
            "missing_images": missing_images,
        }
    for left, right in (
        ("train", "validation"),
        ("train", "test"),
        ("validation", "test"),
    ):
        overlap = set(frames[left]["item_identifier"]) & set(
            frames[right]["item_identifier"]
        )
        report["item_overlap"][f"{left}__{right}"] = len(overlap)
    failures = [
        split
        for split, values in report["splits"].items()
        if not values["row_count_matches"] or values["missing_images"] not in {None, 0}
    ]
    overlap_failures = [
        key for key, value in report["item_overlap"].items() if value != 0
    ]
    report["valid"] = not failures and not overlap_failures
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

