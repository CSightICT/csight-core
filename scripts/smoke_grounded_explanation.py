"""Local authenticated Citation Pack and grounded-explanation smoke flow."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from uuid import uuid4

import urllib3
from sqlalchemy import select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import PolicyRetrievalRunModel, TenantModel
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings


def _login(
    pool: urllib3.PoolManager,
    *,
    base_url: str,
    tenant_slug: str,
    email: str,
    password: str,
) -> str:
    response = pool.request(
        "POST",
        f"{base_url}/api/v1/auth/token",
        json={"tenant_slug": tenant_slug, "email": email, "password": password},
    )
    if response.status != 200:
        raise RuntimeError(f"login failed: {response.status}")
    return str(response.json()["access_token"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    password = settings.development_seed_reviewer_password
    if password is None:
        raise ValueError("DEVELOPMENT_SEED_REVIEWER_PASSWORD is required")
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        source = session.execute(
            select(PolicyRetrievalRunModel.case_id, PolicyRetrievalRunModel.id)
            .join(TenantModel, TenantModel.id == PolicyRetrievalRunModel.tenant_id)
            .where(
                TenantModel.slug == "csight-demo-brand",
                PolicyRetrievalRunModel.status == "SUCCEEDED",
            )
            .order_by(PolicyRetrievalRunModel.created_at.desc())
            .limit(1)
        ).one_or_none()
    if source is None:
        raise RuntimeError("a successful synthetic policy retrieval run is required")
    case_id, retrieval_run_id = map(str, source)
    pool = urllib3.PoolManager()
    password_value = password.get_secret_value()
    brand_token = _login(
        pool,
        base_url=arguments.base_url,
        tenant_slug="csight-demo-brand",
        email="reviewer@csight-demo-brand.demo",
        password=password_value,
    )
    url = f"{arguments.base_url}/api/v1/cases/{case_id}/grounded-explanation-runs"
    key = f"grounding-smoke-{uuid4()}"
    headers = {"Authorization": f"Bearer {brand_token}", "Idempotency-Key": key}
    first = pool.request(
        "POST",
        url,
        headers=headers,
        json={"retrieval_run_id": retrieval_run_id},
    )
    replay = pool.request(
        "POST",
        url,
        headers=headers,
        json={"retrieval_run_id": retrieval_run_id},
    )
    if first.status != 202 or replay.status != 200 or first.json()["id"] != replay.json()["id"]:
        raise RuntimeError("grounded explanation idempotency contract failed")
    run_id = str(first.json()["id"])
    detail: dict[str, object] = {}
    for _ in range(30):
        response = pool.request(
            "GET",
            f"{url}/{run_id}",
            headers={"Authorization": f"Bearer {brand_token}"},
        )
        detail = response.json()
        run = detail.get("run")
        if isinstance(run, dict) and run.get("status") in {"SUCCEEDED", "FAILED"}:
            break
        time.sleep(1)
    run = detail.get("run")
    if not isinstance(run, dict) or run.get("status") != "SUCCEEDED":
        raise RuntimeError("grounded explanation did not succeed")
    pack = detail.get("citation_pack")
    explanation = detail.get("explanation")
    if not isinstance(pack, dict) or not isinstance(explanation, dict):
        raise RuntimeError("grounded explanation detail is incomplete")
    citations = pack.get("citations")
    statements = explanation.get("policy_statements")
    if not isinstance(citations, list) or not citations or not isinstance(statements, list):
        raise RuntimeError("citation pack or explanation is empty")
    if any("policy_clause_row_id" in item for item in citations if isinstance(item, dict)):
        raise RuntimeError("public citation pack exposed an internal clause row ID")
    retail_token = _login(
        pool,
        base_url=arguments.base_url,
        tenant_slug="csight-demo-retail",
        email="reviewer@csight-demo-retail.demo",
        password=password_value,
    )
    cross = pool.request(
        "GET",
        f"{url}/{run_id}",
        headers={"Authorization": f"Bearer {retail_token}"},
    )
    if cross.status != 404:
        raise RuntimeError("cross-tenant grounded explanation detail must be hidden")
    print(
        "GROUNDED_EXPLANATION_SMOKE "
        f"run={run_id} citations={len(citations)} statements={len(statements)} "
        "replay=200 cross_tenant=404"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
