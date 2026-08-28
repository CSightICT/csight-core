"""Replay user-supplied normal-reference images through the frozen local E3 service.

This command validates and scores the directory without copying images into the
repository.  The directory name and the user's statement are the only source of
the normal label, so the report is internal scenario evidence rather than a formal
specificity, false-positive-rate, or product-qualification evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.request import Request
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from scripts.evaluate_e3_top100_replay import (
    EXPECTED_DIMENSIONS,
    EXPECTED_THRESHOLD,
    SOURCE_SELECTION_THRESHOLD,
    VISION_TASK,
    Top100ReplayFailure,
    local_base_url,
    multipart_image,
    request_json,
    validate_runtime_identity,
    validate_vision_result,
    vision_headers,
)

EXPECTED_COUNT = 77
MAX_IMAGE_BYTES = 10 * 1024 * 1024
NORMAL_FILENAME = re.compile(r"normal_rank_(?P<rank>[0-9]{3})_(?P<capture_id>[0-9a-f-]{36})\.jpg")
# Pixel-reviewed for obvious personal text, faces, barcodes, and readable branding.
# Provenance and reuse rights are still absent, so these remain internal-only.
SAFE_INTERNAL_DEMO_RANKS = (2, 8, 17, 23, 65, 67)


class NormalReferenceFailure(RuntimeError):
    """A sanitized fail-closed error for normal-reference replay."""


@dataclass(frozen=True)
class NormalReferenceImage:
    rank: int
    capture_id: str
    path: Path
    image_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ValidatedNormalReference:
    root: Path
    images: tuple[NormalReferenceImage, ...]
    total_image_bytes: int
    content_tree_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_tree_sha256(images: Sequence[NormalReferenceImage]) -> str:
    digest = hashlib.sha256()
    for image in images:
        digest.update(image.path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(image.image_sha256))
    return digest.hexdigest()


def validate_normal_reference(
    root: Path,
    *,
    expected_count: int = EXPECTED_COUNT,
    expected_dimensions: tuple[int, int] = EXPECTED_DIMENSIONS,
) -> ValidatedNormalReference:
    """Validate regular JPEG inputs and freeze their identity without trusting prose."""

    if root.is_symlink() or not root.is_dir():
        raise NormalReferenceFailure("normal reference must be a non-symlink directory")
    resolved_root = root.resolve(strict=True)
    entries = sorted(resolved_root.iterdir())
    if len(entries) != expected_count:
        raise NormalReferenceFailure(
            f"normal reference must contain exactly {expected_count} files"
        )

    images: list[NormalReferenceImage] = []
    ranks: set[int] = set()
    capture_ids: set[str] = set()
    hashes: set[str] = set()
    for path in entries:
        if path.is_symlink() or not path.is_file():
            raise NormalReferenceFailure("normal reference contains a non-regular file")
        match = NORMAL_FILENAME.fullmatch(path.name)
        if match is None:
            raise NormalReferenceFailure("normal reference filename is not canonical")
        rank = int(match.group("rank"))
        capture_id = match.group("capture_id")
        try:
            if str(UUID(capture_id)) != capture_id:
                raise ValueError
        except ValueError:
            raise NormalReferenceFailure(f"normal rank {rank} capture_id is invalid") from None
        size_bytes = path.stat().st_size
        if not 0 < size_bytes <= MAX_IMAGE_BYTES:
            raise NormalReferenceFailure(f"normal rank {rank} image size is invalid")
        image_sha256 = _sha256_file(path)
        try:
            with Image.open(path) as opened:
                opened.verify()
            with Image.open(path) as opened:
                opened.load()
                if opened.format != "JPEG" or opened.mode != "RGB":
                    raise NormalReferenceFailure(f"normal rank {rank} encoding is invalid")
                if opened.size != expected_dimensions:
                    raise NormalReferenceFailure(f"normal rank {rank} dimensions are invalid")
                if opened.getexif() or opened.info.get("icc_profile"):
                    raise NormalReferenceFailure(f"normal rank {rank} contains embedded metadata")
        except (OSError, UnidentifiedImageError):
            raise NormalReferenceFailure(f"normal rank {rank} cannot be decoded") from None
        if rank in ranks or capture_id in capture_ids or image_sha256 in hashes:
            raise NormalReferenceFailure("normal reference identifiers and hashes must be unique")
        ranks.add(rank)
        capture_ids.add(capture_id)
        hashes.add(image_sha256)
        images.append(
            NormalReferenceImage(
                rank=rank,
                capture_id=capture_id,
                path=path,
                image_sha256=image_sha256,
                size_bytes=size_bytes,
            )
        )

    ordered = tuple(sorted(images, key=lambda image: image.rank))
    return ValidatedNormalReference(
        root=resolved_root,
        images=ordered,
        total_image_bytes=sum(image.size_bytes for image in ordered),
        content_tree_sha256=_content_tree_sha256(ordered),
    )


def run_normal_reference_replay(
    package: ValidatedNormalReference,
    *,
    vision_base_url: str,
    api_key: str,
    timeout_seconds: float,
) -> tuple[Mapping[str, object], tuple[Mapping[str, object], ...]]:
    headers = vision_headers(api_key)
    health = request_json(
        Request(f"{vision_base_url}/health", headers=headers, method="GET"),
        timeout_seconds=min(timeout_seconds, 15.0),
    )
    validate_runtime_identity(health)
    records: list[Mapping[str, object]] = []
    for source in package.images:
        body, boundary = multipart_image(
            field_name="file",
            filename=f"normal-rank-{source.rank:03d}.jpg",
            content_type="image/jpeg",
            image_bytes=source.path.read_bytes(),
            fields={"task": VISION_TASK},
        )
        result = request_json(
            Request(
                f"{vision_base_url}/v1/vision/analyze",
                data=body,
                headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            ),
            timeout_seconds=timeout_seconds,
        )
        score, latency_ms = validate_vision_result(result)
        high_confidence = score >= EXPECTED_THRESHOLD
        records.append(
            {
                "rank": source.rank,
                "capture_id": source.capture_id,
                "source_filename": source.path.name,
                "image_sha256": source.image_sha256,
                "source_label": "NORMAL_USER_SUPPLIED_UNVERIFIED_PROVENANCE",
                "replay_score": score,
                "above_source_threshold_0_5": score >= SOURCE_SELECTION_THRESHOLD,
                "high_confidence_defect_candidate": high_confidence,
                "outcome": (
                    "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
                    if high_confidence
                    else "BELOW_HIGH_CONFIDENCE_THRESHOLD"
                ),
                "model_latency_ms": latency_ms,
            }
        )

    scores = [cast(float, record["replay_score"]) for record in records]
    latencies = [cast(int, record["model_latency_ms"]) for record in records]
    candidate_count = sum(bool(record["high_confidence_defect_candidate"]) for record in records)
    summary: Mapping[str, object] = {
        "verdict": "NORMAL_REFERENCE_REPLAY_COMPLETED",
        "attempted_count": len(records),
        "completed_count": len(records),
        "below_frozen_threshold_count": len(records) - candidate_count,
        "high_confidence_candidate_count_at_frozen_threshold": candidate_count,
        "minimum_score": min(scores),
        "median_score": statistics.median(scores),
        "mean_score": statistics.fmean(scores),
        "maximum_score": max(scores),
        "minimum_model_latency_ms": min(latencies),
        "median_model_latency_ms": statistics.median(latencies),
        "maximum_model_latency_ms": max(latencies),
    }
    return {"health": dict(health), "summary": dict(summary)}, tuple(records)


def _record_int(record: Mapping[str, object], key: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise NormalReferenceFailure(f"normal replay record {key} is invalid")
    return value


def _record_float(record: Mapping[str, object], key: str) -> float:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NormalReferenceFailure(f"normal replay record {key} is invalid")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise NormalReferenceFailure(f"normal replay record {key} is invalid")
    return normalized


def select_internal_demo_records(
    records: Sequence[Mapping[str, object]], *, sample_size: int = 4
) -> tuple[Mapping[str, object], ...]:
    if not 0 <= sample_size <= len(SAFE_INTERNAL_DEMO_RANKS):
        raise NormalReferenceFailure("normal demo sample size is outside the reviewed allowlist")
    by_rank = {_record_int(record, "rank"): record for record in records}
    allowed: list[Mapping[str, object]] = []
    for rank in SAFE_INTERNAL_DEMO_RANKS:
        record = by_rank.get(rank)
        if record is None:
            raise NormalReferenceFailure(
                "normal demo allowlist does not match the source directory"
            )
        allowed.append(record)
    return tuple(
        sorted(
            allowed,
            key=lambda record: (
                _record_float(record, "replay_score"),
                _record_int(record, "rank"),
            ),
        )[:sample_size]
    )


def _canonical_hash(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def build_report(
    package: ValidatedNormalReference,
    direct: Mapping[str, object],
    records: Sequence[Mapping[str, object]],
    *,
    demo_sample_size: int,
) -> dict[str, object]:
    selected = select_internal_demo_records(records, sample_size=demo_sample_size)
    report: dict[str, object] = {
        "schema_version": "1.0.0",
        "report_kind": "E3_USER_SUPPLIED_NORMAL_REFERENCE_REPLAY",
        "created_at": datetime.now(UTC).isoformat(),
        "verdict": "NORMAL_REFERENCE_REPLAY_COMPLETED_WITH_SCOPE",
        "claim_boundary": {
            "allowed": [
                "frozen local E3 score distribution on the supplied directory",
                "internal synthetic/scenario demo case selection",
                "model-human disagreement demonstration",
            ],
            "not_supported": [
                "normal confirmation for any individual image",
                "formal accuracy, specificity, false-positive rate, or calibration",
                "independent annotation provenance or held-out split verification",
                "product qualification, customer performance, or public redistribution",
            ],
        },
        "source_directory": {
            "record_count": len(package.images),
            "user_asserted_label": "NORMAL",
            "annotation_provenance_status": "USER_STATEMENT_ONLY",
            "license_status": "NOT_PROVIDED",
            "total_image_bytes": package.total_image_bytes,
            "content_tree_sha256": package.content_tree_sha256,
            "raw_images_copied_to_repository": False,
        },
        "direct_e3_replay": {**dict(direct), "records": list(records)},
        "internal_demo_selection": {
            "method": "LOWEST_E3_SCORE_WITHIN_PIXEL_REVIEWED_INTERNAL_ONLY_ALLOWLIST",
            "reviewed_allowlist_ranks": list(SAFE_INTERNAL_DEMO_RANKS),
            "selected_count": len(selected),
            "records": list(selected),
            "rights_status": "INTERNAL_ONLY_RIGHTS_UNVERIFIED",
        },
        "safety": {
            "below_threshold_means_normal": False,
            "human_final_decision_required": True,
            "automatic_business_decision_performed": False,
            "live_external_action_performed": False,
            "raw_images_published": False,
        },
    }
    report["report_sha256"] = _canonical_hash(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vision-base-url", default="http://127.0.0.1:8093")
    parser.add_argument("--vision-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--demo-sample-size", type=int, default=4)
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        vision_base_url = local_base_url(arguments.vision_base_url, label="Vision replay")
        package = validate_normal_reference(arguments.source)
        direct, records = run_normal_reference_replay(
            package,
            vision_base_url=vision_base_url,
            api_key=os.getenv("VISION_E3_API_KEY", "").strip(),
            timeout_seconds=arguments.vision_timeout_seconds,
        )
        report = build_report(
            package,
            direct,
            records,
            demo_sample_size=arguments.demo_sample_size,
        )
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "verdict": report["verdict"],
                    "report": str(arguments.output),
                    "report_sha256": report["report_sha256"],
                    "direct_summary": direct["summary"],
                    "selected_normal_ranks": [
                        _record_int(record, "rank")
                        for record in cast(
                            Sequence[Mapping[str, object]],
                            cast(Mapping[str, object], report["internal_demo_selection"])[
                                "records"
                            ],
                        )
                    ],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        Top100ReplayFailure,
        NormalReferenceFailure,
    ) as error:
        print(f"Normal-reference E3 replay failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
