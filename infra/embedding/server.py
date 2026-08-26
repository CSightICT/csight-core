"""Private host-native Qwen3 embedding service with no Core database access."""

from __future__ import annotations

import math
import os
from contextlib import asynccontextmanager
from threading import Lock
from typing import Literal

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sentence_transformers import SentenceTransformer

MODEL_ALIAS = "csight-qwen3-embedding-0.6b"
MODEL_ARTIFACT = os.getenv("EMBEDDING_MODEL_ARTIFACT", "Qwen/Qwen3-Embedding-0.6B")
MODEL_REVISION = os.getenv("EMBEDDING_MODEL_REVISION", "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3")
DEVICE = os.getenv("EMBEDDING_DEVICE", "mps")
MAX_TOKENS = int(os.getenv("EMBEDDING_MAX_TOKENS", "8192"))
MAX_BATCH_SIZE = int(os.getenv("EMBEDDING_MAX_BATCH_SIZE", "32"))
QUERY_PROMPT = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"
)


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    model: Literal["csight-qwen3-embedding-0.6b"]
    input: tuple[str, ...] = Field(min_length=1, max_length=MAX_BATCH_SIZE)
    input_type: Literal["query", "document"]


class EmbeddingItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int
    embedding: tuple[float, ...]
    token_count: int
    truncated: bool = False


class EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model: str
    model_revision: str
    dimension: int
    normalized: bool
    data: tuple[EmbeddingItem, ...]


class Runtime:
    def __init__(self) -> None:
        if DEVICE == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("MPS was requested but is unavailable")
        self.model = SentenceTransformer(
            MODEL_ARTIFACT,
            revision=MODEL_REVISION,
            device=DEVICE,
            trust_remote_code=False,
        )
        self.model.max_seq_length = MAX_TOKENS
        self.lock = Lock()
        dimension = self.model.get_embedding_dimension()
        if dimension is None:
            raise RuntimeError("embedding dimension is unavailable")
        self.dimension = dimension

    def encode(self, request: EmbeddingRequest) -> EmbeddingResponse:
        values = tuple(value.strip() for value in request.input)
        if any(not value for value in values):
            raise HTTPException(status_code=422, detail="Embedding input must not be blank.")
        serialized = tuple(
            f"{QUERY_PROMPT}{value}" if request.input_type == "query" else value for value in values
        )
        token_counts = tuple(
            len(self.model.tokenizer(value, add_special_tokens=True, truncation=False)["input_ids"])
            for value in serialized
        )
        if any(count > MAX_TOKENS for count in token_counts):
            raise HTTPException(status_code=422, detail="Embedding input exceeds token limit.")
        with self.lock:
            vectors = self.model.encode(
                values,
                prompt=QUERY_PROMPT if request.input_type == "query" else None,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        items: list[EmbeddingItem] = []
        for index, (vector, token_count) in enumerate(zip(vectors, token_counts, strict=True)):
            values_tuple = tuple(float(value) for value in vector.tolist())
            if len(values_tuple) != self.dimension or any(
                not math.isfinite(value) for value in values_tuple
            ):
                raise RuntimeError("model returned an invalid embedding")
            items.append(
                EmbeddingItem(
                    index=index,
                    embedding=values_tuple,
                    token_count=token_count,
                )
            )
        return EmbeddingResponse(
            model=MODEL_ALIAS,
            model_revision=MODEL_REVISION,
            dimension=self.dimension,
            normalized=True,
            data=tuple(items),
        )


runtime: Runtime | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global runtime
    runtime = Runtime()
    yield
    runtime = None


app = FastAPI(title="CSight private embedding service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    if runtime is None:
        raise HTTPException(status_code=503, detail="Model is not loaded.")
    allocated = torch.mps.current_allocated_memory() if DEVICE == "mps" else 0
    return {
        "status": "ok",
        "device": DEVICE,
        "model_loaded": True,
        "device_allocated_bytes": allocated,
    }


@app.get("/v1/models")
def models() -> dict[str, object]:
    if runtime is None:
        raise HTTPException(status_code=503, detail="Model is not loaded.")
    return {
        "data": [
            {
                "id": MODEL_ALIAS,
                "artifact": MODEL_ARTIFACT,
                "revision": MODEL_REVISION,
                "dimension": runtime.dimension,
                "pooling": "last-token",
                "normalized": True,
                "max_tokens": MAX_TOKENS,
            }
        ]
    }


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
def embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    if runtime is None:
        raise HTTPException(status_code=503, detail="Model is not loaded.")
    return runtime.encode(request)
