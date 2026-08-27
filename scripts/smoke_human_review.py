"""Run an authenticated local Human Review API and persistence smoke flow."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import urllib3
from sqlalchemy import func, select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    CaseModel,
    CaseResolutionEventModel,
    CaseResolutionModel,
    CaseResolutionRequestEventModel,
    ExternalActionIntentModel,
    ExternalActionSimulationAttemptModel,
    ExternalActionSimulationRequestEventModel,
    ExternalActionSimulationResultModel,
    HumanReviewActionModel,
    HumanReviewDecisionBasisModel,
    HumanReviewDecisionModel,
    HumanReviewPacketModel,
    HumanReviewRequestEventModel,
    HumanReviewTaskModel,
    ReviewReportModel,
)
from app.adapters.persistence.session import create_session_factory
from app.application.case_resolution import (
    CaseResolutionRequestedCommand,
    ExternalActionSimulationRequestedCommand,
)
from app.application.human_review import HumanReviewRequestedCommand
from app.bootstrap.settings import Settings
from app.bootstrap.sprint5b import build_create_review_task
from app.bootstrap.sprint5c import (
    build_execute_external_action_simulation,
    build_process_case_resolution,
)


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
    with factory() as session:
        case = session.scalar(
            select(CaseModel).where(
                CaseModel.tenant_id == task.tenant_id,
                CaseModel.id == task.case_id,
            )
        )
    if case is None or case.attributes.get("external_action_input") != {
        "amount": "48000.0000",
        "currency": "KRW",
    }:
        raise RuntimeError(
            "the newest pending manager task must come from the current policy smoke with "
            "explicit Refund DRY-RUN input"
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
    case_path = f"{base_url}/api/v1/cases/{task.case_id}"
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
    case_before = pool.request("GET", case_path, headers=headers["viewer"])
    if case_before.status != 200:
        raise RuntimeError("source Case read failed before Resolution smoke")
    case_status_before = case_before.json()["status"]
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

    resolution_path = f"{case_path}/resolution"
    deadline = time.monotonic() + 60
    resolution: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = pool.request("GET", resolution_path, headers=headers["viewer"])
        if response.status == 200:
            resolution = response.json()
            if resolution.get("status") in {
                "ACTION_DRY_RUN_VALIDATED",
                "ACTION_DRY_RUN_FAILED",
                "ACTION_NEEDS_INPUT",
                "MANUAL_FOLLOW_UP_REQUIRED",
            }:
                break
        elif response.status != 404:
            raise RuntimeError(f"Resolution read failed: {response.status}")
        time.sleep(1)
    if resolution.get("status") != "ACTION_DRY_RUN_VALIDATED":
        raise RuntimeError(f"Refund DRY-RUN did not validate: {resolution}")
    if resolution.get("version") != 4:
        raise RuntimeError("Resolution did not record the four expected ordered versions")

    events_response = pool.request("GET", f"{resolution_path}/events", headers=headers["viewer"])
    intents_response = pool.request(
        "GET", f"{case_path}/external-action-intents", headers=headers["viewer"]
    )
    if events_response.status != 200 or intents_response.status != 200:
        raise RuntimeError("Resolution event or Action Intent read failed")
    events = events_response.json().get("items", [])
    intents = intents_response.json().get("items", [])
    if [item.get("sequence") for item in events] != [1, 2, 3, 4] or len(intents) != 1:
        raise RuntimeError("Resolution event ordering or Intent uniqueness failed")
    intent_id = str(intents[0]["id"])
    intent_response = pool.request(
        "GET",
        f"{base_url}/api/v1/external-action-intents/{intent_id}",
        headers=headers["viewer"],
    )
    if intent_response.status != 200:
        raise RuntimeError("Action Intent detail read failed")
    intent_detail = intent_response.json()
    if (
        len(intent_detail.get("attempts", [])) != 1
        or len(intent_detail.get("results", [])) != 1
        or intent_detail["results"][0].get("side_effects_performed") is not False
        or "execution_token" in json.dumps(intent_detail)
    ):
        raise RuntimeError("DRY-RUN uniqueness, safety, or public fencing contract failed")

    report = pool.request("GET", f"{case_path}/review-report", headers=headers["viewer"])
    metrics = pool.request(
        "GET", f"{base_url}/api/v1/metrics/poc-summary", headers=headers["viewer"]
    )
    if report.status != 200 or report.json().get("schema_version") != "review_report/1.0.0":
        raise RuntimeError("terminal immutable Review Report was not available")
    metric_names = {
        "review_time",
        "recommendation_difference_rate",
        "additional_evidence_request_rate",
        "action_input_missing_rate",
        "dry_run_success_rate",
        "analysis_failure_rate",
        "analysis_partial_success_rate",
    }
    if metrics.status != 200 or not metric_names <= set(metrics.json()):
        raise RuntimeError("PoC KPI response omitted required metrics")
    for name in metric_names:
        if not {"numerator", "denominator", "sample_count", "value", "unit"} <= set(
            metrics.json()[name]
        ):
            raise RuntimeError(f"PoC KPI {name} omitted evidence counts")
    if (
        pool.request("GET", resolution_path, headers={"Authorization": f"Bearer {retail}"}).status
        != 404
    ):
        raise RuntimeError("cross-tenant Resolution must be hidden")
    case_after = pool.request("GET", case_path, headers=headers["viewer"])
    if case_after.status != 200 or case_after.json()["status"] != case_status_before:
        raise RuntimeError("Resolution changed the Case lifecycle status")
    with factory() as session:
        resolution_row = session.scalar(
            select(CaseResolutionModel).where(
                CaseResolutionModel.tenant_id == task.tenant_id,
                CaseResolutionModel.case_id == task.case_id,
            )
        )
        resolution_request = session.scalar(
            select(CaseResolutionRequestEventModel).where(
                CaseResolutionRequestEventModel.tenant_id == task.tenant_id,
                CaseResolutionRequestEventModel.case_id == task.case_id,
            )
        )
        simulation_request = session.scalar(
            select(ExternalActionSimulationRequestEventModel)
            .join(
                ExternalActionIntentModel,
                ExternalActionIntentModel.id
                == ExternalActionSimulationRequestEventModel.external_action_intent_id,
            )
            .where(
                ExternalActionSimulationRequestEventModel.tenant_id == task.tenant_id,
                ExternalActionIntentModel.case_id == task.case_id,
            )
        )
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
            "resolution_events": session.scalar(
                select(func.count(CaseResolutionEventModel.id)).where(
                    CaseResolutionEventModel.tenant_id == task.tenant_id,
                    CaseResolutionEventModel.case_id == task.case_id,
                )
            ),
            "intents": session.scalar(
                select(func.count(ExternalActionIntentModel.id)).where(
                    ExternalActionIntentModel.tenant_id == task.tenant_id,
                    ExternalActionIntentModel.case_id == task.case_id,
                )
            ),
            "attempts": session.scalar(
                select(func.count(ExternalActionSimulationAttemptModel.id)).where(
                    ExternalActionSimulationAttemptModel.tenant_id == task.tenant_id,
                    ExternalActionSimulationAttemptModel.case_id == task.case_id,
                )
            ),
            "results": session.scalar(
                select(func.count(ExternalActionSimulationResultModel.id)).where(
                    ExternalActionSimulationResultModel.tenant_id == task.tenant_id,
                    ExternalActionSimulationResultModel.case_id == task.case_id,
                )
            ),
            "reports": session.scalar(
                select(func.count(ReviewReportModel.id)).where(
                    ReviewReportModel.tenant_id == task.tenant_id,
                    ReviewReportModel.case_id == task.case_id,
                )
            ),
        }
    if resolution_row is None or resolution_request is None or simulation_request is None:
        raise RuntimeError("Resolution smoke did not persist both durable requests")
    resolution_replay = build_process_case_resolution(settings).execute(
        CaseResolutionRequestedCommand(
            event_id=str(resolution_request.id),
            tenant_id=str(resolution_request.tenant_id),
            case_id=str(resolution_request.case_id),
            resolution_id=str(resolution_request.resolution_id),
            correlation_id=resolution_request.correlation_id,
        )
    )
    simulation_replay = build_execute_external_action_simulation(settings).execute(
        ExternalActionSimulationRequestedCommand(
            event_id=str(simulation_request.id),
            tenant_id=str(simulation_request.tenant_id),
            case_id=str(simulation_request.case_id),
            external_action_intent_id=str(simulation_request.external_action_intent_id),
            correlation_id=simulation_request.correlation_id,
        )
    )
    if counts != {
        "tasks": 1,
        "packets": 1,
        "created": 1,
        "claimed": 1,
        "resolved": 1,
        "decisions": 1,
        "basis": 1,
        "resolution_events": 4,
        "intents": 1,
        "attempts": 1,
        "results": 1,
        "reports": 1,
    }:
        raise RuntimeError(f"human review append-only counts failed: {counts}")
    if resolution_replay != "NOOP" or simulation_replay != "NOOP":
        raise RuntimeError("duplicate Resolution or simulation delivery was not a no-op")
    print(
        "HUMAN_REVIEW_SMOKE task=1 packet=1 created=1 claimed=1 resolved=1 decision=1 "
        "basis=1 duplicate_event=NOOP duplicate_claim=409 duplicate_resolve=409 "
        "viewer_read=200 viewer_action=403 reviewer_manager_claim=403 cross_tenant=404 "
        "resolution=ACTION_DRY_RUN_VALIDATED events=4 intent=1 attempt=1 result=1 report=1 "
        "side_effects=0 duplicate_resolution=NOOP duplicate_simulation=NOOP case_status=unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
