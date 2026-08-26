"""Deterministic mock policy reranker with explicit provider failure modes."""

from __future__ import annotations

import hashlib

from app.platform.reranking import (
    MockRerankerMode,
    PolicyRerankRequest,
    PolicyRerankResult,
    RerankerProviderInvalidResponseError,
    RerankerProviderUnavailableError,
    RerankScore,
)


class MockPolicyRerankerAdapter:
    def __init__(self, mode: MockRerankerMode = MockRerankerMode.SUCCESS) -> None:
        self._mode = mode

    def rerank(self, request: PolicyRerankRequest) -> PolicyRerankResult:
        if self._mode in {MockRerankerMode.TIMEOUT, MockRerankerMode.TRANSIENT_ERROR}:
            raise RerankerProviderUnavailableError()
        if self._mode in {
            MockRerankerMode.PERMANENT_ERROR,
            MockRerankerMode.INVALID_RESPONSE,
        }:
            raise RerankerProviderInvalidResponseError()
        ranked = sorted(
            request.candidates,
            key=lambda value: (
                -self._score(request.query, value.candidate_id),
                value.original_rank,
                value.candidate_id,
            ),
        )
        scores = [
            RerankScore(
                candidate_id=value.candidate_id,
                original_rank=value.original_rank,
                rerank_rank=rank,
                rerank_score=self._score(request.query, value.candidate_id),
            )
            for rank, value in enumerate(ranked, start=1)
        ]
        if self._mode is MockRerankerMode.DUPLICATE_CANDIDATE:
            scores[-1] = scores[0].model_copy(update={"rerank_rank": len(scores)})
        elif self._mode is MockRerankerMode.UNKNOWN_CANDIDATE:
            scores[-1] = scores[-1].model_copy(update={"candidate_id": "unknown-candidate"})
        return PolicyRerankResult(
            model="csight-mock-reranker",
            model_revision="mock-reranker-v1",
            profile_version=request.profile.profile_version,
            scores=tuple(scores),
            latency_ms=0.0,
        )

    @staticmethod
    def _score(query: str, candidate_id: str) -> float:
        digest = hashlib.sha256(f"{query}\0{candidate_id}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)


__all__ = ["MockPolicyRerankerAdapter"]
