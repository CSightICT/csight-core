"""Private Qwen3 reranker service; receives only Core-filtered candidates."""

from __future__ import annotations

import math
import os
import time
from contextlib import asynccontextmanager
from threading import Lock
from typing import Literal

import psutil
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ALIAS = "csight-qwen3-reranker-0.6b"
MODEL_ARTIFACT = os.getenv("RERANKER_MODEL_ARTIFACT", "Qwen/Qwen3-Reranker-0.6B")
MODEL_REVISION = os.getenv("RERANKER_MODEL_REVISION", "e61197ed45024b0ed8a2d74b80b4d909f1255473")
PROFILE_VERSION = "1.0.0"
DEVICE = os.getenv("RERANKER_DEVICE", "mps")
MAX_PAIR_TOKENS = int(os.getenv("RERANKER_MAX_PAIR_TOKENS", "2048"))
MAX_BATCH_SIZE = int(os.getenv("RERANKER_MAX_BATCH_SIZE", "8"))
INSTRUCTION = "Given a policy search query, retrieve policy clauses relevant to resolving the query"
PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query "
    'and the Instruct provided. Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n<|im_start|>user\n"
)
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


class RerankDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    candidate_id: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=50_000)


class RerankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    model: Literal["csight-qwen3-reranker-0.6b"]
    query: str = Field(min_length=1, max_length=20_000)
    documents: tuple[RerankDocument, ...] = Field(min_length=1, max_length=50)
    top_n: int = Field(ge=1, le=50)

    @model_validator(mode="after")
    def validate_candidate_set(self) -> RerankRequest:
        candidate_ids = tuple(item.candidate_id for item in self.documents)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_id values must be unique")
        if self.top_n > len(candidate_ids):
            raise ValueError("top_n must not exceed candidate count")
        return self


class RerankResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    original_rank: int
    rerank_rank: int
    rerank_score: float


class RerankResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model: str
    model_revision: str
    profile_version: str
    results: tuple[RerankResult, ...]
    latency_ms: float


