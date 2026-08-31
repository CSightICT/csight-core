"""Offline tests for the bounded Hugging Face candidate audit."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from app.platform.qwen4090_release import Qwen4090Candidate
from scripts.audit_qwen4090_hub import (
    HubCandidateAuditError,
    audit_candidate,
    audit_matrix,
    candidate_api_url,
)
from scripts.verify_qwen4090_candidates import DEFAULT_MATRIX, load_matrix

pytestmark = pytest.mark.unit


def _candidate() -> Qwen4090Candidate:
    return load_matrix(DEFAULT_MATRIX).candidates[2]


def _payload(candidate: Qwen4090Candidate, **updates: object) -> dict[str, Any]:
    tags = [f"license:{candidate.artifact.license_identifier.casefold()}"]
    if candidate.artifact.base_artifact is not None:
        tags.extend(
            [
                f"base_model:{candidate.artifact.base_artifact}",
                f"base_model:quantized:{candidate.artifact.base_artifact}",
            ]
        )
    payload: dict[str, Any] = {
        "id": candidate.artifact.artifact,
        "sha": candidate.artifact.artifact_revision,
        "private": False,
        "gated": False,
        "pipeline_tag": "image-text-to-text",
        "tags": tags,
        "siblings": [
            {
                "rfilename": "model-00001-of-00001.safetensors",
                "size": candidate.artifact.weight_bytes,
                "lfs": {
                    "sha256": "a" * 64,
                    "size": candidate.artifact.weight_bytes,
                },
            },
            {"rfilename": "config.json", "size": 10},
        ],
    }
    payload.update(updates)
    return payload


def test_candidate_audit_accepts_exact_revision_lineage_and_weight_bytes() -> None:
    candidate = _candidate()

    report = audit_candidate(candidate, _payload(candidate))

    assert report["status"] == "HUB_REVISION_VERIFIED"
    assert report["weight_bytes"] == candidate.artifact.weight_bytes
    assert str(report["weight_manifest_digest"]).startswith("sha256:")
    assert candidate_api_url(candidate).startswith("https://huggingface.co/api/models/")


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"sha": "0" * 40}, "exact matrix commit"),
        ({"tags": ["license:apache-2.0"]}, "lineage"),
        (
            {
                "siblings": [
                    {
                        "rfilename": "../model.safetensors",
                        "size": 1,
                        "lfs": {"sha256": "a" * 64, "size": 1},
                    }
                ]
            },
            "escaped",
        ),
    ],
)
def test_candidate_audit_fails_closed_on_upstream_drift(
    updates: dict[str, object],
    message: str,
) -> None:
    candidate = _candidate()

    with pytest.raises(HubCandidateAuditError, match=message):
        audit_candidate(candidate, _payload(candidate, **updates))


def test_matrix_audit_reports_each_candidate_failure_without_hiding_the_rest() -> None:
    matrix = load_matrix(DEFAULT_MATRIX)
    payloads: dict[str, Mapping[str, Any]] = {
        candidate_api_url(candidate): _payload(candidate) for candidate in matrix.candidates
    }
    failed_candidate = matrix.candidates[-1]
    payloads[candidate_api_url(failed_candidate)] = _payload(
        failed_candidate,
        sha="0" * 40,
    )

    def fetcher(url: str) -> Mapping[str, Any]:
        return payloads[url]

    report = audit_matrix(matrix, fetcher=fetcher)

    assert report["status"] == "FAIL"
    verified_candidates = report["verified_candidates"]
    assert isinstance(verified_candidates, list)
    assert len(verified_candidates) == len(matrix.candidates) - 1
    assert report["failures"] == [
        {
            "candidate_id": failed_candidate.candidate_id,
            "error": "Hub revision did not resolve to the exact matrix commit",
        }
    ]
