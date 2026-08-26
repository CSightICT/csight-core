"""Authenticated two-tenant smoke for the locked HYBRID_RERANKED execution profile."""

import argparse
from pathlib import Path

import urllib3

from app.bootstrap.settings import Settings


def _login(pool: urllib3.PoolManager, base_url: str, slug: str, password: str) -> str:
    response = pool.request(
        "POST",
        f"{base_url}/api/v1/auth/token",
        json={
            "tenant_slug": slug,
            "email": f"reviewer@{slug}.demo",
            "password": password,
        },
    )
    if response.status != 200:
        raise RuntimeError(f"login failed with status {response.status}")
    return str(response.json()["access_token"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    password = settings.development_seed_reviewer_password
    if password is None:
        raise ValueError("DEVELOPMENT_SEED_REVIEWER_PASSWORD is required")
    pool = urllib3.PoolManager()
    for slug in ("csight-demo-brand", "csight-demo-retail"):
        token = _login(pool, arguments.base_url, slug, password.get_secret_value())
        response = pool.request(
            "POST",
            f"{arguments.base_url}/api/v1/policy-retrieval/search",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": "수령 후 3일 내 누액 상품의 교환 조건과 필요한 이미지 증거",
                "as_of_date": "2026-02-01",
                "mode": "HYBRID_RERANKED",
                "top_k": 10,
                "filters": {
                    "policy_types": ["LEAKAGE_CONTAMINATION"],
                    "product_categories": ["GENERAL"],
                    "defect_types": ["LEAKAGE"],
                },
            },
        )
        if response.status != 200:
            raise RuntimeError(f"{slug} reranked search failed with {response.status}")
        payload = response.json()
        hits = payload["hits"]
        if not hits or len(hits) > 10:
            raise RuntimeError("reranked search returned an invalid hit count")
        if not all(
            hit["candidate_rank"] >= 1
            and hit["rerank_rank"] >= 1
            and 0 <= hit["rerank_score"] <= 1
            and hit["reranker_profile"] == "qwen3_policy_reranker:1.0.0"
            for hit in hits
        ):
            raise RuntimeError("reranked response metadata is invalid")
        if any(
            hit["clause_id"].startswith("POLICY-RTL" if slug.endswith("brand") else "POLICY-BRD")
            for hit in hits
        ):
            raise RuntimeError("cross-tenant candidate escaped the filter")
        forbidden = ("tenant_id", "embedding_vector", "decision", "approval", "applicable")
        if any(value in response.data.decode("utf-8").casefold() for value in forbidden):
            raise RuntimeError("forbidden internal or decision field escaped the response")
        print(
            f"POLICY_RERANKED_SMOKE tenant={slug} hits={len(hits)} "
            f"first={hits[0]['clause_id']} candidate_rank={hits[0]['candidate_rank']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
