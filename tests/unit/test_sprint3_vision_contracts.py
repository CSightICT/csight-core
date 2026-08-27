"""Sprint 3 canonical Vision, snapshot, fan-out, and join unit contracts."""

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from urllib3.response import BaseHTTPResponse

from app.adapters.llm import MockLLMProvider
from app.adapters.vision import (
    MockVisionProvider,
    RemoteVisionProvider,
    VisionMockMode,
    map_model_class,
)
from app.application.analysis import (
    StartTextAnalysis,
    StartTextAnalysisCommand,
    aggregate_run_status,
)
from app.domains.product_defect_cs import PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT
from app.platform.analysis import (
    MULTIMODAL_ANALYSIS_PIPELINE_VERSION,
    AnalysisAttemptSummary,
    AnalysisPipeline,
    AnalysisRequestIdempotencyRecord,
    AnalysisRunStatus,
    AnalysisStageRun,
    AnalysisStageStatus,
    AnalysisStageType,
    BoundingBox,
    CoordinateSystem,
    DefectType,
    ImageEvidenceRequiredError,
    ImageQualityResult,
    ImageUsability,
    VisionAnalysisRequest,
    VisionAnalysisResult,
    VisionImageAssessment,
    VisionImageAssessmentOutcome,
    VisionInvalidStructuredOutputError,
    VisionProviderAuthenticationError,
    VisionProviderRequestRejectedError,
    VisionProviderTimeoutError,
    VisionProviderUnavailableError,
    VisionTask,
)
from app.platform.case import Case, RequestedAction
from app.platform.evidence import EvidenceMetadata, EvidenceUploadStatus
from app.platform.tenant import Principal, Role
from app.ports.analysis_repository import AnalysisRequestIdempotencyClaim, AnalysisUnitOfWorkFactory

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Ids:
    def __init__(self, values: Iterable[str]) -> None:
        self._values = iter(values)

    def new_id(self) -> str:
        return next(self._values)


def _stage(stage_type: AnalysisStageType, status: AnalysisStageStatus) -> AnalysisStageRun:
    return AnalysisStageRun(
        id=f"stage-{stage_type.value}",
        tenant_id="tenant-1",
        analysis_run_id="run-1",
        stage_type=stage_type,
        status=status,
        attempt_summary=AnalysisAttemptSummary(),
        provider_name="mock",
        model_name="model",
        model_version="1",
        prompt_name="none",
        prompt_version="none",
        prompt_content_hash="0" * 64,
        input_schema_version="1.0",
        output_schema_version="1.0",
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    ("text", "vision", "expected"),
    [
        (AnalysisStageStatus.SUCCEEDED, AnalysisStageStatus.SUCCEEDED, AnalysisRunStatus.SUCCEEDED),
        (
            AnalysisStageStatus.SUCCEEDED,
            AnalysisStageStatus.FAILED,
            AnalysisRunStatus.PARTIAL_SUCCESS,
        ),
        (
            AnalysisStageStatus.FAILED,
            AnalysisStageStatus.SUCCEEDED,
            AnalysisRunStatus.PARTIAL_SUCCESS,
        ),
        (AnalysisStageStatus.FAILED, AnalysisStageStatus.FAILED, AnalysisRunStatus.FAILED),
        (AnalysisStageStatus.SUCCEEDED, AnalysisStageStatus.RUNNING, AnalysisRunStatus.RUNNING),
        (
            AnalysisStageStatus.SUCCEEDED,
            AnalysisStageStatus.RETRY_WAITING,
            AnalysisRunStatus.RETRY_WAITING,
        ),
    ],
)
def test_join_aggregates_stage_terminal_and_retry_states(
    text: AnalysisStageStatus,
    vision: AnalysisStageStatus,
    expected: AnalysisRunStatus,
) -> None:
    assert (
        aggregate_run_status(
            (
                _stage(AnalysisStageType.TEXT_EXTRACTION, text),
                _stage(AnalysisStageType.VISION_ANALYSIS, vision),
            )
        )
        is expected
    )


