"""Authenticated asynchronous deterministic policy evaluation smoke flow."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import urllib3
from sqlalchemy import func, select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    PolicyEvaluationOutboxEventModel,
    PolicyRuleEvaluationResultModel,
)
from app.adapters.persistence.session import create_session_factory
from app.application.policy_engine import ExecutePolicyEvaluationCommand
from app.bootstrap.settings import Settings
from app.bootstrap.sprint5a import build_execute_policy_evaluation


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
    parser.add_argument("--base-url")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--timeout-seconds", type=float, default=60)
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    password = settings.development_seed_reviewer_password
    if password is None:
        raise ValueError("DEVELOPMENT_SEED_REVIEWER_PASSWORD is required")
    base_url = (arguments.base_url or "http://127.0.0.1:8000").rstrip("/")
    if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("policy smoke accepts only a local API URL")
    factory = create_session_factory(get_engine(settings))
    pool = urllib3.PoolManager()
    password_value = password.get_secret_value()
    brand = _login(
        pool,
        base_url=base_url,
        tenant_slug="csight-demo-brand",
        email="reviewer@csight-demo-brand.demo",
        password=password_value,
    )
    auth = {"Authorization": f"Bearer {brand}"}
    suffix = uuid4().hex
    created = pool.request(
        "POST",
        f"{base_url}/api/v1/cases",
        headers={**auth, "Idempotency-Key": f"policy-smoke-case-{suffix}"},
        json={
            "order_ref": f"POLICY-SMOKE-{suffix}",
            "product_ref": "POLICY-SMOKE-HIGH-VALUE",
            "customer_message": "합성 테스트: 용기가 깨져 내용물이 샙니다. 교환을 요청합니다.",
            "requested_action": "EXCHANGE",
            "attributes": {
                "product_category": "GENERAL",
                "days_since_purchase": 3,
                "order_amount": 500000,
                "external_action_input": {
                    "amount": "48000.0000",
                    "currency": "KRW",
                },
            },
        },
    )
    if created.status != 201:
        raise RuntimeError(f"synthetic policy smoke case creation failed: {created.status}")
    case_id = str(created.json()["case_id"])
    analysis_url = f"{base_url}/api/v1/cases/{case_id}/analysis-runs"
    analysis = pool.request(
        "POST",
        analysis_url,
        headers={**auth, "Idempotency-Key": f"policy-smoke-analysis-{suffix}"},
        json={"pipeline": "product_defect_text_extraction", "pipeline_version": "2.0.0"},
    )
    if analysis.status != 202:
        raise RuntimeError(f"synthetic v2 analysis creation failed: {analysis.status}")
    analysis_run_id = str(analysis.json()["analysis_run_id"])
    analysis_deadline = time.monotonic() + arguments.timeout_seconds
    analysis_detail: dict[str, object] = {}
    analysis_status: object = None
    while time.monotonic() < analysis_deadline:
        analysis_detail = pool.request(
            "GET", f"{analysis_url}/{analysis_run_id}", headers=auth
        ).json()
        analysis_run = analysis_detail.get("run")
        if not isinstance(analysis_run, dict):
            raise RuntimeError("synthetic v2 analysis detail omitted its run")
        analysis_status = analysis_run.get("status")
        if analysis_status in {"SUCCEEDED", "FAILED"}:
            break
        time.sleep(1)
    if analysis_status != "SUCCEEDED" or not isinstance(
        analysis_detail.get("extraction_result_v2"), dict
    ):
        raise RuntimeError("synthetic v2 analysis did not succeed")
    url = f"{base_url}/api/v1/cases/{case_id}/policy-evaluation-runs"
    key = f"policy-smoke-{uuid4()}"
    headers = {"Authorization": f"Bearer {brand}", "Idempotency-Key": key}
    body = {"analysis_run_id": str(analysis_run_id), "as_of_date": "2026-02-01"}
    first = pool.request("POST", url, headers=headers, json=body)
    replay = pool.request("POST", url, headers=headers, json=body)
    if first.status != 202 or replay.status != 200:
        raise RuntimeError("policy evaluation create/replay status contract failed")
    run_id = str(first.json()["policy_evaluation_run_id"])
    if replay.json()["policy_evaluation_run_id"] != run_id:
        raise RuntimeError("policy evaluation replay returned a different run")
    deadline = time.monotonic() + arguments.timeout_seconds
    detail: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = pool.request(
            "GET",
            f"{url}/{run_id}",
            headers={"Authorization": f"Bearer {brand}"},
        )
        detail = response.json()
        run = detail.get("run")
        if isinstance(run, dict) and run.get("status") in {"SUCCEEDED", "FAILED"}:
            break
        time.sleep(1)
    run = detail.get("run")
    results = detail.get("rule_results")
    if not isinstance(run, dict) or run.get("status") != "SUCCEEDED":
        raise RuntimeError("policy evaluation did not succeed")
    if not isinstance(results, list) or len(results) != 12:
        raise RuntimeError("policy evaluation detail omitted rule results")
    serialized = json.dumps(detail, sort_keys=True)
    if any(token in serialized for token in ("APPROVED", "REJECTED", "CUSTOMER_FRAUD")):
        raise RuntimeError("policy evaluation exposed a forbidden final decision")
    qualifications = detail.get("input_qualification")
    if not isinstance(qualifications, dict) or qualifications.get("vision") != "MOCK_QUALIFIED":
        raise RuntimeError("policy evaluation hid the mock Vision qualification")
    if "NOT_EVALUATED" not in serialized:
        raise RuntimeError("mock Vision did not produce NOT_EVALUATED")
    if "REQUIRE_ADDITIONAL_EVIDENCE" not in serialized:
        raise RuntimeError("missing image did not require additional evidence")
    if "REQUIRE_MANAGER_REVIEW" not in serialized:
        raise RuntimeError("high-value case did not require manager review")

    retail = _login(
        pool,
        base_url=base_url,
        tenant_slug="csight-demo-retail",
        email="reviewer@csight-demo-retail.demo",
        password=password_value,
    )
    cross = pool.request(
        "GET",
        f"{url}/{run_id}",
        headers={"Authorization": f"Bearer {retail}"},
    )
    if cross.status != 404:
        raise RuntimeError("cross-tenant policy evaluation detail must be hidden")

    with factory() as session:
        event = session.scalar(
            select(PolicyEvaluationOutboxEventModel).where(
                PolicyEvaluationOutboxEventModel.policy_evaluation_run_id == run_id
            )
        )
        before = session.scalar(
            select(func.count(PolicyRuleEvaluationResultModel.id)).where(
                PolicyRuleEvaluationResultModel.policy_evaluation_run_id == run_id
            )
        )
    if event is None:
        raise RuntimeError("policy evaluation outbox event was not persisted")
    duplicate = build_execute_policy_evaluation(settings).execute(
        ExecutePolicyEvaluationCommand(
            event_id=str(event.id),
            tenant_id=str(event.tenant_id),
            case_id=str(event.case_id),
            policy_evaluation_run_id=run_id,
            correlation_id=event.correlation_id,
        )
    )
    with factory() as session:
        after = session.scalar(
            select(func.count(PolicyRuleEvaluationResultModel.id)).where(
                PolicyRuleEvaluationResultModel.policy_evaluation_run_id == run_id
            )
        )
    if duplicate != "NOOP" or before != after:
        raise RuntimeError("duplicate policy task changed append-only results")
    print(
        "POLICY_EVALUATION_SMOKE "
        f"run={run_id} rules={len(results)} replay=200 duplicate=NOOP "
        "cross_tenant=404 vision=NOT_EVALUATED missing_image=REQUIRE_ADDITIONAL_EVIDENCE "
        "high_value=REQUIRE_MANAGER_REVIEW forbidden_decision=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