class Runtime:
    def __init__(self) -> None:
        if DEVICE not in {"mps", "cpu"}:
            raise RuntimeError("RERANKER_DEVICE must be mps or cpu")
        if DEVICE == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("MPS was requested but is unavailable")
        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ARTIFACT,
            revision=MODEL_REVISION,
            padding_side="left",
            trust_remote_code=False,
        )
        self.tokenizer.padding_side = "left"
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ARTIFACT,
            revision=MODEL_REVISION,
            dtype=torch.bfloat16 if DEVICE == "mps" else torch.float32,
            low_cpu_mem_usage=True,
            trust_remote_code=False,
        ).eval()
        self.model.to(DEVICE)
        self.false_token_id = int(self.tokenizer.convert_tokens_to_ids("no"))
        self.true_token_id = int(self.tokenizer.convert_tokens_to_ids("yes"))
        self.prefix_tokens = self.tokenizer.encode(PREFIX, add_special_tokens=False)
        self.suffix_tokens = self.tokenizer.encode(SUFFIX, add_special_tokens=False)
        if (
            self.false_token_id == self.true_token_id
            or min(self.false_token_id, self.true_token_id) < 0
        ):
            raise RuntimeError("yes/no scoring token IDs are invalid")
        if len(self.prefix_tokens) + len(self.suffix_tokens) >= MAX_PAIR_TOKENS:
            raise RuntimeError("pair token limit cannot hold the fixed prompt")
        self.lock = Lock()

    @staticmethod
    def pair_text(query: str, document: str) -> str:
        return f"<Instruct>: {INSTRUCTION}\n<Query>: {query}\n<Document>: {document}"

    def token_count(self, query: str, document: str) -> int:
        body = self.tokenizer.encode(self.pair_text(query, document), add_special_tokens=False)
        return len(self.prefix_tokens) + len(body) + len(self.suffix_tokens)

    def _inputs(self, pairs: tuple[str, ...]) -> dict[str, torch.Tensor]:
        available = MAX_PAIR_TOKENS - len(self.prefix_tokens) - len(self.suffix_tokens)
        inputs = self.tokenizer(
            list(pairs),
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=available,
        )
        for index, input_ids in enumerate(inputs["input_ids"]):
            inputs["input_ids"][index] = self.prefix_tokens + input_ids + self.suffix_tokens
        padded = self.tokenizer.pad(
            inputs,
            padding=True,
            return_tensors="pt",
        )
        return {key: value.to(DEVICE) for key, value in padded.items()}

    def score(self, request: RerankRequest) -> RerankResponse:
        started = time.perf_counter()
        pairs = tuple(self.pair_text(request.query, item.text) for item in request.documents)
        scores: list[float] = []
        with self.lock, torch.inference_mode():
            counts = tuple(self.token_count(request.query, item.text) for item in request.documents)
            if any(count > MAX_PAIR_TOKENS for count in counts):
                raise HTTPException(
                    status_code=422,
                    detail="Reranker pair exceeds the versioned token limit.",
                )
            for offset in range(0, len(pairs), MAX_BATCH_SIZE):
                inputs = self._inputs(pairs[offset : offset + MAX_BATCH_SIZE])
                logits = self.model(**inputs).logits[:, -1, :]
                label_logits = torch.stack(
                    [logits[:, self.false_token_id], logits[:, self.true_token_id]], dim=1
                )
                normalized = torch.nn.functional.log_softmax(label_logits.float(), dim=1)[
                    :, 1
                ].exp()
                scores.extend(float(value) for value in normalized.cpu().tolist())
        if len(scores) != len(request.documents) or any(
            not math.isfinite(value) or value < 0.0 or value > 1.0 for value in scores
        ):
            raise RuntimeError("model returned an invalid relevance score")
        ranked = sorted(
            enumerate(zip(request.documents, scores, strict=True), start=1),
            key=lambda value: (-value[1][1], value[0], value[1][0].candidate_id),
        )[: request.top_n]
        results = tuple(
            RerankResult(
                candidate_id=document.candidate_id,
                original_rank=original_rank,
                rerank_rank=rerank_rank,
                rerank_score=score,
            )
            for rerank_rank, (original_rank, (document, score)) in enumerate(ranked, start=1)
        )
        return RerankResponse(
            model=MODEL_ALIAS,
            model_revision=MODEL_REVISION,
            profile_version=PROFILE_VERSION,
            results=results,
            latency_ms=(time.perf_counter() - started) * 1000,
        )


runtime: Runtime | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global runtime
    runtime = Runtime()
    yield
    runtime = None


app = FastAPI(title="CSight private reranker service", version=PROFILE_VERSION, lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    if runtime is None:
        raise HTTPException(status_code=503, detail="Model is not loaded.")
    allocated = torch.mps.current_allocated_memory() if DEVICE == "mps" else 0
    driver_allocated = torch.mps.driver_allocated_memory() if DEVICE == "mps" else 0
    return {
        "status": "ok",
        "device": DEVICE,
        "model_loaded": True,
        "device_allocated_bytes": allocated,
        "device_driver_allocated_bytes": driver_allocated,
        "process_rss_bytes": psutil.Process(os.getpid()).memory_info().rss,
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
                "architecture": "Qwen3ForCausalLM",
                "profile_version": PROFILE_VERSION,
                "device": DEVICE,
                "padding_side": "left",
                "max_pair_tokens": MAX_PAIR_TOKENS,
                "max_batch_size": MAX_BATCH_SIZE,
                "score_semantics": "normalized yes-vs-no pairwise relevance score",
                "score_range": [0.0, 1.0],
            }
        ]
    }


@app.post("/v1/rerank", response_model=RerankResponse)
def rerank(request: RerankRequest) -> RerankResponse:
    if runtime is None:
        raise HTTPException(status_code=503, detail="Model is not loaded.")
    return runtime.score(request)