def test_bbox_and_quality_distinguish_normalized_geometry_from_not_evaluated() -> None:
    box = BoundingBox(
        coordinate_system=CoordinateSystem.NORMALIZED_XYXY,
        x1=0.1,
        y1=0.2,
        x2=0.8,
        y2=0.9,
    )
    quality = ImageQualityResult(usable=ImageUsability.NOT_EVALUATED)

    assert box.coordinate_system is CoordinateSystem.NORMALIZED_XYXY
    assert quality.score is None
    with pytest.raises(ValueError, match="x2"):
        BoundingBox(x1=0.8, y1=0.2, x2=0.1, y2=0.9)
    with pytest.raises(ValueError, match="remain null"):
        ImageQualityResult(usable=ImageUsability.NOT_EVALUATED, blurred=False)


def test_image_assessment_is_non_localizing_and_below_threshold_is_not_normal() -> None:
    below = VisionImageAssessment(
        score=0.4,
        threshold=0.8,
        outcome=VisionImageAssessmentOutcome.BELOW_HIGH_CONFIDENCE_THRESHOLD,
    )

    assert "NORMAL" not in {item.value for item in VisionImageAssessmentOutcome}
    assert below.outcome is VisionImageAssessmentOutcome.BELOW_HIGH_CONFIDENCE_THRESHOLD
    with pytest.raises(ValueError, match="outcome"):
        VisionImageAssessment(
            score=0.9,
            threshold=0.8,
            outcome=VisionImageAssessmentOutcome.BELOW_HIGH_CONFIDENCE_THRESHOLD,
        )


def test_image_assessment_cannot_claim_a_localized_detection() -> None:
    detection_result = MockVisionProvider().analyze_image(
        VisionAnalysisRequest(
            evidence_id="evidence-1",
            content_type="image/png",
            image_width=100,
            image_height=100,
        ),
        image=b"synthetic-image",
    )
    with pytest.raises(ValueError, match="separate modes"):
        VisionAnalysisResult.model_validate(
            {
                **detection_result.model_dump(mode="json"),
                "image_assessment": {
                    "score": 0.95,
                    "threshold": 0.9,
                    "outcome": "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
                },
            }
        )


def test_kaputt_native_taxonomy_is_mapped_without_exposing_class_ids() -> None:
    assert map_model_class("spillage") is DefectType.LEAKAGE
    assert map_model_class("deformation") is DefectType.DENT
    assert map_model_class("superficial") is DefectType.SURFACE_DAMAGE
    assert map_model_class("not-a-real-class") is DefectType.UNKNOWN


def _principal() -> Principal:
    return Principal(
        user_id="user-1",
        tenant_id="tenant-1",
        email="reviewer@example.com",
        display_name="Reviewer",
        roles=frozenset({Role.REVIEWER}),
    )


def _case() -> Case:
    return Case.create(
        case_id="case-1",
        tenant_id="tenant-1",
        order_ref="order-1",
        product_ref="product-1",
        customer_message="제품이 손상되었습니다.",
        requested_action=RequestedAction.EXCHANGE,
        attributes={},
        created_by="user-1",
        now=NOW,
    )


def _evidence() -> EvidenceMetadata:
    return EvidenceMetadata(
        id="evidence-1",
        tenant_id="tenant-1",
        case_id="case-1",
        upload_status=EvidenceUploadStatus.AVAILABLE,
        storage_bucket="evidence",
        object_key="tenants/tenant-1/cases/case-1/evidence/evidence-1/original",
        original_filename="synthetic.png",
        content_type="image/png",
        size_bytes=3,
        sha256=hashlib.sha256(b"img").hexdigest(),
        width=32,
        height=24,
        created_by="user-1",
        created_at=NOW,
        updated_at=NOW,
    )


def _uow_factory(
    *, evidence: tuple[EvidenceMetadata, ...]
) -> tuple[AnalysisUnitOfWorkFactory, MagicMock]:
    uow = MagicMock()
    uow.__enter__.return_value = uow
    uow.__exit__.return_value = None
    uow.cases.get.return_value = _case()
    uow.evidence.list.return_value = evidence

    def claim(
        *, tenant_id: str, record: AnalysisRequestIdempotencyRecord
    ) -> AnalysisRequestIdempotencyClaim:
        del tenant_id
        return AnalysisRequestIdempotencyClaim(claimed=True, record=record)

    uow.request_idempotency.claim.side_effect = claim
    factory = cast(AnalysisUnitOfWorkFactory, MagicMock(return_value=uow))
    return factory, uow


