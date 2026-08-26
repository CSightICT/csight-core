"""Contract tests for remote reranker failure normalization and allowlist validation."""

import json
from typing import Any, cast

import pytest

from app.adapters.reranking.remote import RemoteQwenRerankerAdapter
from app.platform.reranking import (
    PolicyRerankerProfile,
    PolicyRerankRequest,
    RerankCandidate,
    RerankerProviderInvalidResponseError,
    RerankerProviderUnavailableError,
)

pytestmark = pytest.mark.contract


def _profile() -> PolicyRerankerProfile:
    return PolicyRerankerProfile(
        provider_name="host_transformers",
        model_artifact="Qwen/Qwen3-Reranker-0.6B",
        model_revision="revision",
        instruction="retrieve",
        instruction_hash="a" * 64,
        query_template_hash="b" * 64,
        document_template_hash="c" * 64,
        max_query_tokens=10,
        max_document_tokens=10,
        max_pair_tokens=20,
        candidate_k=20,
        final_k=10,
        batch_size=8,
        device="mps",
        score_semantics="pairwise relevance",
    )


def _request() -> PolicyRerankRequest:
    return PolicyRerankRequest(
        query="query",
        candidates=(
            RerankCandidate(candidate_id="a", text="a", original_rank=1),
            RerankCandidate(candidate_id="b", text="b", original_rank=2),
        ),
        profile=_profile(),
    )


class _Response:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self.data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")


class _Pool:
    def __init__(self, response: _Response) -> None:
        self.response = response

    def request(self, *_: object, **__: object) -> _Response:
        return self.response


def _adapter(response: _Response) -> RemoteQwenRerankerAdapter:
    adapter = RemoteQwenRerankerAdapter(base_url="http://127.0.0.1:8092")
    cast(Any, adapter)._pool = _Pool(response)
    return adapter


def _payload() -> dict[str, Any]:
    return {
        "model": "csight-qwen3-reranker-0.6b",
        "model_revision": "revision",
        "profile_version": "1.0.0",
        "latency_ms": 1,
        "results": [
            {"candidate_id": "b", "original_rank": 2, "rerank_rank": 1, "rerank_score": 0.9},
            {"candidate_id": "a", "original_rank": 1, "rerank_rank": 2, "rerank_score": 0.1},
        ],
    }


def test_remote_success_preserves_complete_candidate_set() -> None:
    result = _adapter(_Response(200, _payload())).rerank(_request())
    assert [value.candidate_id for value in result.scores] == ["b", "a"]


@pytest.mark.parametrize("status", (429, 500))
def test_remote_transient_status_is_unavailable(status: int) -> None:
    with pytest.raises(RerankerProviderUnavailableError):
        _adapter(_Response(status, {})).rerank(_request())


@pytest.mark.parametrize(
    "response",
    (
        _Response(400, {}),
        _Response(200, b"not-json"),
        _Response(200, {**_payload(), "model_revision": "wrong"}),
        _Response(200, {**_payload(), "results": _payload()["results"][:1]}),
        _Response(
            200,
            {
                **_payload(),
                "results": [
                    _payload()["results"][0],
                    {
                        "candidate_id": "unknown",
                        "original_rank": 1,
                        "rerank_rank": 2,
                        "rerank_score": 0.1,
                    },
                ],
            },
        ),
        _Response(
            200,
            {
                **_payload(),
                "results": [_payload()["results"][0], _payload()["results"][0]],
            },
        ),
        _Response(
            200,
            {
                **_payload(),
                "results": [
                    _payload()["results"][0],
                    {
                        "candidate_id": "a",
                        "original_rank": 1,
                        "rerank_rank": 2,
                        "rerank_score": float("nan"),
                    },
                ],
            },
        ),
    ),
)
def test_remote_invalid_contract_is_fail_closed(response: _Response) -> None:
    with pytest.raises(RerankerProviderInvalidResponseError):
        _adapter(response).rerank(_request())
