"""Internal rollout fields must not break or leak through the published run API."""

from datetime import UTC, date, datetime

import pytest

from app.interface.http.grounding_schemas import GroundedExplanationRunResponse
from app.interface.http.policy_query_run_schemas import PolicyRetrievalRunResponse
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.grounding import GroundedExplanationRun, GroundedExplanationRunStatus
from app.platform.query_builder import PolicyRetrievalRun, QueryStrategy, RetrievalRunStatus

pytestmark = pytest.mark.contract


@pytest.mark.parametrize("mode", list(AnalysisExecutionMode))
@pytest.mark.parametrize("route_id", [None, "internal-route-id"])
def test_retrieval_public_projection_preserves_contract(
    mode: AnalysisExecutionMode, route_id: str | None
) -> None:
    run = PolicyRetrievalRun(
        id="run",
        tenant_id="tenant",
        case_id="case",
        analysis_run_id="analysis",
        text_result_id="text",
        strategy=QueryStrategy.RAW,
        execution_mode=mode,
        model_route_plan_id=route_id,
        route_enforcement_contract_version="1.0.0" if route_id else None,
        status=RetrievalRunStatus.QUEUED,
        as_of_date=date(2026, 9, 10),
        top_k=3,
        idempotency_key="private-key",
        request_hash="a" * 64,
        correlation_id="correlation",
        created_at=datetime.now(UTC),
    )
    response = PolicyRetrievalRunResponse.from_run(run)
    payload = response.model_dump(mode="json")
    assert payload == run.model_dump(
        mode="json",
        exclude={
            "tenant_id",
            "text_result_id",
            "idempotency_key",
            "request_hash",
            "execution_mode",
            "model_route_plan_id",
            "route_enforcement_contract_version",
        },
    )
    assert PolicyRetrievalRunResponse.model_validate(payload) == response


@pytest.mark.parametrize("mode", list(AnalysisExecutionMode))
@pytest.mark.parametrize("route_id", [None, "internal-route-id"])
def test_grounding_public_projection_preserves_contract(
    mode: AnalysisExecutionMode, route_id: str | None
) -> None:
    run = GroundedExplanationRun(
        id="run",
        tenant_id="tenant",
        case_id="case",
        retrieval_run_id="retrieval",
        citation_pack_id="citation",
        execution_mode=mode,
        model_route_plan_id=route_id,
        route_enforcement_contract_version="1.0.0" if route_id else None,
        status=GroundedExplanationRunStatus.QUEUED,
        idempotency_key="private-key",
        request_hash="a" * 64,
        correlation_id="correlation",
        created_at=datetime.now(UTC),
    )
    response = GroundedExplanationRunResponse.from_run(run)
    payload = response.model_dump(mode="json")
    assert payload == run.model_dump(
        mode="json",
        exclude={
            "tenant_id",
            "idempotency_key",
            "request_hash",
            "execution_mode",
            "model_route_plan_id",
            "route_enforcement_contract_version",
        },
    )
    assert GroundedExplanationRunResponse.model_validate(payload) == response