def test_multimodal_start_creates_two_stages_two_events_and_stable_snapshot() -> None:
    factory, uow = _uow_factory(evidence=(_evidence(),))
    service = StartTextAnalysis(
        uow_factory=factory,
        provider=MockLLMProvider(),
        vision_provider=MockVisionProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=_Clock(),
        id_generator=_Ids(f"id-{index}" for index in range(8)),
    )

    result = service.execute(
        principal=_principal(),
        case_id="case-1",
        command=StartTextAnalysisCommand(
            pipeline=AnalysisPipeline.PRODUCT_DEFECT_MULTIMODAL_ANALYSIS,
            pipeline_version=MULTIMODAL_ANALYSIS_PIPELINE_VERSION,
            idempotency_key="key-1",
            correlation_id="correlation-1",
        ),
    )

    assert result.run.pipeline is AnalysisPipeline.PRODUCT_DEFECT_MULTIMODAL_ANALYSIS
    assert uow.stage_runs.add.call_count == 2
    assert uow.outbox.add.call_count == 2
    snapshot = uow.evidence_snapshots.add.call_args.kwargs["snapshot"]
    assert snapshot.evidence_id == "evidence-1"
    assert snapshot.position == 0
    assert snapshot.sha256 == _evidence().sha256


def test_multimodal_start_rejects_case_without_available_image() -> None:
    factory, _ = _uow_factory(evidence=())
    service = StartTextAnalysis(
        uow_factory=factory,
        provider=MockLLMProvider(),
        vision_provider=MockVisionProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=_Clock(),
        id_generator=_Ids(f"id-{index}" for index in range(5)),
    )
    with pytest.raises(ImageEvidenceRequiredError):
        service.execute(
            principal=_principal(),
            case_id="case-1",
            command=StartTextAnalysisCommand(
                pipeline=AnalysisPipeline.PRODUCT_DEFECT_MULTIMODAL_ANALYSIS,
                pipeline_version=MULTIMODAL_ANALYSIS_PIPELINE_VERSION,
                idempotency_key="key-1",
                correlation_id="correlation-1",
            ),
        )


class _Response:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self.body = body
        self.status = status

    def read(self, **kwargs: object) -> bytes:
        del kwargs
        return self.body

    def release_conn(self) -> None:
        return None


class _HTTP:
    def __init__(self, body: bytes, *, status: int = 200, error: Exception | None = None) -> None:
        self.body = body
        self.status = status
        self.error = error
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        fields: object | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> BaseHTTPResponse:
        self.calls.append({"method": method, "url": url, "fields": fields, "headers": headers})
        if self.error is not None:
            raise self.error
        return cast(BaseHTTPResponse, _Response(self.body, status=self.status))


def _remote_payload(
    *,
    confidence: float = 0.8,
    x2: float = 90,
    taxonomy_version: str = "kaputt-7-v1",
) -> bytes:
    return json.dumps(
        {
            "schema_version": "1.0",
            "provider": {
                "name": "vision-service",
                "model_name": "kaputt-model",
                "model_version": "1.0",
                "model_revision": "rev-1",
                "taxonomy_version": taxonomy_version,
                "threshold_version": "threshold-1",
                "preprocess_version": "preprocess-1",
                "postprocess_version": "postprocess-1",
            },
            "image_quality": {
                "usable": "NOT_EVALUATED",
                "score": None,
                "blurred": None,
                "dark": None,
                "overexposed": None,
                "product_visible": None,
                "defect_area_visible": None,
                "rejection_reasons": [],
            },
            "detections": [
                {
                    "id": "native-1",
                    "class_id": 4,
                    "class_name": "spillage",
                    "confidence": confidence,
                    "geometry": {
                        "coordinate_system": "pixel_xyxy",
                        "x1": 10,
                        "y1": 20,
                        "x2": x2,
                        "y2": 80,
                    },
                }
            ],
            "latency_ms": 42,
        },
        separators=(",", ":"),
    ).encode()


