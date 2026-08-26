"""Private HTTP adapter for the host-native embedding service."""

from __future__ import annotations

import json
from collections.abc import Sequence

import urllib3
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from urllib3 import Timeout
from urllib3.exceptions import HTTPError

from app.platform.policy_retrieval import (
    DenseProfile,
    EmbeddingProviderUnavailableError,
    EmbeddingVector,
)


class _EmbeddingItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int = Field(ge=0)
    embedding: tuple[float, ...]
    token_count: int | None = Field(default=None, ge=0)
    truncated: bool = False


class _EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model: str
    model_revision: str
    dimension: int = Field(gt=0)
    normalized: bool
    data: tuple[_EmbeddingItem, ...]


class HTTPEmbeddingProvider:
    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._pool = urllib3.PoolManager(cert_reqs="CERT_REQUIRED")

    def embed_query(self, value: str, profile: DenseProfile) -> EmbeddingVector:
        return self._embed((value,), input_type="query", profile=profile)[0]

    def embed_documents(
        self, values: Sequence[str], profile: DenseProfile
    ) -> tuple[EmbeddingVector, ...]:
        return self._embed(tuple(values), input_type="document", profile=profile)

    def _embed(
        self, values: tuple[str, ...], *, input_type: str, profile: DenseProfile
    ) -> tuple[EmbeddingVector, ...]:
        try:
            response = self._pool.request(
                "POST",
                f"{self._base_url}/v1/embeddings",
                body=json.dumps(
                    {
                        "model": "csight-qwen3-embedding-0.6b",
                        "input": values,
                        "input_type": input_type,
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=Timeout(connect=min(5.0, self._timeout), read=self._timeout),
                retries=False,
            )
            if not 200 <= response.status < 300:
                raise HTTPError("embedding provider returned a non-success status")
            parsed = _EmbeddingResponse.model_validate_json(response.data)
        except (HTTPError, OSError, ValueError, ValidationError) as error:
            raise EmbeddingProviderUnavailableError() from error
        if (
            parsed.model_revision != profile.model_revision
            or parsed.dimension != profile.embedding_dimension
            or not parsed.normalized
            or len(parsed.data) != len(values)
        ):
            raise EmbeddingProviderUnavailableError()
        ordered = sorted(parsed.data, key=lambda item: item.index)
        if [item.index for item in ordered] != list(range(len(values))):
            raise EmbeddingProviderUnavailableError()
        try:
            return tuple(
                EmbeddingVector(
                    values=item.embedding,
                    model=parsed.model,
                    model_revision=parsed.model_revision,
                    normalized=parsed.normalized,
                    token_count=item.token_count,
                    truncated=item.truncated,
                )
                for item in ordered
            )
        except ValidationError as error:
            raise EmbeddingProviderUnavailableError() from error


__all__ = ["HTTPEmbeddingProvider"]
