"""Private HTTP adapter for the host-native Qwen3 reranker service."""

from __future__ import annotations

import json

import urllib3
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from urllib3 import Timeout
from urllib3.exceptions import HTTPError

from app.platform.reranking import (
    PolicyRerankRequest,
    PolicyRerankResult,
    RerankerProviderInvalidResponseError,
    RerankerProviderUnavailableError,
    RerankScore,
    validate_rerank_result,
)

MODEL_ALIAS = "csight-qwen3-reranker-0.6b"


class _Result(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    original_rank: int = Field(gt=0)
    rerank_rank: int = Field(gt=0)
    rerank_score: float


class _Response(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model: str
    model_revision: str
    profile_version: str
    results: tuple[_Result, ...]
    latency_ms: float = Field(ge=0)


class RemoteQwenRerankerAdapter:
    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._pool = urllib3.PoolManager(cert_reqs="CERT_REQUIRED")

    def rerank(self, request: PolicyRerankRequest) -> PolicyRerankResult:
        try:
            response = self._pool.request(
                "POST",
                f"{self._base_url}/v1/rerank",
                body=json.dumps(
                    {
                        "model": MODEL_ALIAS,
                        "query": request.query,
                        "documents": [
                            {"candidate_id": value.candidate_id, "text": value.text}
                            for value in request.candidates
                        ],
                        # Return every score so Core can enforce candidate-set invariance.
                        "top_n": len(request.candidates),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=Timeout(connect=min(5.0, self._timeout), read=self._timeout),
                retries=False,
            )
        except (HTTPError, OSError, ValueError) as error:
            raise RerankerProviderUnavailableError() from error
        if response.status == 429 or response.status >= 500:
            raise RerankerProviderUnavailableError()
        if not 200 <= response.status < 300:
            raise RerankerProviderInvalidResponseError()
        try:
            parsed = _Response.model_validate_json(response.data)
            if (
                parsed.model != MODEL_ALIAS
                or parsed.model_revision != request.profile.model_revision
                or parsed.profile_version != request.profile.profile_version
            ):
                raise RerankerProviderInvalidResponseError("Reranker model identity mismatch.")
            result = PolicyRerankResult(
                model=parsed.model,
                model_revision=parsed.model_revision,
                profile_version=parsed.profile_version,
                scores=tuple(
                    RerankScore(
                        candidate_id=value.candidate_id,
                        original_rank=value.original_rank,
                        rerank_rank=value.rerank_rank,
                        rerank_score=value.rerank_score,
                    )
                    for value in parsed.results
                ),
                latency_ms=parsed.latency_ms,
            )
        except (ValidationError, ValueError) as error:
            if isinstance(error, RerankerProviderInvalidResponseError):
                raise
            raise RerankerProviderInvalidResponseError() from error
        validate_rerank_result(request=request, result=result)
        return result


__all__ = ["RemoteQwenRerankerAdapter"]
