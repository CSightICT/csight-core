"""Opt-in qualification against a real private Vision service."""

import os
import ssl
from pathlib import Path

import pytest
import urllib3

from app.adapters.vision import RemoteVisionProvider
from app.platform.analysis import VisionAnalysisRequest, VisionTask

pytestmark = pytest.mark.external_vision


def test_external_vision_health_and_canonical_result() -> None:
    if os.getenv("RUN_EXTERNAL_VISION_TESTS") != "1":
        pytest.skip("SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE")
    base_url = os.environ.get("VISION_BASE_URL", "").strip()
    model_id = os.environ.get("VISION_MODEL_ID", "").strip()
    model_version = os.environ.get("VISION_MODEL_VERSION", "").strip()
    image_path = os.environ.get("VISION_QUALIFICATION_IMAGE", "").strip()
    if not all((base_url, model_id, model_version, image_path)):
        pytest.skip("SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE")

    tls_verify = os.getenv("VISION_TLS_VERIFY", "true").lower() == "true"
    health_headers = {}
    if api_key := os.environ.get("VISION_API_KEY"):
        health_headers["Authorization"] = f"Bearer {api_key}"
    health_client = urllib3.PoolManager(
        cert_reqs=ssl.CERT_REQUIRED if tls_verify else ssl.CERT_NONE
    )
    health = health_client.request(
        "GET",
        f"{base_url.rstrip('/')}/health",
        headers=health_headers,
        timeout=float(os.getenv("VISION_CONNECT_TIMEOUT_SECONDS", "5")),
        retries=False,
    )
    assert health.status == 200

    image = Path(image_path).read_bytes()
    analysis_task = VisionTask(
        os.getenv("VISION_TASK", VisionTask.QUALITY_AND_DEFECT_DETECTION.value)
    )
    expected_threshold_value = os.getenv("VISION_ASSESSMENT_EXPECTED_THRESHOLD", "").strip()
    expected_threshold = float(expected_threshold_value) if expected_threshold_value else None
    provider = RemoteVisionProvider(
        base_url=base_url,
        api_key=os.environ.get("VISION_API_KEY"),
        model_id=model_id,
        model_version=model_version,
        model_revision=os.environ.get("VISION_MODEL_REVISION"),
        connect_timeout_seconds=float(os.getenv("VISION_CONNECT_TIMEOUT_SECONDS", "5")),
        read_timeout_seconds=float(os.getenv("VISION_READ_TIMEOUT_SECONDS", "120")),
        max_image_bytes=int(os.getenv("VISION_MAX_IMAGE_BYTES", "10485760")),
        analysis_task=analysis_task,
        expected_assessment_threshold=expected_threshold,
        tls_verify=tls_verify,
    )
    result = provider.analyze_image(
        VisionAnalysisRequest(
            evidence_id="external-qualification-image",
            content_type="image/jpeg",
            image_width=int(os.getenv("VISION_QUALIFICATION_IMAGE_WIDTH", "1")),
            image_height=int(os.getenv("VISION_QUALIFICATION_IMAGE_HEIGHT", "1")),
            task=analysis_task,
        ),
        image=image,
    )

    assert result.model_name == model_id
    assert result.model_version == model_version
    assert result.latency_ms >= 0
    if analysis_task is VisionTask.ANY_DEFECT_CLASSIFICATION:
        assert result.detections == ()
        assert result.image_assessment is not None
        assert result.image_assessment.threshold == expected_threshold
    else:
        assert result.image_assessment is None
        assert all(
            detection.geometry.coordinate_system.value == "normalized_xyxy"
            for detection in result.detections
        )
