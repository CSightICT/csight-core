"""Collect one immutable, privacy-safe 100-case SHADOW qualification artifact."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.platform.shadow_evidence import (
    ShadowEvidenceError,
    ShadowForbiddenEvents,
    ShadowTaskObservation,
    collect_shadow100_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULT_ROOT = ROOT / "evaluation/results/qwen4090_shadow100"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--forbidden-events", type=Path, required=True)
    parser.add_argument("--primary-route-before-digest", required=True)
    parser.add_argument("--primary-route-after-digest", required=True)
    parser.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    return parser.parse_args()


def _regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ShadowEvidenceError(f"required regular file is missing: {path}")
    content = path.read_bytes()
    if len(content) > 64 * 1024 * 1024:
        raise ShadowEvidenceError("SHADOW evidence input exceeds its size limit")
    return content


def main() -> int:
    arguments = _arguments()
    try:
        observations = tuple(
            ShadowTaskObservation.model_validate_json(line)
            for line in _regular_file(arguments.observations).splitlines()
            if line.strip()
        )
        events = ShadowForbiddenEvents.model_validate_json(
            _regular_file(arguments.forbidden_events)
        )
    except ValidationError as error:
        raise ShadowEvidenceError("SHADOW evidence input failed its strict schema") from error
    evidence = collect_shadow100_evidence(
        observations=observations,
        forbidden_events=events,
        primary_route_before_digest=arguments.primary_route_before_digest,
        primary_route_after_digest=arguments.primary_route_after_digest,
        collected_at=datetime.now(UTC),
    )
    root = arguments.result_root / evidence.candidate_id
    if root.is_symlink():
        raise ShadowEvidenceError("SHADOW result root must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    target = root / "shadow100_evidence.json"
    if target.exists() or target.is_symlink():
        raise ShadowEvidenceError("refusing to overwrite immutable SHADOW evidence")
    target.write_text(
        json.dumps(evidence.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"SHADOW100_EVIDENCE_COLLECTED candidate={evidence.candidate_id} "
        f"cases={evidence.synthetic_case_count} digest={evidence.evidence_digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
