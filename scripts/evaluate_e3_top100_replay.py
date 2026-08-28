"""Replay the selected-correct Kaputt Top-100 through real E3 and local CSight Core.

This is deliberately a positive-path integration replay, not an accuracy or product-
qualification evaluation. The source package contains only examples that E3 already
classified correctly at 0.5 and contains no normal examples.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError

from scripts.smoke_scenario_vision import (
    ScenarioVisionSmokeFailure,
    env_values,
    json_request,
    required_string,
)

EXPECTED_COLUMNS = (
    "rank",
    "copied_file",
    "capture_id",
    "defect",
    "major_defect",
    "defect_types",
    "item_material",
    "item_identifier",
    "defect_probability",
    "true_class_probability",
    "predicted_defect_at_0_5",
    "correct_at_0_5",
    "query_image",
    "image_sha256",
)
EXPECTED_COUNT = 100
EXPECTED_DIMENSIONS = (2048, 2048)
EXPECTED_MODEL_NAME = "csight-dinov2-vits14-kaputt-binary"
EXPECTED_MODEL_VERSION = "e3-epoch10-20260827"
EXPECTED_MODEL_REVISION = "49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e"
EXPECTED_THRESHOLD = 0.8984375
SOURCE_SELECTION_THRESHOLD = 0.5
VISION_TASK = "product_defect_any_defect_classification"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
SAFE_CORE_SAMPLE_RANKS = (3, 32, 54, 58, 78, 80)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ITEM_IDENTIFIER_PATTERN = re.compile(r"[0-9a-f]{8}")


class Top100ReplayFailure(RuntimeError):
    """A sanitized fail-closed error for the local replay."""


@dataclass(frozen=True)
class SourceRecord:
    rank: int
    copied_file: str
    capture_id: str
    defect: bool
    major_defect: bool
    defect_types: tuple[str, ...]
    item_material: str
    item_identifier: str
    defect_probability: float
    true_class_probability: float
    predicted_defect_at_0_5: bool
    correct_at_0_5: bool
    image_sha256: str


@dataclass(frozen=True)
class ValidatedPackage:
    root: Path
    records: tuple[SourceRecord, ...]
    total_image_bytes: int
    material_counts: Mapping[str, int]
    repeated_item_groups: Mapping[str, tuple[int, ...]]
    readme_sha256: str
    manifest_sha256: str
    summary_sha256: str
    content_tree_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest()


def _parse_bool(value: str, *, label: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise Top100ReplayFailure(f"{label} must be True or False")


def _parse_probability(value: str, *, label: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        raise Top100ReplayFailure(f"{label} is not numeric") from None
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        raise Top100ReplayFailure(f"{label} is outside [0, 1]")
    return parsed


def _regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise Top100ReplayFailure(f"{label} must be a regular non-symlink file")
    return path


def _source_record(raw: Mapping[str, str], *, expected_rank: int) -> SourceRecord:
    try:
        rank = int(raw["rank"])
    except (KeyError, ValueError):
        raise Top100ReplayFailure("manifest rank is invalid") from None
    if rank != expected_rank:
        raise Top100ReplayFailure("manifest ranks must be contiguous from 1")
    capture_id = raw["capture_id"]
    try:
        if str(UUID(capture_id)) != capture_id:
            raise ValueError
    except ValueError:
        raise Top100ReplayFailure(f"rank {rank} capture_id is not canonical UUID") from None
    expected_file = f"images/rank_{rank:03d}_{capture_id}.jpg"
    copied_file = raw["copied_file"]
    if copied_file != expected_file:
        raise Top100ReplayFailure(f"rank {rank} copied filename is not canonical")
    relative = PurePosixPath(copied_file)
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 2:
        raise Top100ReplayFailure(f"rank {rank} copied path is unsafe")
    if raw["query_image"] != f"data/test/query-data/image/{capture_id}.jpg":
        raise Top100ReplayFailure(f"rank {rank} query-image basename is inconsistent")
    image_sha256 = raw["image_sha256"]
    if SHA256_PATTERN.fullmatch(image_sha256) is None:
        raise Top100ReplayFailure(f"rank {rank} image SHA-256 is invalid")
    item_identifier = raw["item_identifier"]
    if ITEM_IDENTIFIER_PATTERN.fullmatch(item_identifier) is None:
        raise Top100ReplayFailure(f"rank {rank} item identifier is invalid")
    defect_types = tuple(part for part in raw["defect_types"].split(",") if part)
    if not defect_types:
        raise Top100ReplayFailure(f"rank {rank} omitted defect annotations")
    return SourceRecord(
        rank=rank,
        copied_file=copied_file,
        capture_id=capture_id,
        defect=_parse_bool(raw["defect"], label=f"rank {rank} defect"),
        major_defect=_parse_bool(raw["major_defect"], label=f"rank {rank} major_defect"),
        defect_types=defect_types,
        item_material=raw["item_material"],
        item_identifier=item_identifier,
        defect_probability=_parse_probability(
            raw["defect_probability"], label=f"rank {rank} defect_probability"
        ),
        true_class_probability=_parse_probability(
            raw["true_class_probability"], label=f"rank {rank} true_class_probability"
        ),
        predicted_defect_at_0_5=_parse_bool(
            raw["predicted_defect_at_0_5"], label=f"rank {rank} predicted_defect_at_0_5"
        ),
        correct_at_0_5=_parse_bool(raw["correct_at_0_5"], label=f"rank {rank} correct_at_0_5"),
        image_sha256=image_sha256,
    )


def validate_package(
    root: Path,
    *,
    expected_count: int = EXPECTED_COUNT,
    expected_dimensions: tuple[int, int] = EXPECTED_DIMENSIONS,
) -> ValidatedPackage:
    """Validate every source artifact without trusting package prose as instructions."""

    if root.is_symlink() or not root.is_dir():
        raise Top100ReplayFailure("source package must be a non-symlink directory")
    resolved_root = root.resolve(strict=True)
    readme_path = _regular_file(resolved_root / "README.md", label="README")
    manifest_path = _regular_file(resolved_root / "manifest.csv", label="manifest")
    summary_path = _regular_file(resolved_root / "summary.json", label="summary")
    image_directory = resolved_root / "images"
    if image_directory.is_symlink() or not image_directory.is_dir():
        raise Top100ReplayFailure("images must be a non-symlink directory")

    with manifest_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
            raise Top100ReplayFailure("manifest columns do not match the frozen package schema")
        raw_rows = [cast(Mapping[str, str], row) for row in reader]
    if len(raw_rows) != expected_count:
        raise Top100ReplayFailure(f"manifest must contain exactly {expected_count} records")
    records = tuple(
        _source_record(raw, expected_rank=index) for index, raw in enumerate(raw_rows, start=1)
    )
    if len({record.capture_id for record in records}) != expected_count:
        raise Top100ReplayFailure("capture identifiers are not unique")
    if len({record.image_sha256 for record in records}) != expected_count:
        raise Top100ReplayFailure("exact image hashes are not unique")
    if any(
        not record.defect
        or not record.predicted_defect_at_0_5
        or not record.correct_at_0_5
        or record.true_class_probability != record.defect_probability
        for record in records
    ):
        raise Top100ReplayFailure("package is not the declared selected-correct positive-only set")

    expected_image_names = {PurePosixPath(record.copied_file).name for record in records}
    actual_image_names = {path.name for path in image_directory.iterdir() if path.is_file()}
    if actual_image_names != expected_image_names:
        raise Top100ReplayFailure("images directory and manifest do not contain the same files")
    if any(path.is_dir() or path.is_symlink() for path in image_directory.iterdir()):
        raise Top100ReplayFailure("images directory contains an unexpected directory or symlink")

    total_image_bytes = 0
    for record in records:
        image_path = _regular_file(
            resolved_root / record.copied_file, label=f"rank {record.rank} image"
        )
        if image_path.resolve(strict=True).parent != image_directory.resolve(strict=True):
            raise Top100ReplayFailure(f"rank {record.rank} image escaped the package")
        size_bytes = image_path.stat().st_size
        if not 0 < size_bytes <= MAX_IMAGE_BYTES:
            raise Top100ReplayFailure(f"rank {record.rank} image size is invalid")
        total_image_bytes += size_bytes
        if _sha256_file(image_path) != record.image_sha256:
            raise Top100ReplayFailure(f"rank {record.rank} image SHA-256 mismatch")
        try:
            with Image.open(image_path) as image:
                image.verify()
            with Image.open(image_path) as image:
                image.load()
                if image.format != "JPEG" or image.mode != "RGB":
                    raise Top100ReplayFailure(f"rank {record.rank} image encoding is invalid")
                if image.size != expected_dimensions:
                    raise Top100ReplayFailure(f"rank {record.rank} image dimensions are invalid")
                if image.getexif() or image.info.get("icc_profile"):
                    raise Top100ReplayFailure(f"rank {record.rank} contains embedded metadata")
        except (OSError, UnidentifiedImageError):
            raise Top100ReplayFailure(f"rank {record.rank} image cannot be decoded") from None

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise Top100ReplayFailure("summary JSON is invalid") from None
    if not isinstance(summary, dict):
        raise Top100ReplayFailure("summary JSON must be an object")
    materials = Counter(record.item_material for record in records)
    expected_summary = {
        "count": expected_count,
        "defect_count": expected_count,
        "normal_count": 0,
        "minimum_true_class_probability": min(record.true_class_probability for record in records),
        "maximum_true_class_probability": max(record.true_class_probability for record in records),
        "total_image_bytes": total_image_bytes,
        "materials": dict(materials),
    }
    if summary != expected_summary:
        raise Top100ReplayFailure("summary does not match the validated manifest and images")

    item_ranks: dict[str, list[int]] = {}
    for record in records:
        item_ranks.setdefault(record.item_identifier, []).append(record.rank)
    repeated_item_groups = {
        identifier: tuple(ranks) for identifier, ranks in item_ranks.items() if len(ranks) > 1
    }
    return ValidatedPackage(
        root=resolved_root,
        records=records,
        total_image_bytes=total_image_bytes,
        material_counts=dict(materials),
        repeated_item_groups=repeated_item_groups,
        readme_sha256=_sha256_file(readme_path),
        manifest_sha256=_sha256_file(manifest_path),
        summary_sha256=_sha256_file(summary_path),
        content_tree_sha256=content_tree_sha256(resolved_root),
    )


def select_core_sample(
    records: Sequence[SourceRecord],
    *,
    sample_size: int,
) -> tuple[SourceRecord, ...]:
    """Select visually reviewed hard-plastic records that avoid known visible personal text."""

    if not 0 <= sample_size <= len(SAFE_CORE_SAMPLE_RANKS):
        raise Top100ReplayFailure(
            f"core sample size must be between 0 and {len(SAFE_CORE_SAMPLE_RANKS)}"
        )
    by_rank = {record.rank: record for record in records}
    selected: list[SourceRecord] = []
    for rank in SAFE_CORE_SAMPLE_RANKS[:sample_size]:
        record = by_rank.get(rank)
        if record is None or record.item_material != "plastic_hard" or not record.major_defect:
            raise Top100ReplayFailure("safe Core sample does not match the frozen source metadata")
        selected.append(record)
    return tuple(selected)


def request_json(request: Request, *, timeout_seconds: float) -> Mapping[str, object]:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise Top100ReplayFailure(f"Vision endpoint returned HTTP {error.code}") from None
    except (TimeoutError, URLError):
        raise Top100ReplayFailure("Vision endpoint could not be reached") from None
    if not isinstance(payload, dict):
        raise Top100ReplayFailure("Vision endpoint response was not a JSON object")
    return cast(Mapping[str, object], payload)


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise Top100ReplayFailure(f"response omitted {label}")
    return cast(Mapping[str, object], value)


def _records(value: object, *, label: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise Top100ReplayFailure(f"response omitted {label}")
    return cast(Sequence[Mapping[str, object]], value)


def multipart_image(
    *,
    field_name: str,
    filename: str,
    content_type: str,
    image_bytes: bytes,
    fields: Mapping[str, str],
) -> tuple[bytes, str]:
    boundary = f"csight-top100-{uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            )
        )
    chunks.extend(
        (
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            ).encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            image_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        )
    )
    return b"".join(chunks), boundary


def vision_headers(api_key: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def validate_runtime_identity(health: Mapping[str, object]) -> None:
    expected = {
        "status": "healthy",
        "model_name": EXPECTED_MODEL_NAME,
        "model_version": EXPECTED_MODEL_VERSION,
        "model_revision": EXPECTED_MODEL_REVISION,
        "task": VISION_TASK,
        "threshold": EXPECTED_THRESHOLD,
        "human_final_approval_required": True,
        "normal_confirmation_supported": False,
    }
    for key, value in expected.items():
        if health.get(key) != value:
            raise Top100ReplayFailure(f"Vision health identity mismatch: {key}")


def validate_vision_result(result: Mapping[str, object]) -> tuple[float, int]:
    provider = _mapping(result.get("provider"), label="provider")
    expected_provider = {
        "name": "remote_vision",
        "model_name": EXPECTED_MODEL_NAME,
        "model_version": EXPECTED_MODEL_VERSION,
        "model_revision": EXPECTED_MODEL_REVISION,
        "taxonomy_version": "kaputt-any-defect-binary-v1",
    }
    for key, value in expected_provider.items():
        if provider.get(key) != value:
            raise Top100ReplayFailure(f"Vision result identity mismatch: {key}")
    assessment = _mapping(result.get("image_assessment"), label="image_assessment")
    score = assessment.get("score")
    threshold = assessment.get("threshold")
    latency_ms = result.get("latency_ms")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise Top100ReplayFailure("Vision score is invalid")
    if threshold != EXPECTED_THRESHOLD:
        raise Top100ReplayFailure("Vision threshold is not the frozen E3 threshold")
    if assessment.get("label") != "defect" or result.get("detections") != []:
        raise Top100ReplayFailure("Vision result crossed the non-localizing binary boundary")
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, int) or latency_ms < 0:
        raise Top100ReplayFailure("Vision latency is invalid")
    normalized_score = float(score)
    if not math.isfinite(normalized_score) or not 0.0 <= normalized_score <= 1.0:
        raise Top100ReplayFailure("Vision score is outside [0, 1]")
    return normalized_score, latency_ms


def run_direct_replay(
    package: ValidatedPackage,
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
    replay_records: list[Mapping[str, object]] = []
    for source in package.records:
        image_bytes = (package.root / source.copied_file).read_bytes()
        body, boundary = multipart_image(
            field_name="file",
            filename=f"rank-{source.rank:03d}.jpg",
            content_type="image/jpeg",
            image_bytes=image_bytes,
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
        replay_records.append(
            {
                "rank": source.rank,
                "capture_id": source.capture_id,
                "image_sha256": source.image_sha256,
                "item_identifier": source.item_identifier,
                "material_annotation": source.item_material,
                "major_defect_annotation": source.major_defect,
                "defect_type_annotations_not_model_predictions": list(source.defect_types),
                "source_reported_defect_probability": source.defect_probability,
                "replay_score": score,
                "correct_at_source_threshold_0_5": score >= SOURCE_SELECTION_THRESHOLD,
                "high_confidence_defect_candidate": high_confidence,
                "outcome": (
                    "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
                    if high_confidence
                    else "BELOW_HIGH_CONFIDENCE_THRESHOLD"
                ),
                "model_latency_ms": latency_ms,
            }
        )
    scores = [cast(float, record["replay_score"]) for record in replay_records]
    latencies = [cast(int, record["model_latency_ms"]) for record in replay_records]
    correct_count = sum(
        bool(record["correct_at_source_threshold_0_5"]) for record in replay_records
    )
    high_confidence_count = sum(
        bool(record["high_confidence_defect_candidate"]) for record in replay_records
    )
    summary: Mapping[str, object] = {
        "verdict": (
            "SELECTED_CORRECT_POSITIVE_REPLAY_PASS"
            if correct_count == len(replay_records)
            else "SELECTED_CORRECT_POSITIVE_REPLAY_MISMATCH"
        ),
        "attempted_count": len(replay_records),
        "completed_count": len(replay_records),
        "correct_at_source_threshold_0_5_count": correct_count,
        "high_confidence_candidate_count_at_frozen_threshold": high_confidence_count,
        "minimum_score": min(scores),
        "median_score": statistics.median(scores),
        "mean_score": statistics.fmean(scores),
        "maximum_score": max(scores),
        "minimum_model_latency_ms": min(latencies),
        "median_model_latency_ms": statistics.median(latencies),
        "maximum_model_latency_ms": max(latencies),
    }
    return {"health": dict(health), "summary": dict(summary)}, tuple(replay_records)


def _upload_core_image(
    *,
    url: str,
    authorization: Mapping[str, str],
    image_bytes: bytes,
    rank: int,
) -> Mapping[str, object]:
    body, boundary = multipart_image(
        field_name="file",
        filename=f"top100-rank-{rank:03d}.jpg",
        content_type="image/jpeg",
        image_bytes=image_bytes,
        fields={"evidence_type": "IMAGE"},
    )
    try:
        with urlopen(
            Request(
                url,
                data=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    **dict(authorization),
                },
                method="POST",
            ),
            timeout=30,
        ) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise Top100ReplayFailure(f"Core evidence upload returned HTTP {error.code}") from None
    except (TimeoutError, URLError):
        raise Top100ReplayFailure("local CSight Core could not be reached") from None
    if status != 201 or not isinstance(payload, dict):
        raise Top100ReplayFailure("Core evidence upload response was invalid")
    return cast(Mapping[str, object], payload)


def _validate_core_vision_result(
    result: Mapping[str, object], *, expected_score: float
) -> tuple[float, str]:
    expected_identity = {
        "model_name": EXPECTED_MODEL_NAME,
        "model_version": EXPECTED_MODEL_VERSION,
        "model_revision": EXPECTED_MODEL_REVISION,
    }
    for key, value in expected_identity.items():
        if result.get(key) != value:
            raise Top100ReplayFailure(f"Core-persisted Vision identity mismatch: {key}")
    assessment = _mapping(result.get("image_assessment"), label="Core image_assessment")
    detections = _records(result.get("detections"), label="Core detections")
    score = assessment.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise Top100ReplayFailure("Core-persisted Vision score is invalid")
    normalized_score = float(score)
    if abs(normalized_score - expected_score) > 1e-6:
        raise Top100ReplayFailure("direct E3 and Core-persisted scores do not reproduce")
    if assessment.get("assessment_type") != "ANY_DEFECT":
        raise Top100ReplayFailure("Core assessment type is not ANY_DEFECT")
    if assessment.get("threshold") != EXPECTED_THRESHOLD or detections:
        raise Top100ReplayFailure("Core result crossed the binary non-localizing boundary")
    expected_outcome = (
        "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
        if normalized_score >= EXPECTED_THRESHOLD
        else "BELOW_HIGH_CONFIDENCE_THRESHOLD"
    )
    if assessment.get("outcome") != expected_outcome:
        raise Top100ReplayFailure("Core assessment outcome is inconsistent")
    return normalized_score, expected_outcome


def run_core_sample(
    package: ValidatedPackage,
    direct_records: Sequence[Mapping[str, object]],
    *,
    core_base_url: str,
    tenant_slug: str,
    reviewer_email: str,
    reviewer_password: str,
    sample_size: int,
    timeout_seconds: float,
) -> Mapping[str, object]:
    selected = select_core_sample(package.records, sample_size=sample_size)
    if not selected:
        return {"verdict": "CORE_SAMPLE_NOT_REQUESTED", "records": []}
    _, token_response = json_request(
        method="POST",
        url=f"{core_base_url}/api/v1/auth/token",
        body={
            "tenant_slug": tenant_slug,
            "email": reviewer_email,
            "password": reviewer_password,
        },
        expected=frozenset({200}),
    )
    authorization = {"Authorization": f"Bearer {required_string(token_response, 'access_token')}"}
    direct_by_rank: dict[int, Mapping[str, object]] = {}
    for record in direct_records:
        rank = record.get("rank")
        if isinstance(rank, bool) or not isinstance(rank, int):
            raise Top100ReplayFailure("direct replay rank is invalid")
        direct_by_rank[rank] = record
    run_suffix = f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    core_records: list[Mapping[str, object]] = []
    for source in selected:
        _, created = json_request(
            method="POST",
            url=f"{core_base_url}/api/v1/cases",
            headers={
                **authorization,
                "Idempotency-Key": f"top100-e3-case-{run_suffix}-{source.rank:03d}",
            },
            body={
                "order_ref": f"TOP100-E3-{run_suffix}-{source.rank:03d}",
                "product_ref": "KAPUTT-PLASTIC-HARD-PROXY",
                "customer_message": (
                    "내부 시뮬레이션 데이터입니다. 제공된 상품 이미지의 결함 가능성을 "
                    "검토해 주세요. 이미지 분석은 참고용이며 최종 판단은 상담원이 수행합니다."
                ),
                "requested_action": "UNSPECIFIED",
                "attributes": {
                    "top100_e3_replay": {
                        "schema_version": "1.0",
                        "source_scope": "KAPUTT_SELECTED_CORRECT_HELD_OUT_CLAIM",
                        "source_package_content_tree_sha256": package.content_tree_sha256,
                        "source_rank": source.rank,
                        "source_capture_id": source.capture_id,
                        "source_image_sha256": source.image_sha256,
                        "source_material_annotation": source.item_material,
                        "source_defect_annotations_not_model_predictions": list(
                            source.defect_types
                        ),
                        "selection_bias": "POSITIVE_ONLY_CORRECT_ONLY_HIGH_CONFIDENCE",
                    }
                },
            },
            expected=frozenset({201}),
        )
        case_id = required_string(created, "case_id")
        evidence = _upload_core_image(
            url=f"{core_base_url}/api/v1/cases/{case_id}/evidence",
            authorization=authorization,
            image_bytes=(package.root / source.copied_file).read_bytes(),
            rank=source.rank,
        )
        evidence_id = required_string(evidence, "evidence_id")
        if evidence.get("sha256") != source.image_sha256:
            raise Top100ReplayFailure("Core Evidence SHA-256 does not match the source image")
        analysis_url = f"{core_base_url}/api/v1/cases/{case_id}/analysis-runs"
        _, started = json_request(
            method="POST",
            url=analysis_url,
            headers={
                **authorization,
                "Idempotency-Key": f"top100-e3-run-{run_suffix}-{source.rank:03d}",
            },
            body={
                "pipeline": "product_defect_multimodal_analysis",
                "pipeline_version": "1.0.0",
            },
            expected=frozenset({202}),
        )
        analysis_run_id = required_string(started, "analysis_run_id")
        deadline = time.monotonic() + timeout_seconds
        detail: Mapping[str, object] = {}
        status = "UNKNOWN"
        while time.monotonic() < deadline:
            _, detail = json_request(
                method="GET",
                url=f"{analysis_url}/{analysis_run_id}",
                headers=authorization,
                expected=frozenset({200}),
            )
            run = _mapping(detail.get("run"), label="Core run")
            raw_status = run.get("status")
            status = raw_status if isinstance(raw_status, str) else "UNKNOWN"
            if status in {"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"}:
                break
            time.sleep(0.5)
        else:
            raise Top100ReplayFailure(f"Core rank {source.rank} run timed out")
        if status != "SUCCEEDED":
            raise Top100ReplayFailure(f"Core rank {source.rank} run finished as {status}")
        vision_records = _records(detail.get("vision_results"), label="Core vision_results")
        if len(vision_records) != 1:
            raise Top100ReplayFailure("Core did not persist exactly one Vision result")
        persisted_result = _mapping(vision_records[0].get("result"), label="Core Vision result")
        direct_score = direct_by_rank[source.rank].get("replay_score")
        if isinstance(direct_score, bool) or not isinstance(direct_score, (int, float)):
            raise Top100ReplayFailure("direct replay score is invalid")
        score, outcome = _validate_core_vision_result(
            persisted_result, expected_score=float(direct_score)
        )
        core_records.append(
            {
                "rank": source.rank,
                "capture_id": source.capture_id,
                "case_id": case_id,
                "evidence_id": evidence_id,
                "analysis_run_id": analysis_run_id,
                "console_path": f"/cases/{case_id}",
                "run_status": status,
                "source_material_annotation": source.item_material,
                "score": score,
                "outcome": outcome,
                "localized_detection_count": 0,
                "automatic_decision_performed": False,
                "external_action_performed": False,
            }
        )
    return {
        "verdict": "REAL_E3_CORE_SELECTED_SAMPLE_PASS",
        "attempted_count": len(selected),
        "completed_count": len(core_records),
        "selection": {
            "method": "VISUALLY_REVIEWED_HARD_PLASTIC_ALLOWLIST",
            "allowed_ranks": list(SAFE_CORE_SAMPLE_RANKS),
            "known_visible_personal_text_excluded_rank": 61,
        },
        "records": core_records,
    }


def _canonical_hash(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def build_report(
    package: ValidatedPackage,
    direct: Mapping[str, object],
    direct_records: Sequence[Mapping[str, object]],
    core: Mapping[str, object],
) -> dict[str, object]:
    summary = _mapping(direct.get("summary"), label="direct summary")
    core_verdict = core.get("verdict")
    passed = summary.get("verdict") == "SELECTED_CORRECT_POSITIVE_REPLAY_PASS" and core_verdict in {
        "REAL_E3_CORE_SELECTED_SAMPLE_PASS",
        "CORE_SAMPLE_NOT_REQUESTED",
    }
    report: dict[str, object] = {
        "schema_version": "1.0.0",
        "report_kind": "E3_SELECTED_CORRECT_POSITIVE_REPLAY",
        "created_at": datetime.now(UTC).isoformat(),
        "verdict": (
            "TOP100_SELECTED_SUCCESS_REPLAY_AND_CORE_SAMPLE_PASS"
            if passed and core_verdict == "REAL_E3_CORE_SELECTED_SAMPLE_PASS"
            else "TOP100_SELECTED_SUCCESS_REPLAY_PASS"
            if passed
            else "TOP100_SELECTED_SUCCESS_REPLAY_FAILED"
        ),
        "claim_boundary": {
            "allowed": [
                "selected known-positive happy-path E3 replay",
                "real checkpoint HTTP and Core persistence integration evidence",
                "internal synthetic/scenario PoC evidence",
            ],
            "not_supported": [
                "accuracy, recall, specificity, false-positive rate, or calibration",
                "normal-item confirmation",
                "defect-type prediction, localization, bbox, or segmentation",
                "product qualification, customer performance, ROI, or Limited PoC promotion",
                "public redistribution or public image gallery",
            ],
            "selection_bias": "100 DEFECT / 0 NORMAL; E3-CORRECT-ONLY; REPORTED SCORE 1.0",
        },
        "source_package": {
            "record_count": len(package.records),
            "defect_count": len(package.records),
            "normal_count": 0,
            "hard_plastic_count": package.material_counts.get("plastic_hard", 0),
            "hard_plastic_major_defect_count": sum(
                record.item_material == "plastic_hard" and record.major_defect
                for record in package.records
            ),
            "total_image_bytes": package.total_image_bytes,
            "materials": dict(package.material_counts),
            "repeated_item_groups": {
                key: list(value) for key, value in package.repeated_item_groups.items()
            },
            "readme_sha256": package.readme_sha256,
            "manifest_sha256": package.manifest_sha256,
            "summary_sha256": package.summary_sha256,
            "content_tree_sha256": package.content_tree_sha256,
            "license_status": "NOT_PROVIDED_IN_SOURCE_PACKAGE",
            "annotation_provenance_status": "NOT_PROVIDED_IN_SOURCE_PACKAGE",
            "held_out_top100_claim_independently_reproduced": False,
            "raw_images_copied_to_repository": False,
        },
        "direct_e3_replay": {
            **dict(direct),
            "records": list(direct_records),
        },
        "core_poc_sample": dict(core),
        "safety": {
            "human_final_decision_required": True,
            "normal_confirmation_performed": False,
            "automatic_business_decision_performed": False,
            "live_external_action_performed": False,
            "raw_images_published": False,
        },
    }
    report["report_sha256"] = _canonical_hash(report)
    return report


def local_base_url(value: str, *, label: str) -> str:
    normalized = value.rstrip("/")
    if not normalized.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise Top100ReplayFailure(f"{label} accepts only a loopback HTTP URL")
    return normalized


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vision-base-url", default="http://127.0.0.1:8093")
    parser.add_argument("--vision-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--core-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--core-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--core-sample-size", type=int, default=0)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--tenant-slug", default="csight-demo")
    parser.add_argument("--reviewer-email", default="reviewer@csight.demo")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        vision_base_url = local_base_url(arguments.vision_base_url, label="Vision replay")
        core_base_url = local_base_url(arguments.core_base_url, label="Core replay")
        package = validate_package(arguments.package)
        direct, direct_records = run_direct_replay(
            package,
            vision_base_url=vision_base_url,
            api_key=os.getenv("VISION_E3_API_KEY", "").strip(),
            timeout_seconds=arguments.vision_timeout_seconds,
        )
        reviewer_password = ""
        if arguments.core_sample_size:
            reviewer_password = env_values(arguments.env_file).get(
                "DEVELOPMENT_SEED_REVIEWER_PASSWORD", ""
            )
            if len(reviewer_password) < 12:
                raise Top100ReplayFailure(
                    "DEVELOPMENT_SEED_REVIEWER_PASSWORD is required for the Core sample"
                )
        core = run_core_sample(
            package,
            direct_records,
            core_base_url=core_base_url,
            tenant_slug=arguments.tenant_slug,
            reviewer_email=arguments.reviewer_email,
            reviewer_password=reviewer_password,
            sample_size=arguments.core_sample_size,
            timeout_seconds=arguments.core_timeout_seconds,
        )
        report = build_report(package, direct, direct_records, core)
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
                    "source_package_content_tree_sha256": package.content_tree_sha256,
                    "direct_summary": direct["summary"],
                    "core_verdict": core["verdict"],
                    "core_case_count": len(cast(Sequence[object], core.get("records", []))),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if not str(report["verdict"]).endswith("FAILED") else 1
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        ScenarioVisionSmokeFailure,
        Top100ReplayFailure,
    ) as error:
        print(f"Top-100 E3 replay failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
