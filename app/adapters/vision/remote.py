"""Private multipart HTTP adapter for the CSight Vision service contract."""

import json
import ssl
from collections.abc import Callable, Mapping
from time import monotonic
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

import urllib3
from pydantic import ValidationError
from urllib3 import Timeout
from urllib3.exceptions import HTTPError, TimeoutError
from urllib3.response import BaseHTTPResponse

from app.adapters.vision.taxonomy import (
    CSIGHT_ANY_DEFECT_ASSESSMENT_VERSION,
    CSIGHT_VISION_TAXONOMY_VERSION,
    KAPUT_ANY_DEFECT_TAXONOMY_VERSION,
    KAPUT_TAXONOMY_VERSION,
    map_model_class,
)
from app.platform.analysis import (
    BoundingBox,
    CoordinateSystem,
    DetectionFinding,
    ImageQualityResult,
    ProviderMetadata,
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

_PROVIDER = "remote_vision"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_REMOTE_TASKS = {
    VisionTask.QUALITY_CHECK: "image_quality",
    VisionTask.DEFECT_DETECTION: "product_defect_detection",
    VisionTask.QUALITY_AND_DEFECT_DETECTION: "product_defect_detection",
    VisionTask.ANY_DEFECT_CLASSIFICATION: "product_defect_any_defect_classification",
}


class _HTTPClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        fields: object | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> BaseHTTPResponse: ...


class RemoteVisionProvider:
    """Normalize model-native classes and geometry at the provider boundary."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_id: str,
        model_version: str,
        model_revision: str | None,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        max_image_bytes: int,
        analysis_task: VisionTask | str = VisionTask.QUALITY_AND_DEFECT_DETECTION,
        expected_assessment_threshold: float | None = None,
        tls_verify: bool = True,
        http_client: _HTTPClient | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._endpoint = _endpoint(base_url)
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._model_id = _required(model_id)
        self._model_version = _required(model_version)
        self._model_revision = model_revision.strip() if model_revision else None
        self._analysis_task = VisionTask(analysis_task)
        if expected_assessment_threshold is not None and (
            isinstance(expected_assessment_threshold, bool)
            or not 0.0 <= expected_assessment_threshold <= 1.0
        ):
            raise ValueError("expected assessment threshold must be between zero and one")
        if (
            self._analysis_task is VisionTask.ANY_DEFECT_CLASSIFICATION
            and expected_assessment_threshold is None
        ):
            raise ValueError("expected assessment threshold is required for any-defect mode")
        self._expected_assessment_threshold = expected_assessment_threshold
        if connect_timeout_seconds <= 0 or read_timeout_seconds <= 0 or max_image_bytes <= 0:
            raise ValueError("Vision timeout and image limits must be positive")
        self._timeout = Timeout(connect=connect_timeout_seconds, read=read_timeout_seconds)
        self._max_image_bytes = max_image_bytes
        self._clock = clock
        if http_client is None:
            cert_reqs = ssl.CERT_REQUIRED if tls_verify else ssl.CERT_NONE
            http_client = cast(_HTTPClient, urllib3.PoolManager(cert_reqs=cert_reqs))
        self._http = http_client

    @property
    def provider_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider=_PROVIDER,
            name=self._model_id,
            version=self._model_version,
            revision=self._model_revision,
        )

    @property
    def analysis_task(self) -> VisionTask:
        return self._analysis_task

    def analyze_image(
        self,
        request: VisionAnalysisRequest,
        *,
        image: bytes,
    ) -> VisionAnalysisResult:
        if not image or len(image) > self._max_image_bytes:
            raise VisionProviderRequestRejectedError(
                provider=_PROVIDER,
                message="the image is empty or exceeds the configured provider limit",
            )
        if request.task is not self._analysis_task:
            raise VisionProviderRequestRejectedError(
                provider=_PROVIDER,
                message="the Vision request task does not match the configured deployment",
            )
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        started = self._clock()
        response: BaseHTTPResponse | None = None
        try:
            response = self._http.request(
                "POST",
                self._endpoint,
                fields={
                    "file": (
                        f"{request.evidence_id}.bin",
                        image,
                        request.content_type,
                    ),
                    "task": _REMOTE_TASKS[request.task],
                },
                headers=headers,
                timeout=self._timeout,
                retries=False,
                redirect=False,
                preload_content=False,
            )
            body = response.read(amt=_MAX_RESPONSE_BYTES + 1, decode_content=False)
            status = response.status
        except TimeoutError:
            raise VisionProviderTimeoutError(
                provider=_PROVIDER, message="the Vision request exceeded its deadline"
            ) from None
        except (HTTPError, OSError):
            raise VisionProviderUnavailableError(
                provider=_PROVIDER, message="the Vision service could not be reached"
            ) from None
        finally:
            if response is not None:
                response.release_conn()
        self._raise_status(status)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise VisionInvalidStructuredOutputError(
                provider=_PROVIDER, message="the Vision response exceeded its size limit"
            )
        latency_ms = max(0, round((self._clock() - started) * 1000))
        return self._decode(body=body, request=request, measured_latency_ms=latency_ms)

    def _decode(
        self,
        *,
        body: bytes,
        request: VisionAnalysisRequest,
        measured_latency_ms: int,
    ) -> VisionAnalysisResult:
        try:
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError
            provider = value["provider"]
            if not isinstance(provider, dict):
                raise ValueError
            detections_value = value.get("detections", [])
            if not isinstance(detections_value, list):
                raise ValueError
            if value.get("schema_version") != "1.0":
                raise ValueError
            is_binary = request.task is VisionTask.ANY_DEFECT_CLASSIFICATION
            image_assessment_value = value.get("image_assessment")
            if is_binary:
                if (
                    provider.get("taxonomy_version") != KAPUT_ANY_DEFECT_TAXONOMY_VERSION
                    or detections_value
                ):
                    raise ValueError
                image_assessment = self._normalize_image_assessment(image_assessment_value)
                detections: tuple[DetectionFinding, ...] = ()
                taxonomy_version = CSIGHT_ANY_DEFECT_ASSESSMENT_VERSION
            else:
                if (
                    provider.get("taxonomy_version") != KAPUT_TAXONOMY_VERSION
                    or image_assessment_value is not None
                ):
                    raise ValueError
                image_assessment = None
                detections = tuple(
                    self._normalize_detection(item, request=request, index=index)
                    for index, item in enumerate(detections_value)
                )
                taxonomy_version = CSIGHT_VISION_TAXONOMY_VERSION
            return VisionAnalysisResult(
                schema_version="1.0",
                provider_name=_required_provider_text(provider.get("name", _PROVIDER)),
                model_name=_required_provider_text(provider["model_name"]),
                model_version=_required_provider_text(provider["model_version"]),
                model_revision=_optional_provider_text(provider.get("model_revision")),
                dataset_version=_optional_provider_text(provider.get("dataset_version")),
                taxonomy_version=taxonomy_version,
                threshold_version=_required_provider_text(provider["threshold_version"]),
                preprocess_version=_required_provider_text(provider["preprocess_version"]),
                postprocess_version=_required_provider_text(provider["postprocess_version"]),
                framework=_optional_provider_text(provider.get("framework")),
                runtime=_optional_provider_text(provider.get("runtime")),
                precision=_optional_provider_text(provider.get("precision")),
                image_width=request.image_width,
                image_height=request.image_height,
                image_quality=ImageQualityResult.model_validate(value["image_quality"]),
                detections=detections,
                image_assessment=image_assessment,
                latency_ms=int(value.get("latency_ms", measured_latency_ms)),
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            raise VisionInvalidStructuredOutputError(
                provider=_PROVIDER,
                message="the Vision response did not match the canonical schema",
            ) from None

    def _normalize_image_assessment(self, value: object) -> VisionImageAssessment:
        if not isinstance(value, dict) or value.get("label") != "defect":
            raise ValueError
        score = _probability(value.get("score"))
        threshold = _probability(value.get("threshold"))
        if (
            self._expected_assessment_threshold is None
            or abs(threshold - self._expected_assessment_threshold) > 1e-12
        ):
            raise ValueError
        outcome = (
            VisionImageAssessmentOutcome.HIGH_CONFIDENCE_DEFECT_CANDIDATE
            if score >= threshold
            else VisionImageAssessmentOutcome.BELOW_HIGH_CONFIDENCE_THRESHOLD
        )
        return VisionImageAssessment(
            score=score,
            threshold=threshold,
            outcome=outcome,
        )

    @staticmethod
    def _normalize_detection(
        value: object,
        *,
        request: VisionAnalysisRequest,
        index: int,
    ) -> DetectionFinding:
        if not isinstance(value, dict):
            raise ValueError
        geometry = value["geometry"]
        if not isinstance(geometry, dict):
            raise ValueError
        class_name = str(value["class_name"])
        coordinate_system = geometry.get("coordinate_system", "normalized_xyxy")
        coords = [float(geometry[key]) for key in ("x1", "y1", "x2", "y2")]
        if coordinate_system == "pixel_xyxy":
            coords = [
                coords[0] / request.image_width,
                coords[1] / request.image_height,
                coords[2] / request.image_width,
                coords[3] / request.image_height,
            ]
        elif coordinate_system != "normalized_xyxy":
            raise ValueError
        return DetectionFinding(
            id=str(value.get("id", f"detection-{index}")),
            label=map_model_class(class_name),
            model_class_id=str(value["class_id"]) if value.get("class_id") is not None else None,
            model_class_name=class_name,
            confidence=float(value["confidence"]),
            geometry=BoundingBox(
                coordinate_system=CoordinateSystem.NORMALIZED_XYXY,
                x1=coords[0],
                y1=coords[1],
                x2=coords[2],
                y2=coords[3],
            ),
        )

    @staticmethod
    def _raise_status(status: int) -> None:
        if 200 <= status < 300:
            return
        if status in {401, 403}:
            raise VisionProviderAuthenticationError(
                provider=_PROVIDER, message="the Vision service rejected its credentials"
            )
        if status == 429 or status >= 500:
            raise VisionProviderUnavailableError(
                provider=_PROVIDER, message=f"the Vision service is unavailable (HTTP {status})"
            )
        raise VisionProviderRequestRejectedError(
            provider=_PROVIDER, message=f"the Vision service rejected the request (HTTP {status})"
        )


def _endpoint(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base_url must be an HTTP(S) origin without credentials or query data")
    return f"{normalized}/v1/vision/analyze"


def _required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Vision model identity must not be blank")
    return normalized


def _required_provider_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError
    normalized = value.strip()
    if not normalized:
        raise ValueError
    return normalized


def _optional_provider_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_provider_text(value)


def _probability(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError
    probability = float(value)
    if not 0.0 <= probability <= 1.0:
        raise ValueError
    return probability
