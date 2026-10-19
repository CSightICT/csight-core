"""Exact-file Hub audit for CSight-owned GGUF artifacts."""

import pytest

from scripts.audit_qwen4090_gguf_hub import (
    GGUFHubAuditError,
    audit_candidate,
    candidate_api_url,
)
from scripts.verify_qwen4090_gguf_candidates import DEFAULT_MATRIX, load_gguf_matrix

pytestmark = pytest.mark.unit


def _pinned_candidate():
    candidate = load_gguf_matrix(DEFAULT_MATRIX).candidates[0]
    return candidate.model_copy(
        update={
            "artifact": candidate.artifact.model_copy(
                update={
                    "artifact_revision": "1" * 40,
                    "artifact_content_digest": "sha256:" + "a" * 64,
                    "weight_bytes": 1234,
                }
            )
        }
    )


def test_hub_audit_requires_exact_root_gguf_lfs_identity() -> None:
    candidate = _pinned_candidate()
    payload = {
        "id": candidate.artifact.artifact,
        "sha": candidate.artifact.artifact_revision,
        "tags": [
            "license:apache-2.0",
            f"base_model:{candidate.artifact.upstream_model_artifact}",
            f"base_model:quantized:{candidate.artifact.upstream_model_artifact}",
        ],
        "siblings": [
            {
                "rfilename": candidate.artifact.gguf_filename,
                "size": 1234,
                "lfs": {"size": 1234, "sha256": "a" * 64},
            }
        ],
    }

    result = audit_candidate(candidate, payload)

    assert result["status"] == "HUB_GGUF_VERIFIED"
    assert "huggingface.co/api/models/" in candidate_api_url(candidate)


def test_hub_audit_fails_closed_for_unpinned_or_wrong_gguf() -> None:
    candidate = load_gguf_matrix(DEFAULT_MATRIX).candidates[0]
    with pytest.raises(GGUFHubAuditError, match="not pinned"):
        candidate_api_url(candidate)

    pinned = _pinned_candidate()
    with pytest.raises(GGUFHubAuditError, match="exact GGUF"):
        audit_candidate(
            pinned,
            {
                "id": pinned.artifact.artifact,
                "sha": pinned.artifact.artifact_revision,
                "tags": [
                    "license:apache-2.0",
                    f"base_model:{pinned.artifact.upstream_model_artifact}",
                    f"base_model:quantized:{pinned.artifact.upstream_model_artifact}",
                ],
                "siblings": [],
            },
        )
