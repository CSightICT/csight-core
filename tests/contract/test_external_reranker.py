"""Opt-in contract test for the real pinned private reranker service."""

import math
import os

import pytest
import urllib3
from urllib3 import Timeout

pytestmark = [pytest.mark.contract, pytest.mark.external_reranker]


def test_real_qwen_reranker_service_contract() -> None:
    if os.getenv("RUN_EXTERNAL_RERANKER_TESTS") != "1":
        pytest.skip("SKIPPED_EXTERNAL_RERANKER_NOT_ENABLED")
    base_url = os.getenv("RERANKER_BASE_URL", "http://127.0.0.1:8092").rstrip("/")
    pool = urllib3.PoolManager(timeout=Timeout(connect=2, read=180), retries=False)
    health = pool.request("GET", f"{base_url}/health")
    assert health.status == 200
    model = pool.request("GET", f"{base_url}/v1/models").json()["data"][0]
    assert model["revision"] == "e61197ed45024b0ed8a2d74b80b4d909f1255473"
    assert model["architecture"] == "Qwen3ForCausalLM"
    assert model["padding_side"] == "left"
    response = pool.request(
        "POST",
        f"{base_url}/v1/rerank",
        json={
            "model": "csight-qwen3-reranker-0.6b",
            "query": "수령 후 3일 내 누액 상품 교환 조건",
            "documents": [
                {
                    "candidate_id": "relevant",
                    "text": "문서: 교환 정책\n섹션: 누액\n정책 유형: RETURN_EXCHANGE\n"
                    "조항 유형: RULE\n본문: 3일 내 누액 사진 제출 시 교환한다.",
                },
                {
                    "candidate_id": "irrelevant",
                    "text": "문서: 보관 정책\n섹션: 로그\n정책 유형: PRIVACY\n"
                    "조항 유형: RULE\n본문: 로그를 30일 보관한다.",
                },
            ],
            "top_n": 2,
        },
    )
    assert response.status == 200
    payload = response.json()
    assert payload["results"][0]["candidate_id"] == "relevant"
    assert {value["candidate_id"] for value in payload["results"]} == {
        "relevant",
        "irrelevant",
    }
    assert all(math.isfinite(value["rerank_score"]) for value in payload["results"])
    assert all(0 <= value["rerank_score"] <= 1 for value in payload["results"])
    malformed = pool.request(
        "POST",
        f"{base_url}/v1/rerank",
        json={
            "model": "csight-qwen3-reranker-0.6b",
            "query": "query",
            "documents": [
                {"candidate_id": "duplicate", "text": "a"},
                {"candidate_id": "duplicate", "text": "b"},
            ],
            "top_n": 2,
        },
    )
    assert malformed.status == 422