def _binary_remote_payload(
    *,
    score: float,
    threshold: float = 0.8984375,
    detections: list[object] | None = None,
) -> bytes:
    return json.dumps(
        {
            "schema_version": "1.0",
            "provider": {
                "name": "vision-service",
                "model_name": "dinov2-any-defect",
                "model_version": "e3-epoch-10",
                "model_revision": "checkpoint-package-revision",
                "dataset_version": "kaputt-heldout-report-2026-08-27",
                "taxonomy_version": "kaputt-any-defect-binary-v1",
                "threshold_version": "e3-validation-frozen-v1",
                "preprocess_version": "full-frame-1024-v1",
                "postprocess_version": "sigmoid-any-defect-v1",
            },
            "image_quality": {
                "usable": "NOT_EVALUATED",
                "score": None,
                "blurred": None,
                "dark": None,
                "overexposed": None,
                "product_visible": None,
                "defect_area_visible": None,
                "rejection_reasons": [],
            },
            "image_assessment": {
                "label": "defect",
                "score": score,
                "threshold": threshold,
            },
            "detections": detections or [],
            "latency_ms": 37,
        },
        separators=(",", ":"),
    ).encode()


def _remote(
    client: _HTTP,
    *,
    analysis_task: VisionTask = VisionTask.QUALITY_AND_DEFECT_DETECTION,
    expected_assessment_threshold: float | None = None,
) -> RemoteVisionProvider:
    return RemoteVisionProvider(
        base_url="https://vision.internal",
        api_key="private-key",
        model_id="kaputt-model",
        model_version="1.0",
        model_revision="rev-1",
        connect_timeout_seconds=2,
        read_timeout_seconds=10,
        max_image_bytes=1024,
        analysis_task=analysis_task,
        expected_assessment_threshold=expected_assessment_threshold,
        http_client=client,
    )


def test_remote_vision_multipart_normalizes_pixel_geometry_and_taxonomy() -> None:
    client = _HTTP(_remote_payload())
    result = _remote(client).analyze_image(
        VisionAnalysisRequest(
            evidence_id="evidence-1",
            content_type="image/png",
            image_width=100,
            image_height=100,
        ),
        image=b"synthetic-image",
    )

    assert client.calls[0]["method"] == "POST"
    assert client.calls[0]["url"] == "https://vision.internal/v1/vision/analyze"
    assert isinstance(client.calls[0]["fields"], dict)
    assert result.detections[0].label is DefectType.LEAKAGE
    assert result.taxonomy_version == "csight-defect-v1"
    assert result.detections[0].model_class_id == "4"
    assert result.detections[0].geometry.x1 == 0.1
    assert result.detections[0].geometry.x2 == 0.9
    assert result.detections[0].geometry.coordinate_system is CoordinateSystem.NORMALIZED_XYXY


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.95, VisionImageAssessmentOutcome.HIGH_CONFIDENCE_DEFECT_CANDIDATE),
        (0.5, VisionImageAssessmentOutcome.BELOW_HIGH_CONFIDENCE_THRESHOLD),
    ],
)
def test_remote_any_defect_returns_score_and_frozen_threshold_without_detection(
    score: float,
    expected: VisionImageAssessmentOutcome,
) -> None:
    client = _HTTP(_binary_remote_payload(score=score))
    provider = _remote(
        client,
        analysis_task=VisionTask.ANY_DEFECT_CLASSIFICATION,
        expected_assessment_threshold=0.8984375,
    )
    result = provider.analyze_image(
        VisionAnalysisRequest(
            evidence_id="evidence-1",
            content_type="image/png",
            image_width=100,
            image_height=100,
            task=provider.analysis_task,
        ),
        image=b"synthetic-image",
    )

    fields = client.calls[0]["fields"]
    assert isinstance(fields, dict)
    assert fields["task"] == "product_defect_any_defect_classification"
    assert result.detections == ()
    assert result.image_assessment is not None
    assert result.image_assessment.score == score
    assert result.image_assessment.threshold == 0.8984375
    assert result.image_assessment.outcome is expected
    assert result.taxonomy_version == "csight-any-defect-assessment-v1"


