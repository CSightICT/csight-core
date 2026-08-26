"""Authenticated local smoke for lexical, dense, hybrid, and tenant isolation."""

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
    tokens = {
        slug: _login(pool, arguments.base_url, slug, password.get_secret_value())
        for slug in ("csight-demo-brand", "csight-demo-retail")
    }
    first_by_tenant: dict[str, str] = {}
    for slug, token in tokens.items():
        for mode in ("LEXICAL", "DENSE", "HYBRID"):
            response = pool.request(
                "POST",
                f"{arguments.base_url}/api/v1/policy-retrieval/search",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "query": "누액 상품의 교환 조건과 필요한 이미지 증거",
                    "as_of_date": "2026-02-01",
                    "mode": mode,
                    "top_k": 5,
                    "filters": {
                        "policy_types": ["LEAKAGE_CONTAMINATION"],
                        "product_categories": ["GENERAL"],
                        "defect_types": ["LEAKAGE"],
                    },
                },
            )
            if response.status != 200:
                raise RuntimeError(f"{slug} {mode} failed with status {response.status}")
            payload = response.json()
            if not payload["hits"]:
                raise RuntimeError(f"{slug} {mode} returned no hits")
            first_by_tenant.setdefault(slug, payload["hits"][0]["clause_id"])
            if not all(hit["document_status"] == "ACTIVE" for hit in payload["hits"]):
                raise RuntimeError("non-active policy escaped the API filter")
            print(
                f"POLICY_SEARCH_SMOKE tenant={slug} mode={mode} "
                f"hits={len(payload['hits'])} first={payload['hits'][0]['clause_id']}"
            )
    if first_by_tenant["csight-demo-brand"].startswith("POLICY-RTL") or first_by_tenant[
        "csight-demo-retail"
    ].startswith("POLICY-BRD"):
        raise RuntimeError("cross-tenant policy hit detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
