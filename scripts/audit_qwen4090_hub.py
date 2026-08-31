"""Audit frozen Qwen candidate revisions against Hugging Face Hub metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from app.platform.qwen4090_release import Qwen4090Candidate, Qwen4090CandidateMatrix
from scripts.verify_qwen4090_candidates import DEFAULT_MATRIX, load_matrix

DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
HUB_ORIGIN = "https://huggingface.co"


class HubCandidateAuditError(RuntimeError):
    """A pinned Hub revision is missing or does not match the reviewed matrix."""


HubFetcher = Callable[[str], Mapping[str, Any]]


def candidate_api_url(candidate: Qwen4090Candidate) -> str:
    """Build a fixed-origin Hub API URL from the schema-constrained repository ID."""

    owner, repository = candidate.artifact.artifact.split("/", 1)
    revision = candidate.artifact.artifact_revision
    return (
        f"{HUB_ORIGIN}/api/models/{quote(owner, safe='')}/{quote(repository, safe='')}"
        f"/revision/{quote(revision, safe='')}?blobs=true"
    )


def fetch_hub_json(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    maximum_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> Mapping[str, Any]:
    """Fetch one bounded Hub response without exposing an optional access token."""

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
        raise HubCandidateAuditError("Hub request escaped the fixed HTTPS origin")
    headers = {
        "Accept": "application/json",
        "User-Agent": "csight-qwen4090-hub-audit/1.0",
    }
    token = os.getenv("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout_seconds) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "huggingface.co":
            raise HubCandidateAuditError("Hub response redirected outside the fixed HTTPS origin")
        content = response.read(maximum_bytes + 1)
    if len(content) > maximum_bytes:
        raise HubCandidateAuditError("Hub response exceeded the bounded metadata size")
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HubCandidateAuditError("Hub returned invalid JSON metadata") from error
    if not isinstance(payload, dict):
        raise HubCandidateAuditError("Hub returned a non-object metadata record")
    return payload


def _safe_filename(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise HubCandidateAuditError("Hub sibling has an invalid filename")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise HubCandidateAuditError("Hub sibling filename escaped the repository")
    return value


def _weight_manifest(payload: Mapping[str, Any]) -> tuple[int, int, str]:
    siblings = payload.get("siblings")
    if not isinstance(siblings, list):
        raise HubCandidateAuditError("Hub metadata omitted the sibling inventory")
    rows: list[tuple[str, int, str]] = []
    for raw_sibling in siblings:
        if not isinstance(raw_sibling, dict):
            raise HubCandidateAuditError("Hub sibling inventory is malformed")
        filename = _safe_filename(raw_sibling.get("rfilename"))
        if not filename.endswith(".safetensors"):
            continue
        size = raw_sibling.get("size")
        lfs = raw_sibling.get("lfs")
        if not isinstance(size, int) or size <= 0 or not isinstance(lfs, dict):
            raise HubCandidateAuditError("Hub weight file omitted size or LFS identity")
        sha256 = lfs.get("sha256")
        lfs_size = lfs.get("size")
        if (
            not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
            or lfs_size != size
        ):
            raise HubCandidateAuditError("Hub weight file has invalid LFS metadata")
        rows.append((filename, size, sha256))
    if not rows:
        raise HubCandidateAuditError("Hub revision contains no safetensors weights")
    digest = hashlib.sha256()
    for filename, size, sha256 in sorted(rows):
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256.encode("ascii"))
        digest.update(b"\n")
    return len(rows), sum(row[1] for row in rows), "sha256:" + digest.hexdigest()


def audit_candidate(
    candidate: Qwen4090Candidate,
    payload: Mapping[str, Any],
) -> dict[str, object]:
    """Require exact revision, license, lineage, and weight-byte parity."""

    if payload.get("id") != candidate.artifact.artifact:
        raise HubCandidateAuditError("Hub repository identity does not match the matrix")
    if payload.get("sha") != candidate.artifact.artifact_revision:
        raise HubCandidateAuditError("Hub revision did not resolve to the exact matrix commit")
    tags = payload.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise HubCandidateAuditError("Hub tags are missing or malformed")
    normalized_license = candidate.artifact.license_identifier.casefold()
    if f"license:{normalized_license}" not in {tag.casefold() for tag in tags}:
        raise HubCandidateAuditError("Hub license does not match the matrix")
    base_artifact = candidate.artifact.base_artifact
    if base_artifact is not None:
        expected_lineage = {
            f"base_model:{base_artifact}",
            f"base_model:quantized:{base_artifact}",
        }
        if not expected_lineage.issubset(set(tags)):
            raise HubCandidateAuditError("Hub quantization lineage does not match the matrix")
    weight_file_count, weight_bytes, weight_manifest_digest = _weight_manifest(payload)
    if weight_bytes != candidate.artifact.weight_bytes:
        raise HubCandidateAuditError("Hub safetensors byte count does not match the matrix")
    return {
        "candidate_id": candidate.candidate_id,
        "artifact": candidate.artifact.artifact,
        "artifact_revision": candidate.artifact.artifact_revision,
        "source": candidate.artifact.source.value,
        "private": payload.get("private") is True,
        "gated": payload.get("gated", False),
        "pipeline_tag": payload.get("pipeline_tag"),
        "weight_file_count": weight_file_count,
        "weight_bytes": weight_bytes,
        "weight_manifest_digest": weight_manifest_digest,
        "status": "HUB_REVISION_VERIFIED",
    }


def audit_matrix(
    matrix: Qwen4090CandidateMatrix,
    *,
    fetcher: HubFetcher,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for candidate in matrix.candidates:
        try:
            results.append(audit_candidate(candidate, fetcher(candidate_api_url(candidate))))
        except (HubCandidateAuditError, OSError, ValueError) as error:
            failures.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "error": str(error),
                }
            )
    return {
        "schema_version": "qwen4090_hub_audit/1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "verified_candidates": results,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES)
    arguments = parser.parse_args()
    if arguments.timeout_seconds <= 0 or arguments.max_response_bytes <= 0:
        parser.error("timeout and maximum response bytes must be positive")

    try:
        matrix = load_matrix(arguments.matrix)
        report = audit_matrix(
            matrix,
            fetcher=lambda url: fetch_hub_json(
                url,
                timeout_seconds=arguments.timeout_seconds,
                maximum_bytes=arguments.max_response_bytes,
            ),
        )
    except (HubCandidateAuditError, OSError, ValueError) as error:
        report = {
            "schema_version": "qwen4090_hub_audit/1.0.0",
            "status": "FAIL",
            "verified_candidates": [],
            "failures": [{"candidate_id": "MATRIX", "error": str(error)}],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
