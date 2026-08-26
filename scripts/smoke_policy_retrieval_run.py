"""Local authenticated deterministic Case-to-policy retrieval smoke."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from uuid import uuid4

import urllib3

from app.bootstrap.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)  # pyright: ignore[reportCallIssue]
    password = settings.development_seed_reviewer_password
    if password is None:
        raise ValueError("DEVELOPMENT_SEED_REVIEWER_PASSWORD is required")
    pool = urllib3.PoolManager()
    login = pool.request(
        "POST",
        f"{args.base_url}/api/v1/auth/token",
        json={
            "tenant_slug": "csight-demo-brand",
            "email": "reviewer@csight-demo-brand.demo",
            "password": password.get_secret_value(),
        },
    )
    token = str(login.json()["access_token"])
    auth = {"Authorization": f"Bearer {token}"}
    suffix = uuid4().hex
    created = pool.request(
        "POST",
        f"{args.base_url}/api/v1/cases",
        headers={**auth, "Idempotency-Key": f"query-smoke-case-{suffix}"},
        json={
            "order_ref": f"QUERY-SMOKE-{suffix}",
            "product_ref": f"QUERY-SMOKE-PRODUCT-{suffix}",
            "customer_message": "용기 하단이 깨져 내용물이 샙니다. 교환해주세요.",
            "requested_action": "EXCHANGE",
            "attributes": {"product_category": "GENERAL", "days_since_purchase": 3},
        },
    )
    case_id = str(created.json()["case_id"])
    analysis_url = f"{args.base_url}/api/v1/cases/{case_id}/analysis-runs"
    analysis = pool.request(
        "POST",
        analysis_url,
        headers={**auth, "Idempotency-Key": f"query-smoke-analysis-{suffix}"},
        json={
            "pipeline": "product_defect_text_extraction",
            "pipeline_version": "2.0.0",
        },
    )
    analysis_run_id = str(analysis.json()["analysis_run_id"])
    for _ in range(60):
        detail = pool.request("GET", f"{analysis_url}/{analysis_run_id}", headers=auth).json()
        if detail["run"]["status"] in {"SUCCEEDED", "FAILED"}:
            break
        time.sleep(1)
    if detail["run"]["status"] != "SUCCEEDED":
        raise RuntimeError("v2 analysis did not succeed")
    run_url = f"{args.base_url}/api/v1/cases/{case_id}/policy-retrieval-runs"
    response = pool.request(
        "POST",
        run_url,
        headers={**auth, "Idempotency-Key": f"query-smoke-run-{suffix}"},
        json={
            "analysis_run_id": analysis_run_id,
            "strategy": "DETERMINISTIC",
            "as_of_date": "2026-02-01",
            "top_k": 10,
        },
    )
    if response.status != 202:
        raise RuntimeError(f"retrieval run POST failed: {response.status}")
    run_id = str(response.json()["id"])
    for _ in range(60):
        final = pool.request("GET", f"{run_url}/{run_id}", headers=auth).json()
        if final["run"]["status"] in {"SUCCEEDED", "FAILED"}:
            break
        time.sleep(1)
    if final["run"]["status"] != "SUCCEEDED":
        raise RuntimeError("policy retrieval run did not succeed")
    if final["retrieval_profile"]["base_mode"] != "HYBRID" or not final["hits"]:
        raise RuntimeError("policy retrieval run returned an invalid retrieval result")
    print(
        f"POLICY_RETRIEVAL_RUN_SMOKE case={case_id} run={run_id} "
        f"queries={len(final['query_plan']['queries'])} hits={len(final['hits'])}"
    )


if __name__ == "__main__":
    main()