@pytest.mark.parametrize(
    "payload",
    [
        _binary_remote_payload(score=0.95, threshold=0.8),
        _binary_remote_payload(score=0.95, detections=[{"fabricated": True}]),
    ],
)
def test_remote_any_defect_fails_closed_on_threshold_drift_or_fabricated_detection(
    payload: bytes,
) -> None:
    provider = _remote(
        _HTTP(payload),
        analysis_task=VisionTask.ANY_DEFECT_CLASSIFICATION,
        expected_assessment_threshold=0.8984375,
    )
    with pytest.raises(VisionInvalidStructuredOutputError):
        provider.analyze_image(
            VisionAnalysisRequest(
                evidence_id="evidence-1",
                content_type="image/png",
                image_width=100,
                image_height=100,
                task=VisionTask.ANY_DEFECT_CLASSIFICATION,
            ),
            image=b"synthetic-image",
        )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("model_name", None),
        ("model_version", "  "),
        ("threshold_version", None),
        ("preprocess_version", 7),
        ("postprocess_version", []),
    ],
)
def test_remote_any_defect_rejects_missing_or_invalid_required_version_metadata(
    field: str,
    invalid_value: object,
) -> None:
    payload = json.loads(_binary_remote_payload(score=0.95))
    payload["provider"][field] = invalid_value
    provider = _remote(
        _HTTP(json.dumps(payload).encode()),
        analysis_task=VisionTask.ANY_DEFECT_CLASSIFICATION,
        expected_assessment_threshold=0.8984375,
    )

    with pytest.raises(VisionInvalidStructuredOutputError):
        provider.analyze_image(
            VisionAnalysisRequest(
                evidence_id="evidence-1",
                content_type="image/png",
                image_width=100,
                image_height=100,
                task=VisionTask.ANY_DEFECT_CLASSIFICATION,
            ),
            image=b"synthetic-image",
        )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("name", None),
        ("model_revision", 7),
        ("dataset_version", {}),
        ("framework", []),
        ("runtime", False),
        ("precision", "  "),
    ],
)
def test_remote_any_defect_rejects_invalid_optional_metadata_when_present(
    field: str,
    invalid_value: object,
) -> None:
    payload = json.loads(_binary_remote_payload(score=0.95))
    payload["provider"][field] = invalid_value
    provider = _remote(
        _HTTP(json.dumps(payload).encode()),
        analysis_task=VisionTask.ANY_DEFECT_CLASSIFICATION,
        expected_assessment_threshold=0.8984375,
    )

    with pytest.raises(VisionInvalidStructuredOutputError):
        provider.analyze_image(
            VisionAnalysisRequest(
                evidence_id="evidence-1",
                content_type="image/png",
                image_width=100,
                image_height=100,
                task=VisionTask.ANY_DEFECT_CLASSIFICATION,
            ),
            image=b"synthetic-image",
        )


def test_remote_vision_rejects_request_task_that_bypasses_deployment_mode() -> None:
    provider = _remote(_HTTP(_remote_payload()))

    with pytest.raises(VisionProviderRequestRejectedError, match="configured deployment"):
        provider.analyze_image(
            VisionAnalysisRequest(
                evidence_id="evidence-1",
                content_type="image/png",
                image_width=100,
                image_height=100,
                task=VisionTask.ANY_DEFECT_CLASSIFICATION,
            ),
            image=b"synthetic-image",
        )


@pytest.mark.parametrize(
    "payload",
    [
        _remote_payload(confidence=1.2),
        _remote_payload(x2=110),
        _remote_payload(taxonomy_version="unsupported-v9"),
        b"not-json",
    ],
)
def test_remote_vision_rejects_invalid_schema_or_geometry(payload: bytes) -> None:
    with pytest.raises(VisionInvalidStructuredOutputError):
        _remote(_HTTP(payload)).analyze_image(
            VisionAnalysisRequest(
                evidence_id="evidence-1",
                content_type="image/png",
                image_width=100,
                image_height=100,
            ),
            image=b"synthetic-image",
        )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, VisionProviderRequestRejectedError),
        (401, VisionProviderAuthenticationError),
        (403, VisionProviderAuthenticationError),
        (429, VisionProviderUnavailableError),
        (500, VisionProviderUnavailableError),
    ],
)
def test_remote_vision_classifies_http_statuses(
    status: int,
    expected: type[Exception],
) -> None:
    with pytest.raises(expected):
        _remote(_HTTP(b"{}", status=status)).analyze_image(
            VisionAnalysisRequest(
                evidence_id="evidence-1",
                content_type="image/png",
                image_width=100,
                image_height=100,
            ),
            image=b"synthetic-image",
        )


def test_remote_vision_normalizes_transport_timeout() -> None:
    from urllib3.exceptions import TimeoutError

    error = TimeoutError("deadline")
    with pytest.raises(VisionProviderTimeoutError):
        _remote(_HTTP(b"", error=error)).analyze_image(
            VisionAnalysisRequest(
                evidence_id="evidence-1",
                content_type="image/png",
                image_width=100,
                image_height=100,
            ),
            image=b"synthetic-image",
        )


