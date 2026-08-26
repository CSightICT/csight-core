"""Authenticated, synthetic-only Sprint 2 HTTP smoke flow."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


class SmokeFailure(RuntimeError):
    """A sanitized smoke assertion failure."""


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _json_request(
    *,
    method: str,
    url: str,
    body: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
    expected: frozenset[int],
) -> tuple[int, Mapping[str, object]]:
    request_headers = {"Accept": "application/json", **dict(headers or {})}
    encoded = None
    if body is not None:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=encoded, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        status = error.code
        try:
            payload = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            payload = {}
    except (TimeoutError, URLError) as error:
        del error
        raise SmokeFailure("the local CSight API could not be reached") from None
    if status not in expected:
        code = _error_code(payload)
        raise SmokeFailure(f"unexpected HTTP {status} ({code})")
    if not isinstance(payload, dict):
        raise SmokeFailure("the API response was not a JSON object")
    return status, cast(Mapping[str, object], payload)


def _error_code(payload: object) -> str:
    if not isinstance(payload, dict):
        return "UNKNOWN_ERROR"
    error = payload.get("error")
    if not isinstance(error, dict):
        return "UNKNOWN_ERROR"
    code = error.get("code")
    return code if isinstance(code, str) else "UNKNOWN_ERROR"


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SmokeFailure(f"the API response omitted {key}")
    return value


def run(*, base_url: str, reviewer_password: str, timeout_seconds: float) -> None:
    suffix = uuid4().hex[:12]
    customer_message = "합성 테스트: 용기 하단에서 내용물이 샜습니다. 교환을 요청합니다."
    _, token_response = _json_request(
        method="POST",
        url=f"{base_url}/api/v1/auth/token",
        body={
            "tenant_slug": "csight-demo",
            "email": "reviewer@csight.demo",
            "password": reviewer_password,
        },
        expected=frozenset({200}),
    )
    token = _required_string(token_response, "access_token")
    authorization = {"Authorization": f"Bearer {token}"}

    _, case_response = _json_request(
        method="POST",
        url=f"{base_url}/api/v1/cases",
        headers={**authorization, "Idempotency-Key": f"smoke-case-{suffix}"},
        body={
            "order_ref": f"SYNTHETIC-ORDER-{suffix}",
            "product_ref": f"SYNTHETIC-PRODUCT-{suffix}",
            "customer_message": customer_message,
            "requested_action": "EXCHANGE",
            "attributes": {"synthetic_smoke": True},
        },
        expected=frozenset({201}),
    )
    case_id = _required_string(case_response, "case_id")
    analysis_key = f"smoke-analysis-{suffix}"
    analysis_url = f"{base_url}/api/v1/cases/{case_id}/analysis-runs"
    _, run_response = _json_request(
        method="POST",
        url=analysis_url,
        headers={**authorization, "Idempotency-Key": analysis_key},
        body={
            "pipeline": "product_defect_text_extraction",
            "pipeline_version": "1.0.0",
        },
        expected=frozenset({202}),
    )
    run_id = _required_string(run_response, "analysis_run_id")

    replay_status, replay = _json_request(
        method="POST",
        url=analysis_url,
        headers={**authorization, "Idempotency-Key": analysis_key},
        body={
            "pipeline": "product_defect_text_extraction",
            "pipeline_version": "1.0.0",
        },
        expected=frozenset({200}),
    )
    if replay_status != 200 or _required_string(replay, "analysis_run_id") != run_id:
        raise SmokeFailure("the idempotency replay did not return the original run")

    deadline = time.monotonic() + timeout_seconds
    detail: Mapping[str, object] = {}
    while time.monotonic() < deadline:
        _, detail = _json_request(
            method="GET",
            url=f"{analysis_url}/{run_id}",
            headers=authorization,
            expected=frozenset({200}),
        )
        run_projection = detail.get("run")
        if not isinstance(run_projection, dict):
            raise SmokeFailure("the run detail omitted its run projection")
        status = run_projection.get("status")
        if status in {"SUCCEEDED", "FAILED"}:
            break
        time.sleep(1)
    else:
        raise SmokeFailure("the analysis run did not reach a terminal state before the timeout")

    run_projection = detail.get("run")
    assert isinstance(run_projection, dict)
    if run_projection.get("status") != "SUCCEEDED":
        failure = run_projection.get("failure")
        failure_code = failure.get("code") if isinstance(failure, dict) else "UNKNOWN_ERROR"
        raise SmokeFailure(f"the analysis run failed ({failure_code})")
    extraction = detail.get("extraction_result")
    if not isinstance(extraction, dict) or not isinstance(extraction.get("result"), dict):
        raise SmokeFailure("the successful run omitted its structured extraction result")

    print(f"Analysis smoke passed: case={case_id}, run={run_id}, status=SUCCEEDED")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        env = _env_values(arguments.env_file)
        password = env.get("DEVELOPMENT_SEED_REVIEWER_PASSWORD", "")
        if len(password) < 12:
            raise SmokeFailure(
                "DEVELOPMENT_SEED_REVIEWER_PASSWORD must be configured before the smoke run"
            )
        port = env.get("API_PORT", "8000")
        base_url = (arguments.base_url or f"http://127.0.0.1:{port}").rstrip("/")
        if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise SmokeFailure("the smoke command accepts only an explicit local API URL")
        if arguments.timeout_seconds <= 0:
            raise SmokeFailure("timeout-seconds must be positive")
        run(
            base_url=base_url,
            reviewer_password=password,
            timeout_seconds=arguments.timeout_seconds,
        )
    except (OSError, ValueError, SmokeFailure) as error:
        print(f"Analysis smoke failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
