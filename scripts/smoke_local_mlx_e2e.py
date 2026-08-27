"""Run ten authenticated Local MLX Case-to-grounding flows through Docker Core."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from uuid import uuid4

import urllib3

from app.bootstrap.settings import Settings


def _request(pool: urllib3.PoolManager, method: str, url: str, **kwargs: object) -> dict:
    response = pool.request(method, url, **kwargs)
    if response.status not in {200, 201, 202}:
        raise RuntimeError(f"{method} {url} failed with HTTP {response.status}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("API response was not an object")
    return payload


def _wait(
    pool: urllib3.PoolManager,
    url: str,
    headers: dict[str, str],
    projection: str,
    timeout: float = 300,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = _request(pool, "GET", url, headers=headers)
        run = detail.get(projection)
        if isinstance(run, dict) and run.get("status") in {"SUCCEEDED", "FAILED"}:
            if run["status"] != "SUCCEEDED":
                raise RuntimeError(f"run failed: {run.get('failure_code') or run.get('failure')}")
            return detail
        time.sleep(1)
    raise RuntimeError("run timed out")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)  # pyright: ignore[reportCallIssue]
    password = settings.development_seed_reviewer_password
    if password is None:
        raise RuntimeError("development reviewer password is required")
    pool = urllib3.PoolManager()
    login = _request(
        pool,
        "POST",
        f"{args.base_url}/api/v1/auth/token",
        json={
            "tenant_slug": "csight-demo-brand",
            "email": "reviewer@csight-demo-brand.demo",
            "password": password.get_secret_value(),
        },
    )
    auth = {"Authorization": f"Bearer {login['access_token']}"}
    successes = 0
    for index in range(1, 11):
        suffix = uuid4().hex
        case = _request(
            pool,
            "POST",
            f"{args.base_url}/api/v1/cases",
            headers={**auth, "Idempotency-Key": f"local-mlx-case-{suffix}"},
            json={
                "order_ref": f"LOCAL-MLX-{index}-{suffix[:8]}",
                "product_ref": "LOCAL-MLX-SYNTHETIC",
                "customer_message": "용기 하단이 깨져 내용물이 샙니다. 교환해주세요.",
                "requested_action": "EXCHANGE",
                "attributes": {"product_category": "GENERAL", "days_since_purchase": 3},
            },
        )
        case_id = str(case["case_id"])
        analysis_url = f"{args.base_url}/api/v1/cases/{case_id}/analysis-runs"
        analysis = _request(
            pool,
            "POST",
            analysis_url,
            headers={**auth, "Idempotency-Key": f"local-mlx-analysis-{suffix}"},
            json={"pipeline": "product_defect_text_extraction", "pipeline_version": "2.0.0"},
        )
        analysis_id = str(analysis["analysis_run_id"])
        analysis_detail = _wait(pool, f"{analysis_url}/{analysis_id}", auth, "run")
        extraction = analysis_detail.get("extraction_result_v2")
        if not isinstance(extraction, dict):
            raise RuntimeError("analysis result missing")

        retrieval_url = f"{args.base_url}/api/v1/cases/{case_id}/policy-retrieval-runs"
        retrieval = _request(
            pool,
            "POST",
            retrieval_url,
            headers={**auth, "Idempotency-Key": f"local-mlx-retrieval-{suffix}"},
            json={
                "analysis_run_id": analysis_id,
                "strategy": "RAW",
                "as_of_date": "2026-02-01",
                "top_k": 3,
            },
        )
        retrieval_id = str(retrieval["id"])
        retrieval_detail = _wait(pool, f"{retrieval_url}/{retrieval_id}", auth, "run")
        if not retrieval_detail.get("hits"):
            raise RuntimeError("retrieval returned no hits")

        grounding_url = f"{args.base_url}/api/v1/cases/{case_id}/grounded-explanation-runs"
        key = f"local-mlx-grounding-{suffix}"
        grounding = _request(
            pool,
            "POST",
            grounding_url,
            headers={**auth, "Idempotency-Key": key},
            json={"retrieval_run_id": retrieval_id},
        )
        replay = _request(
            pool,
            "POST",
            grounding_url,
            headers={**auth, "Idempotency-Key": key},
            json={"retrieval_run_id": retrieval_id},
        )
        if grounding["id"] != replay["id"]:
            raise RuntimeError("grounding idempotency replay created a duplicate")
        detail = _wait(pool, f"{grounding_url}/{grounding['id']}", auth, "run")
        pack = detail.get("citation_pack")
        explanation = detail.get("explanation")
        if not isinstance(pack, dict) or not isinstance(explanation, dict):
            raise RuntimeError("grounded result missing")
        allowlist = {item["citation_id"] for item in pack.get("citations", [])}
        used = {
            citation
            for statement in explanation.get("policy_statements", [])
            for citation in statement.get("citation_ids", [])
        }
        if not used or not used <= allowlist:
            raise RuntimeError("citation allowlist validation failed")
        successes += 1
    print(
        "LOCAL_MLX_E2E "
        f"cases={successes} failures={10 - successes} strategy=RAW "
        "retriever=HYBRID duplicate_grounding=0 citation_violations=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
