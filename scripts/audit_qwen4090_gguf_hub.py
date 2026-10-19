"""Audit exact CSight GGUF artifacts against bounded Hugging Face Hub metadata."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from app.platform.qwen4090_gguf import Qwen4090CandidateMatrixV2, Qwen4090GGUFCandidate
from scripts.verify_qwen4090_gguf_candidates import DEFAULT_MATRIX, load_gguf_matrix

HUB_ORIGIN = "https://huggingface.co"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class GGUFHubAuditError(RuntimeError):
    """A pinned GGUF Hub revision is absent or differs from its matrix identity."""


HubFetcher = Callable[[str], Mapping[str, Any]]


def candidate_api_url(candidate: Qwen4090GGUFCandidate) -> str:
    revision = candidate.artifact.artifact_revision
    if revision is None:
        raise GGUFHubAuditError("GGUF artifact revision is not pinned")
    owner, repository = candidate.artifact.artifact.split("/", 1)
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
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
        raise GGUFHubAuditError("Hub request escaped the fixed HTTPS origin")
    headers = {
        "Accept": "application/json",
        "User-Agent": "csight-qwen4090-gguf-hub-audit/2.0",
    }
    token = os.getenv("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout_seconds) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "huggingface.co":
            raise GGUFHubAuditError("Hub response redirected outside the fixed HTTPS origin")
        content = response.read(maximum_bytes + 1)
    if len(content) > maximum_bytes:
        raise GGUFHubAuditError("Hub response exceeded the bounded metadata size")
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GGUFHubAuditError("Hub returned invalid JSON metadata") from error
    if not isinstance(payload, dict):
        raise GGUFHubAuditError("Hub returned a non-object metadata record")
    return payload


def _exact_gguf(payload: Mapping[str, Any], filename: str) -> tuple[int, str]:
    path = PurePosixPath(filename)
    if path.is_absolute() or ".." in path.parts or path.name != filename:
        raise GGUFHubAuditError("matrix GGUF filename is not a repository-root filename")
    siblings = payload.get("siblings")
    if not isinstance(siblings, list):
        raise GGUFHubAuditError("Hub metadata omitted the sibling inventory")
    matches = [
        row for row in siblings if isinstance(row, dict) and row.get("rfilename") == filename
    ]
    if len(matches) != 1:
        raise GGUFHubAuditError("Hub revision does not contain the exact GGUF exactly once")
    row = matches[0]
    size = row.get("size")
    lfs = row.get("lfs")
    if not isinstance(size, int) or size <= 0 or not isinstance(lfs, dict):
        raise GGUFHubAuditError("GGUF sibling omitted size or LFS identity")
    sha256 = lfs.get("sha256")
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
        or lfs.get("size") != size
    ):
        raise GGUFHubAuditError("GGUF sibling has invalid LFS metadata")
    return size, "sha256:" + sha256


def audit_candidate(
    candidate: Qwen4090GGUFCandidate,
    payload: Mapping[str, Any],
) -> dict[str, object]:
    artifact = candidate.artifact
    if artifact.artifact_revision is None or artifact.artifact_content_digest is None:
        raise GGUFHubAuditError("GGUF artifact revision and content digest must be pinned")
    if artifact.weight_bytes is None:
        raise GGUFHubAuditError("GGUF byte size must be pinned")
    if payload.get("id") != artifact.artifact or payload.get("sha") != artifact.artifact_revision:
        raise GGUFHubAuditError("Hub repository or revision does not match the matrix")
    tags = payload.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise GGUFHubAuditError("Hub tags are missing or malformed")
    normalized_tags = {tag.casefold() for tag in tags}
    if f"license:{artifact.license_identifier}".casefold() not in normalized_tags:
        raise GGUFHubAuditError("Hub license does not match the matrix")
    required_lineage = {
        f"base_model:{artifact.upstream_model_artifact}".casefold(),
        f"base_model:quantized:{artifact.upstream_model_artifact}".casefold(),
    }
    if not required_lineage.issubset(normalized_tags):
        raise GGUFHubAuditError("Hub quantization lineage does not identify the BF16 base")
    weight_bytes, digest = _exact_gguf(payload, artifact.gguf_filename)
    if weight_bytes != artifact.weight_bytes or digest != artifact.artifact_content_digest:
        raise GGUFHubAuditError("Hub GGUF bytes or digest do not match the matrix")
    return {
        "candidate_id": candidate.candidate_id,
        "artifact": artifact.artifact,
        "artifact_revision": artifact.artifact_revision,
        "gguf_filename": artifact.gguf_filename,
        "weight_bytes": weight_bytes,
        "artifact_content_digest": digest,
        "status": "HUB_GGUF_VERIFIED",
    }


def audit_matrix(
    matrix: Qwen4090CandidateMatrixV2,
    *,
    fetcher: HubFetcher,
) -> dict[str, object]:
    verified: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for candidate in matrix.candidates:
        try:
            verified.append(audit_candidate(candidate, fetcher(candidate_api_url(candidate))))
        except (GGUFHubAuditError, OSError, ValueError) as error:
            failures.append({"candidate_id": candidate.candidate_id, "error": str(error)})
    return {
        "schema_version": "qwen4090_gguf_hub_audit/1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "verified_candidates": verified,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES)
    arguments = parser.parse_args()
    matrix = load_gguf_matrix(arguments.matrix)
    report = audit_matrix(
        matrix,
        fetcher=lambda url: fetch_hub_json(
            url,
            timeout_seconds=arguments.timeout_seconds,
            maximum_bytes=arguments.max_response_bytes,
        ),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
