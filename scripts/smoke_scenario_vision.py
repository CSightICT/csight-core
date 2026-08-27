"""Run the local synthetic hard-plastic binary-Vision contract smoke flow.

This command does not execute the E3 checkpoint.  It proves that the CSight
runtime can upload an image, preserve it in a multimodal snapshot, and expose
an image-level any-defect candidate without inventing a defect type or box.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image, ImageDraw


class ScenarioVisionSmokeFailure(RuntimeError):
    """A sanitized failure that is safe to print in a local demo."""


def env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _error_code(payload: object) -> str:
    if not isinstance(payload, dict):
        return "UNKNOWN_ERROR"
    error = payload.get("error")
    if not isinstance(error, dict):
        return "UNKNOWN_ERROR"
    code = error.get("code")
    return code if isinstance(code, str) else "UNKNOWN_ERROR"


def _decode_response(
    request: Request,
    *,
    expected: frozenset[int],
) -> tuple[int, Mapping[str, object]]:
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        status = error.code
        try:
            payload = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            payload = {}
    except (TimeoutError, URLError):
        raise ScenarioVisionSmokeFailure("the local CSight API could not be reached") from None
    if status not in expected:
        raise ScenarioVisionSmokeFailure(f"unexpected HTTP {status} ({_error_code(payload)})")
    if not isinstance(payload, dict):
        raise ScenarioVisionSmokeFailure("the API response was not a JSON object")
    return status, cast(Mapping[str, object], payload)


def json_request(
    *,
    method: str,
    url: str,
    expected: frozenset[int],
    body: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, Mapping[str, object]]:
    request_headers = {"Accept": "application/json", **dict(headers or {})}
    encoded = None
    if body is not None:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    return _decode_response(
        Request(url, data=encoded, headers=request_headers, method=method),
        expected=expected,
    )


def synthetic_pump_image(*, visible_breakage: bool = True) -> bytes:
    """Create a non-customer image used only to exercise the Mock contract."""

    stream = BytesIO()
    image = Image.new("RGB", (256, 256), color=(242, 246, 248))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((72, 74, 184, 226), radius=16, fill=(217, 224, 229))
    draw.rectangle((105, 45, 151, 88), fill=(183, 196, 204))
    draw.rectangle((126, 30, 184, 48), fill=(155, 173, 184))
    if visible_breakage:
        draw.line(
            ((134, 74), (120, 104), (145, 128), (124, 158)),
            fill=(183, 48, 48),
            width=5,
        )
    image.save(stream, format="PNG")
    return stream.getvalue()


def upload_image(
    *,
    url: str,
    authorization: Mapping[str, str],
    image: bytes,
    filename: str = "synthetic-pump-breakage.png",
) -> Mapping[str, object]:
    boundary = f"csight-{uuid4().hex}"
    newline = b"\r\n"
    body = b"".join(
        (
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="evidence_type"\r\n\r\n',
            b"IMAGE",
            newline,
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; '
            + f'filename="{filename}"\r\n'.encode(),
            b"Content-Type: image/png\r\n\r\n",
            image,
            newline,
            f"--{boundary}--\r\n".encode(),
        )
    )
    _, payload = _decode_response(
        Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                **dict(authorization),
            },
            method="POST",
        ),
        expected=frozenset({201}),
    )
    return payload


def required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ScenarioVisionSmokeFailure(f"the API response omitted {key}")
    return value


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ScenarioVisionSmokeFailure(f"the result omitted {label}")
    return cast(Mapping[str, object], value)


def _records(value: object, *, label: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ScenarioVisionSmokeFailure(f"the result omitted {label}")
    return cast(Sequence[Mapping[str, object]], value)


def run(
    *,
    base_url: str,
    reviewer_password: str,
    timeout_seconds: float,
    expected_threshold: float,
) -> Mapping[str, object]:
    suffix = uuid4().hex[:12]
    _, token_response = json_request(
        method="POST",
        url=f"{base_url}/api/v1/auth/token",
        body={
            "tenant_slug": "csight-demo",
            "email": "reviewer@csight.demo",
            "password": reviewer_password,
        },
        expected=frozenset({200}),
    )
    authorization = {"Authorization": f"Bearer {required_string(token_response, 'access_token')}"}
    _, case_response = json_request(
        method="POST",
        url=f"{base_url}/api/v1/cases",
        headers={**authorization, "Idempotency-Key": f"scenario-vision-case-{suffix}"},
        body={
            "order_ref": f"SCENARIO-ORDER-{suffix}",
            "product_ref": "SYN-HDP-100",
            "customer_message": (
                "합성 시나리오: 경질 플라스틱 수동 펌프의 목 부분이 분리되어 "
                "내용물을 누를 수 없습니다. 교환을 요청합니다."
            ),
            "requested_action": "EXCHANGE",
            "attributes": {
                "synthetic_scenario": True,
                "material_proxy": "plastic_hard",
                "vision_scope": "binary_any_defect_advisory_only",
            },
        },
        expected=frozenset({201}),
    )
    case_id = required_string(case_response, "case_id")
    evidence = upload_image(
        url=f"{base_url}/api/v1/cases/{case_id}/evidence",
        authorization=authorization,
        image=synthetic_pump_image(),
    )
    evidence_id = required_string(evidence, "evidence_id")

    analysis_url = f"{base_url}/api/v1/cases/{case_id}/analysis-runs"
    _, started = json_request(
        method="POST",
        url=analysis_url,
        headers={**authorization, "Idempotency-Key": f"scenario-vision-run-{suffix}"},
        body={
            "pipeline": "product_defect_multimodal_analysis",
            "pipeline_version": "1.0.0",
        },
        expected=frozenset({202}),
    )
    run_id = required_string(started, "analysis_run_id")

    deadline = time.monotonic() + timeout_seconds
    detail: Mapping[str, object] = {}
    status = "UNKNOWN"
    while time.monotonic() < deadline:
        _, detail = json_request(
            method="GET",
            url=f"{analysis_url}/{run_id}",
            headers=authorization,
            expected=frozenset({200}),
        )
        run_projection = _mapping(detail.get("run"), label="run")
        raw_status = run_projection.get("status")
        status = raw_status if isinstance(raw_status, str) else "UNKNOWN"
        if status in {"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"}:
            break
        time.sleep(1)
    else:
        raise ScenarioVisionSmokeFailure("the multimodal run did not finish before timeout")
    if status != "SUCCEEDED":
        raise ScenarioVisionSmokeFailure(f"the multimodal run finished as {status}")

    vision_records = _records(detail.get("vision_results"), label="vision_results")
    if len(vision_records) != 1:
        raise ScenarioVisionSmokeFailure("the run did not persist exactly one Vision result")
    result = _mapping(vision_records[0].get("result"), label="Vision result")
    assessment = _mapping(result.get("image_assessment"), label="image_assessment")
    detections = _records(result.get("detections"), label="detections")
    if detections:
        raise ScenarioVisionSmokeFailure("binary assessment must not invent detections")
    score = assessment.get("score")
    threshold = assessment.get("threshold")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ScenarioVisionSmokeFailure("image_assessment.score is invalid")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ScenarioVisionSmokeFailure("image_assessment.threshold is invalid")
    if abs(float(threshold) - expected_threshold) > 1e-12:
        raise ScenarioVisionSmokeFailure(
            f"runtime threshold {threshold} does not match frozen E3 threshold {expected_threshold}"
        )
    if float(score) < float(threshold):
        raise ScenarioVisionSmokeFailure("candidate mock returned a score below its threshold")
    if assessment.get("outcome") != "HIGH_CONFIDENCE_DEFECT_CANDIDATE":
        raise ScenarioVisionSmokeFailure("candidate outcome does not match score >= threshold")
    if assessment.get("assessment_type") != "ANY_DEFECT":
        raise ScenarioVisionSmokeFailure("the assessment is not ANY_DEFECT")

    return {
        "verdict": "SYNTHETIC_BINARY_VISION_CONTRACT_PASS",
        "claim_boundary": "MOCK_CONTRACT_ONLY_NOT_E3_INFERENCE",
        "case_id": case_id,
        "evidence_id": evidence_id,
        "analysis_run_id": run_id,
        "run_status": status,
        "model_name": result.get("model_name"),
        "model_version": result.get("model_version"),
        "assessment_type": assessment.get("assessment_type"),
        "score": score,
        "frozen_threshold": threshold,
        "outcome": assessment.get("outcome"),
        "localized_detection_count": len(detections),
        "normal_classification_performed": False,
        "automatic_decision_performed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--expected-threshold", type=float, default=0.8984375)
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        env = env_values(arguments.env_file)
        password = env.get("DEVELOPMENT_SEED_REVIEWER_PASSWORD", "")
        if len(password) < 12:
            raise ScenarioVisionSmokeFailure(
                "DEVELOPMENT_SEED_REVIEWER_PASSWORD must be configured before the smoke run"
            )
        port = env.get("API_PORT", "8000")
        base_url = (arguments.base_url or f"http://127.0.0.1:{port}").rstrip("/")
        if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ScenarioVisionSmokeFailure("the smoke command accepts only a local API URL")
        if arguments.timeout_seconds <= 0:
            raise ScenarioVisionSmokeFailure("timeout-seconds must be positive")
        if not 0.0 <= arguments.expected_threshold <= 1.0:
            raise ScenarioVisionSmokeFailure("expected-threshold must be between zero and one")
        report = run(
            base_url=base_url,
            reviewer_password=password,
            timeout_seconds=arguments.timeout_seconds,
            expected_threshold=arguments.expected_threshold,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    except (OSError, UnicodeError, ValueError, ScenarioVisionSmokeFailure) as error:
        print(f"Scenario Vision smoke failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