@pytest.mark.parametrize(
    ("mode", "detection_count", "usable"),
    [
        (VisionMockMode.SUCCESS_SINGLE_DEFECT, 1, ImageUsability.USABLE),
        (VisionMockMode.SUCCESS_MULTIPLE_DEFECTS, 2, ImageUsability.USABLE),
        (VisionMockMode.NO_DEFECT, 0, ImageUsability.USABLE),
        (VisionMockMode.EMPTY_DETECTIONS, 0, ImageUsability.USABLE),
        (VisionMockMode.LOW_QUALITY_IMAGE, 0, ImageUsability.NOT_USABLE),
    ],
)
def test_mock_vision_success_scenarios_are_deterministic(
    mode: VisionMockMode,
    detection_count: int,
    usable: ImageUsability,
) -> None:
    provider = MockVisionProvider(mode=mode)
    request = VisionAnalysisRequest(
        evidence_id="evidence-1",
        content_type="image/png",
        image_width=100,
        image_height=100,
    )

    first = provider.analyze_image(request, image=b"same-image")
    second = provider.analyze_image(request, image=b"same-image")

    assert first == second
    assert len(first.detections) == detection_count
    assert first.image_quality.usable is usable


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            VisionMockMode.BINARY_CANDIDATE,
            VisionImageAssessmentOutcome.HIGH_CONFIDENCE_DEFECT_CANDIDATE,
        ),
        (
            VisionMockMode.BINARY_BELOW_THRESHOLD,
            VisionImageAssessmentOutcome.BELOW_HIGH_CONFIDENCE_THRESHOLD,
        ),
    ],
)
def test_binary_mock_modes_are_explicit_synthetic_non_localizing_assessments(
    mode: VisionMockMode,
    expected: VisionImageAssessmentOutcome,
) -> None:
    provider = MockVisionProvider(mode=mode, assessment_threshold=0.8984375)
    request = VisionAnalysisRequest(
        evidence_id="evidence-1",
        content_type="image/png",
        image_width=100,
        image_height=100,
        task=provider.analysis_task,
    )

    first = provider.analyze_image(request, image=b"same-synthetic-image")
    second = provider.analyze_image(request, image=b"same-synthetic-image")

    assert first == second
    assert first.provider_name == "mock"
    assert first.dataset_version == "synthetic-any-defect-v1"
    assert first.image_quality.usable is ImageUsability.NOT_EVALUATED
    assert first.detections == ()
    assert first.image_assessment is not None
    assert first.image_assessment.threshold == 0.8984375
    assert first.image_assessment.outcome is expected


@pytest.mark.parametrize(
    ("mode", "task"),
    [
        (VisionMockMode.SUCCESS_SINGLE_DEFECT, VisionTask.ANY_DEFECT_CLASSIFICATION),
        (VisionMockMode.BINARY_CANDIDATE, VisionTask.QUALITY_AND_DEFECT_DETECTION),
    ],
)
def test_mock_vision_rejects_mode_and_task_contract_mismatch(
    mode: VisionMockMode,
    task: VisionTask,
) -> None:
    with pytest.raises(ValueError, match="same contract"):
        MockVisionProvider(
            mode=mode,
            analysis_task=task,
            assessment_threshold=(0.8984375 if mode is VisionMockMode.BINARY_CANDIDATE else None),
        )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (VisionMockMode.TIMEOUT, VisionProviderTimeoutError),
        (VisionMockMode.TRANSIENT_ERROR, VisionProviderUnavailableError),
        (VisionMockMode.PERMANENT_ERROR, VisionProviderRequestRejectedError),
        (VisionMockMode.INVALID_SCHEMA, VisionInvalidStructuredOutputError),
        (VisionMockMode.INVALID_GEOMETRY, VisionInvalidStructuredOutputError),
    ],
)
def test_mock_vision_failure_scenarios_are_normalized(
    mode: VisionMockMode,
    expected: type[Exception],
) -> None:
    with pytest.raises(expected):
        MockVisionProvider(mode=mode).analyze_image(
            VisionAnalysisRequest(
                evidence_id="evidence-1",
                content_type="image/png",
                image_width=100,
                image_height=100,
            ),
            image=b"synthetic-image",
        )
