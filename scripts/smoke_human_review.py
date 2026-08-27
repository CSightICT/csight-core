"""Run an authenticated local Human Review API and persistence smoke flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import urllib3
from sqlalchemy import func, select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    HumanReviewActionModel,
    HumanReviewDecisionBasisModel,
    HumanReviewDecisionModel,
    HumanReviewPacketModel,
    HumanReviewRequestEventModel,
    HumanReviewTaskModel,
)
from app.adapters.persistence.session import create_session_factory
from app.application.human_review import HumanReviewRequestedCommand
from app.bootstrap.settings import Settings
from app.bootstrap.sprint5b import build_create_review_task


def _login(
    pool: urllib3.PoolManager,
    *,
    base_url: str,
    tenant: str,
    email: str,
    password: str,
) -> str:
    response = pool.request(
        "POST",
        f"{base_url}/api/v1/auth/token",
        json={"tenant_slug": tenant, "email": email, "password": password},
    )
    if response.status != 200:
        raise RuntimeError(f"human review login failed: {response.status}")
    return str(response.json()["access_token"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    base_url = arguments.base_url.rstrip("/")
    if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("human review smoke accepts only a local API URL")
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    admin_password = settings.development_seed_admin_password
    reviewer_password = settings.development_seed_reviewer_password
    viewer_password = settings.development_seed_quality_viewer_password
    if admin_password is None or reviewer_password is None or viewer_password is None:
        raise ValueError("development seed role passwords are required")
    passwords = {
        "admin": admin_password.get_secret_value(),
        "reviewer": reviewer_password.get_secret_value(),
        "viewer": viewer_password.get_secret_value(),
    }
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        task = session.scalar(
            select(HumanReviewTaskModel)
            .where(
                HumanReviewTaskModel.status == "PENDING",
                HumanReviewTaskModel.task_type == "MANAGER_REVIEW",
            )
            .order_by(HumanReviewTaskModel.created_at.desc())
            .limit(1)
        )
        request_event = (
            None
            if task is None
            else session.scalar(
                select(HumanReviewRequestEventModel).where(
                    HumanReviewRequestEventModel.policy_evaluation_run_id
                    == task.policy_evaluation_run_id
                )
            )
        )
    if task is None or request_event is None:
        raise RuntimeError(
            "a pending manager review task and its durable event are required; "
            "run policy smoke first"
        )
    pool = urllib3.PoolManager()
    tokens = {
        role: _login(
            pool,
            base_url=base_url,
            tenant="csight-demo-brand",
            email=f"{role}@csight-demo-brand.demo",
            password=passwords[role],
        )
        for role in ("admin", "reviewer", "viewer")
    }
    retail = _login(
        pool,
        base_url=base_url,
        tenant="csight-demo-retail",
        email="viewer@csight-demo-retail.demo",
        password=passwords["viewer"],
    )
    path = f"{base_url}/api/v1/human-review-tasks/{task.id}"
    headers = {role: {"Authorization": f"Bearer {token}"} for role, token in tokens.items()}
    viewer_detail = pool.request("GET", path, headers=headers["viewer"])
    if (
        viewer_detail.status != 200
        or pool.request(
            "POST", f"{path}/claim", headers=headers["viewer"], json={"expected_version": 1}
        ).status
        != 403
    ):
        raise RuntimeError("quality viewer read-only contract failed")
    if (
        pool.request(
            "POST", f"{path}/claim", headers=headers["reviewer"], json={"expected_version": 1}
        ).status
        != 403
    ):
        raise RuntimeError("reviewer must not claim manager review")
    if pool.request("GET", path, headers={"Authorization": f"Bearer {retail}"}).status != 404:
        raise RuntimeError("cross-tenant human review detail must be hidden")
    initial = viewer_detail.json()
    packet_hash = initial["packet"]["packet_hash"]
    rule_result_id = str(initial["rule_results"][0]["id"])
    replay_command = HumanReviewRequestedCommand(
        event_id=str(request_event.id),
        tenant_id=str(task.tenant_id),
        case_id=str(task.case_id),
        policy_evaluation_run_id=str(task.policy_evaluation_run_id),
        correlation_id=request_event.correlation_id,
    )
    creator = build_create_review_task(settings)
    if creator.execute(replay_command) != "NOOP" or creator.execute(replay_command) != "NOOP":
        raise RuntimeError("duplicate human review event was not a no-op")
    claim = pool.request(
        "POST", f"{path}/claim", headers=headers["admin"], json={"expected_version": 1}
    )
    if claim.status != 200:
        raise RuntimeError(f"admin manager claim failed: {claim.status}")
    if (
        pool.request(
            "POST", f"{path}/claim", headers=headers["admin"], json={"expected_version": 1}
        ).status
        != 409
    ):
        raise RuntimeError("duplicate claim must conflict")
    resolve_body = {
        "expected_version": 2,
        "decision": "APPROVE_REFUND",
        "reason_codes": ["POLICY_CONDITION_MET"],
        "rationale": "정책 평가 결과와 고정된 검토 근거를 확인하여 환불 요청을 승인합니다.",
        "basis": [{"type": "POLICY_RULE_RESULT", "reference_id": rule_result_id}],
    }
    resolved = pool.request("POST", f"{path}/resolve", headers=headers["admin"], json=resolve_body)
    if resolved.status != 200:
        raise RuntimeError(f"human decision resolve failed: {resolved.status}")
    if (
        pool.request("POST", f"{path}/resolve", headers=headers["admin"], json=resolve_body).status
        != 409
    ):
        raise RuntimeError("duplicate resolve must conflict")
    final = pool.request("GET", path, headers=headers["viewer"])
    serialized = json.dumps(final.json(), sort_keys=True)
    if final.status != 200 or final.json()["packet"]["packet_hash"] != packet_hash:
        raise RuntimeError("resolved detail or packet immutability failed")
    if any(
        value in serialized.lower() for value in ("raw_prompt", "raw_response", "reasoning", "jwt")
    ):
        raise RuntimeError("review detail exposed forbidden raw data")
    with factory() as session:
        counts = {
            "tasks": session.scalar(
                select(func.count(HumanReviewTaskModel.id)).where(
                    HumanReviewTaskModel.id == task.id
                )
            ),
            "packets": session.scalar(
                select(func.count(HumanReviewPacketModel.id)).where(
                    HumanReviewPacketModel.review_task_id == task.id
                )
            ),
            "created": session.scalar(
                select(func.count(HumanReviewActionModel.id)).where(
                    HumanReviewActionModel.review_task_id == task.id,
                    HumanReviewActionModel.action_type == "CREATED",
                )
            ),
            "claimed": session.scalar(
                select(func.count(HumanReviewActionModel.id)).where(
                    HumanReviewActionModel.review_task_id == task.id,
                    HumanReviewActionModel.action_type == "CLAIMED",
                )
            ),
            "resolved": session.scalar(
                select(func.count(HumanReviewActionModel.id)).where(
                    HumanReviewActionModel.review_task_id == task.id,
                    HumanReviewActionModel.action_type == "RESOLVED",
                )
            ),
            "decisions": session.scalar(
                select(func.count(HumanReviewDecisionModel.id)).where(
                    HumanReviewDecisionModel.review_task_id == task.id
                )
            ),
            "basis": session.scalar(
                select(func.count(HumanReviewDecisionBasisModel.id))
                .join(
                    HumanReviewDecisionModel,
                    HumanReviewDecisionModel.id
                    == HumanReviewDecisionBasisModel.human_review_decision_id,
                )
                .where(HumanReviewDecisionModel.review_task_id == task.id)
            ),
        }
    if counts != {
        "tasks": 1,
        "packets": 1,
        "created": 1,
        "claimed": 1,
        "resolved": 1,
        "decisions": 1,
        "basis": 1,
    }:
        raise RuntimeError(f"human review append-only counts failed: {counts}")
    print(
        "HUMAN_REVIEW_SMOKE task=1 packet=1 created=1 claimed=1 resolved=1 decision=1 "
        "basis=1 duplicate_event=NOOP duplicate_claim=409 duplicate_resolve=409 "
        "viewer_read=200 viewer_action=403 reviewer_manager_claim=403 cross_tenant=404"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
