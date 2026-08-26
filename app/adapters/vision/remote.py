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
    CSIGHT_VISION_TAXONOMY_VERSION,
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
    VisionInvalidStructuredOutputError,
    VisionProviderAuthenticationError,
    VisionProviderRequestRejectedError,
    VisionProviderTimeoutError,
    VisionProviderUnavailableError,
)

_PROVIDER = "remote_vision"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


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
        tls_verify: bool = True,
        http_client: _HTTPClient | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._endpoint = _endpoint(base_url)
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._model_id = _required(model_id)
        self._model_version = _required(model_version)
        self._model_revision = model_revision.strip() if model_revision else None
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
                    "task": "product_defect_detection",
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
            detections = tuple(
                self._normalize_detection(item, request=request, index=index)
                for index, item in enumerate(detections_value)
            )
            if value.get("schema_version") != "1.0":
                raise ValueError
            if provider.get("taxonomy_version") != KAPUT_TAXONOMY_VERSION:
                raise ValueError
            return VisionAnalysisResult(
                schema_version="1.0",
                provider_name=str(provider.get("name", _PROVIDER)),
                model_name=str(provider["model_name"]),
                model_version=str(provider["model_version"]),
                model_revision=provider.get("model_revision"),
                dataset_version=provider.get("dataset_version"),
                taxonomy_version=CSIGHT_VISION_TAXONOMY_VERSION,
                threshold_version=str(provider["threshold_version"]),
                preprocess_version=str(provider["preprocess_version"]),
                postprocess_version=str(provider["postprocess_version"]),
                framework=provider.get("framework"),
                runtime=provider.get("runtime"),
                precision=provider.get("precision"),
                image_width=request.image_width,
                image_height=request.image_height,
                image_quality=ImageQualityResult.model_validate(value["image_quality"]),
                detections=detections,
                latency_ms=int(value.get("latency_ms", measured_latency_ms)),
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            raise VisionInvalidStructuredOutputError(
                provider=_PROVIDER,
                message="the Vision response did not match the canonical schema",
            ) from None

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
