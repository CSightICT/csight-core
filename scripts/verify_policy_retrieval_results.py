"""Verify and report immutable policy retrieval evaluation artifacts by mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path("evaluation/results/policy_retrieval_v1")
MODES = {
    "lexical": "LEXICAL_BM25",
    "dense": "DENSE_QWEN3",
    "hybrid": "HYBRID_RRF",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=(*MODES, "all"), default="all")
    arguments = parser.parse_args()
    profile = json.loads((ROOT / "retrieval_profile_v1.json").read_text(encoding="utf-8"))
    if not profile.get("test_evaluated"):
        raise ValueError("locked test evaluation has not completed")
    selected = tuple(MODES.values()) if arguments.mode == "all" else (MODES[arguments.mode],)
    report: dict[str, object] = {"profile": profile["profile_name"], "test_locked": True}
    for split, expected_queries in (("dev", 80), ("test", 40)):
        metrics = json.loads((ROOT / f"{split}_metrics.json").read_text(encoding="utf-8"))
        rows = sum(
            1 for line in (ROOT / f"{split}_per_query.jsonl").read_text().splitlines() if line
        )
        if rows != expected_queries:
            raise ValueError(f"{split} per-query result count mismatch")
        report[split] = {mode: metrics[mode] for mode in selected}
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
