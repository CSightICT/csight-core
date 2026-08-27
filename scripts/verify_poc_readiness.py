"""Report the evidence-backed PoC promotion verdict."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from app.platform.poc_readiness import PocVerdict, assess_poc_readiness

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "evaluation/poc_readiness/current_gate.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--require-limited-poc", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    manifest = cast(Mapping[str, object], json.loads(args.manifest.read_text(encoding="utf-8")))
    assessment = assess_poc_readiness(manifest)
    print(json.dumps(assessment.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_limited_poc and assessment.verdict is not PocVerdict.LIMITED_POC:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
