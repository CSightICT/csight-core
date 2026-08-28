"""Run one real E3 forward pass through the loopback HTTP contract."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from io import BytesIO
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image, ImageDraw

EXPECTED_MODEL_NAME = "csight-dinov2-vits14-kaputt-binary"
EXPECTED_MODEL_VERSION = "e3-epoch10-20260827"
EXPECTED_MODEL_REVISION = "49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e"
EXPECTED_THRESHOLD = 0.8984375


def _synthetic_pump_image() -> bytes:
    stream = BytesIO()
    image = Image.new("RGB", (256, 256), color=(242, 246, 248))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((72, 74, 184, 226), radius=16, fill=(217, 224, 229))
    draw.rectangle((105, 45, 151, 88), fill=(183, 196, 204))
    draw.rectangle((126, 30, 184, 48), fill=(155, 173, 184))
    draw.line(((134, 74), (120, 104), (145, 128), (124, 158)), fill=(183, 48, 48), width=5)
    image.save(stream, format="PNG")
    return stream.getvalue()


def _request_json(request: Request, *, timeout: float) -> Mapping[str, object]:
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(f"E3 Vision service returned HTTP {error.code}") from None
    except (TimeoutError, URLError):
        raise RuntimeError("E3 Vision service could not be reached") from None
    if not isinstance(value, dict):
        raise RuntimeError("E3 Vision service response was not a JSON object")
    return cast(Mapping[str, object], value)


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"E3 Vision response omitted {label}")
    return cast(Mapping[str, object], value)


def main() -> int:
    host = os.getenv("VISION_E3_HOST", "127.0.0.1")
    port = os.getenv("VISION_E3_PORT", "8093")
    base_url = f"http://{host}:{port}"
    api_key = os.getenv("VISION_E3_API_KEY", "").strip()
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        health = _request_json(
            Request(f"{base_url}/health", headers=headers, method="GET"),
            timeout=10,
        )
        if (
            health.get("status") != "healthy"
            or health.get("model_name") != EXPECTED_MODEL_NAME
            or health.get("model_version") != EXPECTED_MODEL_VERSION
            or health.get("model_revision") != EXPECTED_MODEL_REVISION
        ):
            raise RuntimeError("E3 health identity did not match the frozen checkpoint")

        image = _synthetic_pump_image()
        boundary = f"csight-e3-{uuid4().hex}"
        newline = b"\r\n"
        body = b"".join(
            (
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="task"\r\n\r\n',
                b"product_defect_any_defect_classification",
                newline,
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="file"; filename="qualification.bin"\r\n',
                b"Content-Type: image/png\r\n\r\n",
                image,
                newline,
                f"--{boundary}--\r\n".encode(),
            )
        )
        result = _request_json(
            Request(
                f"{base_url}/v1/vision/analyze",
                data=body,
                headers={
                    **headers,
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                method="POST",
            ),
            timeout=180,
        )
        provider = _mapping(result.get("provider"), label="provider")
        assessment = _mapping(result.get("image_assessment"), label="image_assessment")
        score = assessment.get("score")
        threshold = assessment.get("threshold")
        if (
            provider.get("name") != "remote_vision"
            or provider.get("model_name") != EXPECTED_MODEL_NAME
            or provider.get("model_version") != EXPECTED_MODEL_VERSION
            or provider.get("model_revision") != EXPECTED_MODEL_REVISION
            or provider.get("taxonomy_version") != "kaputt-any-defect-binary-v1"
        ):
            raise RuntimeError("E3 response identity did not match the Core contract")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise RuntimeError("E3 response score was invalid")
        if threshold != EXPECTED_THRESHOLD or result.get("detections") != []:
            raise RuntimeError("E3 response threshold or non-localizing boundary was invalid")
        normalized_score = float(score)
        outcome = (
            "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
            if normalized_score >= EXPECTED_THRESHOLD
            else "BELOW_HIGH_CONFIDENCE_THRESHOLD"
        )
        print(
            json.dumps(
                {
                    "verdict": "REAL_E3_HTTP_INFERENCE_PASS",
                    "claim_boundary": (
                        "REAL_E3_CHECKPOINT_ON_SYNTHETIC_CONNECTIVITY_IMAGE_"
                        "NOT_PRODUCT_QUALIFICATION"
                    ),
                    "model_name": EXPECTED_MODEL_NAME,
                    "model_version": EXPECTED_MODEL_VERSION,
                    "model_revision": EXPECTED_MODEL_REVISION,
                    "device": health.get("device"),
                    "precision": health.get("precision"),
                    "score": normalized_score,
                    "threshold": EXPECTED_THRESHOLD,
                    "outcome": outcome,
                    "localized_detection_count": 0,
                    "normal_classification_performed": False,
                    "automatic_decision_performed": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"E3 qualification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
