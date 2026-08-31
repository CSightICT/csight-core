"""HTTP contracts for tenant-scoped Sprint 2 analysis runs."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.application.analysis import (
    AnalysisRunDetail,
    AnalysisRunPage,
    ListAnalysisRunsQuery,
    StartTextAnalysisCommand,
    StartTextAnalysisResult,
)
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint1ServiceContainer, Sprint2ServiceContainer
from app.main import create_app
from app.platform.analysis import (
    AnalysisAdmissionLimitExceededError,
    AnalysisAttemptSummary,
    AnalysisExecutionMode,
    AnalysisFailure,
    AnalysisPipeline,
    AnalysisRun,
    AnalysisRunNotFoundError,
    AnalysisRunStatus,
    AnalysisStageRun,
    AnalysisStageStatus,
    AnalysisStageType,
    AnalysisTrigger,
    ExtractedRequestedAction,
    ExtractionIssueType,
    ImageQualityResult,
    ImageUsability,
    LLMExtractionResultRecord,
    LLMTextExtractionResult,
    ProviderExecutionMetadata,
    VisionAnalysisResult,
    VisionAnalysisResultRecord,
    VisionImageAssessment,
    VisionImageAssessmentOutcome,
)
from app.platform.analysis.errors import (
    AnalysisAlreadyTerminalError,
    AnalysisPipelineNotSupportedError,
)
from app.platform.case import Case, CaseStatus, CaseStatusTransition, RequestedAction
from app.platform.errors import (
    AuthenticationRequiredError,
    CaseNotFoundError,
    IdempotencyKeyReusedError,
)
from app.platform.evidence import EvidenceMetadata
from app.platform.model_routing import (
    ActiveModelRoutePlanRequiredError,
    ModelRouteActivationConflictError,
)
from app.platform.tenant import Permission, Principal, Role
from tests.case_assignment_support import AllowCaseAccess

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 26, 2, 3, 4, tzinfo=UTC)
_PRIVATE_IDEMPOTENCY_KEY = "private-analysis-idempotency-key"
_PRIVATE_CORRELATION_ID = "private-correlation-id"
_PRIVATE_FAILURE_MESSAGE = "private internal provider failure message"
_PRIVATE_PROVIDER_REQUEST_ID = "private-provider-request-id"


def _principal(role: Role, *, tenant_id: str = "tenant-a") -> Principal:
    return Principal(
        user_id=f"user-{role.value.lower()}",
        tenant_id=tenant_id,
        email=f"{role.value.lower()}@example.test",
        display_name=role.value.title(),
        roles=frozenset({role}),
    )


def _case(*, tenant_id: str = "tenant-a", case_id: str = "case-1") -> Case:
    return Case(
        id=case_id,
        tenant_id=tenant_id,
        status=CaseStatus.RECEIVED,
        order_ref="SYNTHETIC-ORDER-1",
        product_ref="SYNTHETIC-PRODUCT-1",
        customer_message="Private Case detail customer message",
        requested_action=RequestedAction.EXCHANGE,
        created_by="user-reviewer",
        created_at=NOW,
        updated_at=NOW,
    )


def _run(
    *,
    tenant_id: str = "tenant-a",
    case_id: str = "case-1",
    analysis_run_id: str = "run-1",
    failed: bool = False,
) -> AnalysisRun:
    failure = (
        AnalysisFailure(
            code="LLM_PROVIDER_UNAVAILABLE",
            message=_PRIVATE_FAILURE_MESSAGE,
            retryable=True,
        )
        if failed
        else None
    )
    return AnalysisRun(
        id=analysis_run_id,
        tenant_id=tenant_id,
        case_id=case_id,
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version="1.0.0",
        trigger=AnalysisTrigger.USER_REQUEST,
        status=AnalysisRunStatus.FAILED if failed else AnalysisRunStatus.QUEUED,
        requested_by="user-reviewer",
        correlation_id=_PRIVATE_CORRELATION_ID,
        idempotency_key=_PRIVATE_IDEMPOTENCY_KEY,
        request_hash="a" * 64,
        requested_at=NOW,
        started_at=NOW if failed else None,
        completed_at=NOW + timedelta(seconds=1) if failed else None,
        failure=failure,
        created_at=NOW,
        updated_at=NOW + timedelta(seconds=1) if failed else NOW,
    )


def _stage(*, failed: bool = True) -> AnalysisStageRun:
    failure = (
        AnalysisFailure(
            code="LLM_PROVIDER_UNAVAILABLE",
            message=_PRIVATE_FAILURE_MESSAGE,
            retryable=True,
        )
        if failed
        else None
    )
    return AnalysisStageRun(
        id="stage-1",
        tenant_id="tenant-a",
        analysis_run_id="failed-run" if failed else "run-1",
        stage_type=AnalysisStageType.TEXT_EXTRACTION,
        status=AnalysisStageStatus.FAILED if failed else AnalysisStageStatus.SUCCEEDED,
        attempt_summary=AnalysisAttemptSummary(
            attempt_count=1,
            last_attempt_started_at=NOW,
            last_attempt_completed_at=NOW + timedelta(seconds=1),
        ),
        provider_name="vllm",
        model_name="configured/model",
        model_version="deployment-v3",
        model_revision="revision-a1",
        provider_execution=ProviderExecutionMetadata(
            provider_name="vllm",
            model_name="configured/model",
            model_version="deployment-v3",
            model_revision="revision-a1",
            provider_request_id=_PRIVATE_PROVIDER_REQUEST_ID,
            input_token_count=100,
            output_token_count=25,
            latency_ms=123,
        ),
        prompt_name="product_defect_text_extraction",
        prompt_version="1.0.0",
        prompt_content_hash="b" * 64,
        input_schema_version="1.0",
        output_schema_version="1.0",
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        failure=failure,
        created_at=NOW,
        updated_at=NOW + timedelta(seconds=1),
    )


def _extraction_record() -> LLMExtractionResultRecord:
    return LLMExtractionResultRecord(
        id="extraction-1",
        tenant_id="tenant-a",
        analysis_run_id="failed-run",
        stage_run_id="stage-1",
        result=LLMTextExtractionResult(
            language="en",
            issue_types=(ExtractionIssueType.LEAKAGE,),
            requested_action=ExtractedRequestedAction.EXCHANGE,
            summary="Synthetic normalized extraction summary.",
        ),
        created_at=NOW + timedelta(seconds=1),
    )


def _binary_vision_record() -> VisionAnalysisResultRecord:
    return VisionAnalysisResultRecord(
        id="vision-result-1",
        tenant_id="tenant-a",
        analysis_run_id="binary-run",
        stage_run_id="vision-stage-1",
        evidence_id="evidence-1",
        result=VisionAnalysisResult(
            provider_name="mock",
            model_name="csight-mock-vision",
            model_version="synthetic-contract-v1",
            dataset_version="synthetic-any-defect-v1",
            taxonomy_version="csight-any-defect-assessment-v1",
            threshold_version="synthetic-mock-any-defect-threshold-v1",
            preprocess_version="synthetic-v1",
            postprocess_version="synthetic-v1",
            image_width=100,
            image_height=100,
            image_quality=ImageQualityResult(usable=ImageUsability.NOT_EVALUATED),
            detections=(),
            image_assessment=VisionImageAssessment(
                score=0.95,
                threshold=0.8984375,
                outcome=VisionImageAssessmentOutcome.HIGH_CONFIDENCE_DEFECT_CANDIDATE,
            ),
            latency_ms=20,
        ),
        created_at=NOW,
    )


class _ResolvePrincipal:
    def execute(self, token: str) -> Principal:
        principals = {
            "admin-token": _principal(Role.ADMIN),
            "reviewer-token": _principal(Role.REVIEWER),
            "viewer-token": _principal(Role.QUALITY_VIEWER),
        }
        try:
            return principals[token]
        except KeyError as error:
            raise AuthenticationRequiredError() from error


class _GetCase:
    def execute(self, *, principal: Principal, case_id: str) -> Case:
        principal.require(Permission.CASE_READ)
        if case_id == "missing-case":
            raise CaseNotFoundError()
        return _case(tenant_id=principal.tenant_id, case_id=case_id)


class _GetCaseHistory:
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
    ) -> tuple[CaseStatusTransition, ...]:
        principal.require(Permission.CASE_READ)
        return ()


class _ListCaseEvidence:
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
    ) -> tuple[EvidenceMetadata, ...]:
        principal.require(Permission.CASE_READ)
        return ()


@dataclass(slots=True)
class _StartTextAnalysis:
    commands: list[StartTextAnalysisCommand] = field(default_factory=list)
    principals: list[Principal] = field(default_factory=list)

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        command: StartTextAnalysisCommand,
    ) -> StartTextAnalysisResult:
        principal.require(Permission.ANALYSIS_CREATE)
        self.principals.append(principal)
        self.commands.append(command)
        if case_id == "missing-case":
            raise CaseNotFoundError()
        if command.idempotency_key == "conflict-key":
            raise IdempotencyKeyReusedError()
        if command.idempotency_key == "terminal-key":
            raise AnalysisAlreadyTerminalError()
        if command.idempotency_key == "quota-key":
            raise AnalysisAdmissionLimitExceededError(
                global_nonterminal=4,
                tenant_nonterminal=2,
                global_limit=4,
                tenant_limit=4,
                retry_after_seconds=5,
            )
        if command.idempotency_key == "missing-route-key":
            raise ActiveModelRoutePlanRequiredError()
        if command.idempotency_key == "stale-route-key":
            raise ModelRouteActivationConflictError()
        if command.pipeline_version == "unsupported":
            raise AnalysisPipelineNotSupportedError()
        return StartTextAnalysisResult(
            run=_run(tenant_id=principal.tenant_id, case_id=case_id).model_copy(
                update={"execution_mode": command.execution_mode}
            ),
            replayed=command.idempotency_key == "replay-key",
        )


@dataclass(slots=True)
class _ListAnalysisRuns:
    queries: list[ListAnalysisRunsQuery] = field(default_factory=list)

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        query: ListAnalysisRunsQuery,
    ) -> AnalysisRunPage:
        principal.require(Permission.ANALYSIS_READ)
        if case_id == "missing-case":
            raise CaseNotFoundError()
        self.queries.append(query)
        return AnalysisRunPage(
            items=(_run(tenant_id=principal.tenant_id, case_id=case_id),),
            page=query.page,
            page_size=query.page_size,
            total=1,
        )


class _GetAnalysisRun:
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        analysis_run_id: str,
    ) -> AnalysisRunDetail:
        principal.require(Permission.ANALYSIS_READ)
        if analysis_run_id == "missing-run":
            raise AnalysisRunNotFoundError()
        if analysis_run_id == "terminal-run":
            raise AnalysisAlreadyTerminalError()
        failed = analysis_run_id == "failed-run"
        return AnalysisRunDetail(
            run=_run(
                tenant_id=principal.tenant_id,
                case_id=case_id,
                analysis_run_id=analysis_run_id,
                failed=failed,
            ),
            stages=(_stage(failed=failed),),
            extraction_result=_extraction_record() if failed else None,
            vision_results=((_binary_vision_record(),) if analysis_run_id == "binary-run" else ()),
        )


class _GetLatestAnalysisRun:
    def execute(self, *, principal: Principal, case_id: str) -> AnalysisRun | None:
        principal.require(Permission.ANALYSIS_READ)
        if case_id == "no-analysis-case":
            return None
        return _run(tenant_id=principal.tenant_id, case_id=case_id)


@dataclass(slots=True)
class _HTTPContext:
    client: TestClient
    start: _StartTextAnalysis
    list_runs: _ListAnalysisRuns


def _sprint1_services() -> Sprint1ServiceContainer:
    unused: Any = object()
    return Sprint1ServiceContainer(
        authenticate_user=unused,
        resolve_principal=_ResolvePrincipal(),
        create_case=unused,
        list_cases=unused,
        get_case=_GetCase(),
        get_case_status_history=_GetCaseHistory(),
        add_image_evidence=unused,
        list_case_evidence=_ListCaseEvidence(),
        get_evidence_metadata=unused,
        create_evidence_access_url=unused,
        get_case_assignment=unused,
        assign_case=unused,
        authorize_case_access=AllowCaseAccess(),  # pyright: ignore[reportArgumentType]
    )


def _build_context(*, sprint2_enabled: bool = True) -> _HTTPContext:
    start = _StartTextAnalysis()
    list_runs = _ListAnalysisRuns()
    sprint2_services = (
        Sprint2ServiceContainer(
            start_text_analysis=start,
            list_analysis_runs=list_runs,
            get_analysis_run=_GetAnalysisRun(),
            get_latest_analysis_run=_GetLatestAnalysisRun(),
        )
        if sprint2_enabled
        else None
    )
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    application = create_app(
        settings,
        sprint1_services=_sprint1_services(),
        sprint2_services=sprint2_services,
    )
    return _HTTPContext(
        client=TestClient(application),
        start=start,
        list_runs=list_runs,
    )


@pytest.fixture
def context() -> _HTTPContext:
    return _build_context()


def _authorization(role: Role = Role.REVIEWER) -> dict[str, str]:
    tokens = {
        Role.ADMIN: "admin-token",
        Role.REVIEWER: "reviewer-token",
        Role.QUALITY_VIEWER: "viewer-token",
    }
    return {"Authorization": f"Bearer {tokens[role]}"}


def _start_body(*, pipeline_version: str = "1.0.0") -> dict[str, object]:
    return {
        "pipeline": "product_defect_text_extraction",
        "pipeline_version": pipeline_version,
    }


@pytest.mark.parametrize("role", [Role.ADMIN, Role.REVIEWER])
def test_admin_and_reviewer_can_start_with_required_idempotency_contract(
    context: _HTTPContext,
    role: Role,
) -> None:
    response = context.client.post(
        "/api/v1/cases/case-1/analysis-runs",
        headers={
            **_authorization(role),
            "Idempotency-Key": _PRIVATE_IDEMPOTENCY_KEY,
            "X-Correlation-ID": "corr-analysis-http",
        },
        json=_start_body(),
    )

    assert response.status_code == 202
    assert response.headers["Location"] == "/api/v1/cases/case-1/analysis-runs/run-1"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.json()["analysis_run_id"] == "run-1"
    assert response.json()["status"] == "QUEUED"
    assert response.json()["execution_mode"] == "PRIMARY"
    command = context.start.commands[-1]
    assert command.pipeline is AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION
    assert command.pipeline_version == "1.0.0"
    assert command.idempotency_key == _PRIVATE_IDEMPOTENCY_KEY
    assert command.correlation_id == "corr-analysis-http"
    assert context.start.principals[-1].tenant_id == "tenant-a"
    assert "idempotency_key" not in response.text
    assert "request_hash" not in response.text
    assert "correlation_id" not in response.text
    assert _PRIVATE_IDEMPOTENCY_KEY not in response.text


def test_start_accepts_explicit_shadow_mode_without_changing_permissions(
    context: _HTTPContext,
) -> None:
    response = context.client.post(
        "/api/v1/cases/case-1/analysis-runs",
        headers={**_authorization(Role.REVIEWER), "Idempotency-Key": "shadow-key"},
        json={**_start_body(), "execution_mode": "SHADOW"},
    )

    assert response.status_code == 202
    assert response.json()["execution_mode"] == "SHADOW"
    assert context.start.commands[-1].execution_mode is AnalysisExecutionMode.SHADOW


def test_admission_limit_is_429_with_retry_after(context: _HTTPContext) -> None:
    response = context.client.post(
        "/api/v1/cases/case-1/analysis-runs",
        headers={**_authorization(), "Idempotency-Key": "quota-key"},
        json=_start_body(),
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "5"
    assert response.json()["error"]["code"] == "ANALYSIS_ADMISSION_LIMIT_EXCEEDED"
    assert response.json()["error"]["details"] == {
        "global_nonterminal": 4,
        "tenant_nonterminal": 2,
        "global_limit": 4,
        "tenant_limit": 4,
    }


def test_start_replay_is_200_and_invalid_idempotency_inputs_do_not_reach_service(
    context: _HTTPContext,
) -> None:
    replay = context.client.post(
        "/api/v1/cases/case-1/analysis-runs",
        headers={**_authorization(), "Idempotency-Key": "replay-key"},
        json=_start_body(),
    )
    command_count = len(context.start.commands)
    missing = context.client.post(
        "/api/v1/cases/case-1/analysis-runs",
        headers=_authorization(),
        json=_start_body(),
    )
    tenant_injection = context.client.post(
        "/api/v1/cases/case-1/analysis-runs",
        headers={**_authorization(), "Idempotency-Key": "tenant-injection"},
        json={**_start_body(), "tenant_id": "tenant-b"},
    )
    blank_key = context.client.post(
        "/api/v1/cases/case-1/analysis-runs",
        headers={**_authorization(), "Idempotency-Key": "   "},
        json=_start_body(),
    )

    assert replay.status_code == 200
    assert replay.headers["Location"].endswith("/analysis-runs/run-1")
    assert missing.status_code == 422
    assert tenant_injection.status_code == 422
    assert blank_key.status_code == 422
    assert missing.json()["error"]["code"] == "VALIDATION_ERROR"
    assert tenant_injection.json()["error"]["code"] == "VALIDATION_ERROR"
    assert len(context.start.commands) == command_count


def test_quality_viewer_cannot_create_but_all_roles_can_read(context: _HTTPContext) -> None:
    forbidden = context.client.post(
        "/api/v1/cases/case-1/analysis-runs",
        headers={
            **_authorization(Role.QUALITY_VIEWER),
            "Idempotency-Key": "viewer-key",
        },
        json=_start_body(),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    for role in Role:
        listed = context.client.get(
            "/api/v1/cases/case-1/analysis-runs",
            headers=_authorization(role),
        )
        detail = context.client.get(
            "/api/v1/cases/case-1/analysis-runs/run-1",
            headers=_authorization(role),
        )
        assert listed.status_code == 200
        assert detail.status_code == 200


def test_analysis_list_filters_are_typed_and_tenant_cannot_be_injected(
    context: _HTTPContext,
) -> None:
    response = context.client.get(
        "/api/v1/cases/case-1/analysis-runs",
        headers=_authorization(Role.QUALITY_VIEWER),
        params={
            "status": "QUEUED",
            "pipeline": "product_defect_text_extraction",
            "page": 2,
            "page_size": 5,
        },
    )
    injected = context.client.get(
        "/api/v1/cases/case-1/analysis-runs",
        headers=_authorization(),
        params={"tenant_id": "tenant-b"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["page"] == 2
    assert response.json()["page_size"] == 5
    query = context.list_runs.queries[-1]
    assert query.status is AnalysisRunStatus.QUEUED
    assert query.pipeline is AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION
    assert query.page == 2
    assert query.page_size == 5
    assert injected.status_code == 422
    assert injected.json()["error"]["code"] == "VALIDATION_ERROR"


def test_analysis_detail_exposes_only_normalized_results_and_safe_audit_metadata(
    context: _HTTPContext,
) -> None:
    response = context.client.get(
        "/api/v1/cases/case-1/analysis-runs/failed-run",
        headers=_authorization(Role.QUALITY_VIEWER),
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["run"]["failure"] == {
        "code": "LLM_PROVIDER_UNAVAILABLE",
        "retryable": True,
    }
    stage = body["stages"][0]
    assert stage["attempt_count"] == 1
    assert stage["provider_name"] == "vllm"
    assert stage["model_version"] == "deployment-v3"
    assert stage["prompt_version"] == "1.0.0"
    assert stage["prompt_content_hash"] == "b" * 64
    assert stage["input_schema_version"] == "1.0"
    assert stage["output_schema_version"] == "1.0"
    assert stage["provider_execution"]["latency_ms"] == 123
    assert body["extraction_result"]["result"]["issue_types"] == ["LEAKAGE"]
    for private_value in (
        _PRIVATE_IDEMPOTENCY_KEY,
        _PRIVATE_CORRELATION_ID,
        _PRIVATE_FAILURE_MESSAGE,
        _PRIVATE_PROVIDER_REQUEST_ID,
    ):
        assert private_value not in response.text
    for forbidden_name in (
        "idempotency_key",
        "request_hash",
        "correlation_id",
        "claim_token",
        "provider_request_id",
        "system_template",
        "user_template",
    ):
        assert forbidden_name not in response.text


def test_analysis_detail_exposes_binary_assessment_without_bbox_or_defect_type(
    context: _HTTPContext,
) -> None:
    response = context.client.get(
        "/api/v1/cases/case-1/analysis-runs/binary-run",
        headers=_authorization(Role.QUALITY_VIEWER),
    )

    assert response.status_code == 200
    result = response.json()["vision_results"][0]["result"]
    assert result["detections"] == []
    assert result["image_assessment"] == {
        "assessment_type": "ANY_DEFECT",
        "model_output_name": "defect",
        "score": 0.95,
        "threshold": 0.8984375,
        "threshold_operator": "GREATER_THAN_OR_EQUAL",
        "outcome": "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
    }
    assert "canonical_label" not in response.text
    assert "geometry" not in response.text


@pytest.mark.parametrize(
    ("method", "path", "headers", "json_body", "status_code", "error_code"),
    [
        (
            "GET",
            "/api/v1/cases/case-1/analysis-runs/missing-run",
            _authorization(),
            None,
            404,
            "ANALYSIS_RUN_NOT_FOUND",
        ),
        (
            "GET",
            "/api/v1/cases/case-1/analysis-runs/terminal-run",
            _authorization(),
            None,
            409,
            "ANALYSIS_ALREADY_TERMINAL",
        ),
        (
            "POST",
            "/api/v1/cases/case-1/analysis-runs",
            {**_authorization(), "Idempotency-Key": "unsupported-key"},
            _start_body(pipeline_version="unsupported"),
            422,
            "ANALYSIS_PIPELINE_NOT_SUPPORTED",
        ),
        (
            "POST",
            "/api/v1/cases/case-1/analysis-runs",
            {**_authorization(), "Idempotency-Key": "terminal-key"},
            _start_body(),
            409,
            "ANALYSIS_ALREADY_TERMINAL",
        ),
        (
            "POST",
            "/api/v1/cases/case-1/analysis-runs",
            {**_authorization(), "Idempotency-Key": "conflict-key"},
            _start_body(),
            409,
            "IDEMPOTENCY_KEY_REUSED",
        ),
        (
            "POST",
            "/api/v1/cases/case-1/analysis-runs",
            {**_authorization(), "Idempotency-Key": "missing-route-key"},
            _start_body(pipeline_version="2.0.0"),
            503,
            "ACTIVE_MODEL_ROUTE_PLAN_REQUIRED",
        ),
        (
            "POST",
            "/api/v1/cases/case-1/analysis-runs",
            {**_authorization(), "Idempotency-Key": "stale-route-key"},
            _start_body(pipeline_version="2.0.0"),
            409,
            "MODEL_ROUTE_ACTIVATION_CONFLICT",
        ),
    ],
)
def test_analysis_errors_use_stable_safe_http_envelopes(
    context: _HTTPContext,
    method: str,
    path: str,
    headers: dict[str, str],
    json_body: dict[str, object] | None,
    status_code: int,
    error_code: str,
) -> None:
    response = context.client.request(method, path, headers=headers, json=json_body)

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == error_code
    assert response.json()["error"]["correlation_id"]
    assert _PRIVATE_FAILURE_MESSAGE not in response.text


def test_case_detail_is_sprint1_compatible_and_optionally_includes_latest_run() -> None:
    sprint1_only = _build_context(sprint2_enabled=False)
    without_analysis = sprint1_only.client.get(
        "/api/v1/cases/case-1",
        headers=_authorization(),
    )
    unavailable_analysis = sprint1_only.client.get(
        "/api/v1/cases/case-1/analysis-runs",
        headers=_authorization(),
    )
    with_analysis = _build_context().client.get(
        "/api/v1/cases/case-1",
        headers=_authorization(Role.QUALITY_VIEWER),
    )

    assert without_analysis.status_code == 200
    assert without_analysis.json()["latest_analysis_run"] is None
    assert unavailable_analysis.status_code == 503
    assert unavailable_analysis.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert with_analysis.status_code == 200
    assert with_analysis.json()["latest_analysis_run"]["analysis_run_id"] == "run-1"
    assert "idempotency_key" not in with_analysis.text


def _schema_property_names(schema: object, document: dict[str, object]) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    reference = schema.get("$ref")
    if isinstance(reference, str):
        current: object = document
        for component in reference.removeprefix("#/").split("/"):
            if not isinstance(current, dict):
                return set()
            current = current.get(component)
        return _schema_property_names(current, document)
    names: set[str] = set()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        names.update(str(name) for name in properties)
        for nested in properties.values():
            names.update(_schema_property_names(nested, document))
    for keyword in ("allOf", "anyOf", "oneOf", "items"):
        nested = schema.get(keyword)
        if isinstance(nested, list):
            for item in nested:
                names.update(_schema_property_names(item, document))
        else:
            names.update(_schema_property_names(nested, document))
    return names


def test_openapi_declares_required_key_tenant_free_inputs_and_safe_outputs(
    context: _HTTPContext,
) -> None:
    document = context.client.get("/openapi.json").json()
    path = document["paths"]["/api/v1/cases/{case_id}/analysis-runs"]
    post = path["post"]
    parameters = {parameter["name"]: parameter for parameter in post["parameters"]}
    assert parameters["Idempotency-Key"]["required"] is True
    assert post["responses"]["202"]["headers"].keys() >= {"Location", "Cache-Control"}
    assert post["responses"].keys() >= {"200", "202", "404", "409", "422", "429", "503"}
    assert "Retry-After" in post["responses"]["429"]["headers"]
    assert path["get"]["responses"].keys() >= {"200", "401", "403", "404", "422", "503"}

    request_schema = post["requestBody"]["content"]["application/json"]["schema"]
    request_names = _schema_property_names(request_schema, document)
    assert request_names == {"pipeline", "pipeline_version", "execution_mode"}

    response_schema = post["responses"]["202"]["content"]["application/json"]["schema"]
    response_names = _schema_property_names(response_schema, document)
    detail_schema = document["paths"]["/api/v1/cases/{case_id}/analysis-runs/{analysis_run_id}"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["schema"]
    response_names.update(_schema_property_names(detail_schema, document))
    assessment_schema = document["components"]["schemas"]["VisionImageAssessment"]
    assert set(assessment_schema["properties"]) == {
        "assessment_type",
        "model_output_name",
        "score",
        "threshold",
        "threshold_operator",
        "outcome",
    }
    outcome_schema = document["components"]["schemas"]["VisionImageAssessmentOutcome"]
    assert "NORMAL" not in outcome_schema["enum"]
    assert (
        not {
            "idempotency_key",
            "request_hash",
            "correlation_id",
            "claim_token",
            "provider_request_id",
            "message",
            "system_template",
            "user_template",
        }
        & response_names
    )


def test_analysis_role_permissions_are_explicit() -> None:
    for role in (Role.ADMIN, Role.REVIEWER):
        principal = _principal(role)
        assert principal.has_permission(Permission.ANALYSIS_CREATE)
        assert principal.has_permission(Permission.ANALYSIS_READ)

    viewer = _principal(Role.QUALITY_VIEWER)
    assert not viewer.has_permission(Permission.ANALYSIS_CREATE)
    assert viewer.has_permission(Permission.ANALYSIS_READ)
