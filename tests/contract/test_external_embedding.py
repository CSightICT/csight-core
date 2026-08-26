"""Opt-in contract tests for the real private embedding service."""

import math
import os

import pytest
import urllib3
from urllib3 import Timeout

pytestmark = [pytest.mark.contract, pytest.mark.external_embedding]


def test_real_qwen_embedding_service_contract() -> None:
    if os.getenv("RUN_EXTERNAL_EMBEDDING_TESTS") != "1":
        pytest.skip("SKIPPED_EXTERNAL_EMBEDDING_NOT_ENABLED")
    base_url = os.getenv("EMBEDDING_BASE_URL", "http://127.0.0.1:8091").rstrip("/")
    pool = urllib3.PoolManager(timeout=Timeout(connect=2, read=60), retries=False)
    health = pool.request("GET", f"{base_url}/health")
    assert health.status == 200
    model = pool.request("GET", f"{base_url}/v1/models").json()["data"][0]
    assert model["revision"] == "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    assert model["dimension"] == 1024
    assert model["pooling"] == "last-token"
    for input_type in ("query", "document"):
        response = pool.request(
            "POST",
            f"{base_url}/v1/embeddings",
            json={
                "model": "csight-qwen3-embedding-0.6b",
                "input": ["누액 상품 교환 조건", "필요한 이미지 증거"],
                "input_type": input_type,
            },
        )
        assert response.status == 200
        payload = response.json()
        assert payload["dimension"] == 1024
        assert payload["normalized"] is True
        assert len(payload["data"]) == 2
        for item in payload["data"]:
            assert len(item["embedding"]) == 1024
            assert all(math.isfinite(value) for value in item["embedding"])
            norm = math.sqrt(sum(value * value for value in item["embedding"]))
            assert norm == pytest.approx(1.0, abs=0.005)
    malformed = pool.request(
        "POST", f"{base_url}/v1/embeddings", json={"model": "wrong", "input": []}
    )
    assert malformed.status == 422
