#!/usr/bin/env python3
"""Run isolated Collector, Prometheus, and Alertmanager qualification evidence."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_NAME = "csight-observability-qualification"
CORRELATION_ID = "otel-qualification-v1"
RECOVERY_CORRELATION_ID = "otel-collector-recovery-v1"
TRACE_ID = "11111111111111111111111111111111"
PARENT_SPAN_ID = "2222222222222222"
ALERT_NAME = "CSightHttpTelemetryObserved"
METRIC_NAME = "csight_http_server_request_count_total"
FORBIDDEN_LABEL_PARTS = (
    "tenant",
    "case",
    "user",
    "run_id",
    "event",
    "task_id",
    "correlation",
)
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
)


def _request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 3.0,
) -> tuple[int, dict[str, Any]]:
    status, payload, _ = _request_json_response(
        url,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    return status, payload


def _request_json_response(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 3.0,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read())
            return response.status, body, dict(response.headers.items())
    except urllib.error.HTTPError as error:
        body = json.loads(error.read())
        return error.code, body, dict(error.headers.items())


def _poll(description: str, operation: Any, *, timeout_seconds: float = 45.0) -> Any:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = operation()
            if result is not None:
                return result
        except (OSError, ValueError, urllib.error.URLError) as error:
            last_error = error
        time.sleep(0.5)
    suffix = f": {last_error}" if last_error is not None else ""
    raise RuntimeError(f"timed out waiting for {description}{suffix}")


def _prometheus_query(expression: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"query": expression})
    status, payload = _request_json(f"http://prometheus:9090/api/v1/query?{query}")
    if status != 200 or payload.get("status") != "success":
        raise RuntimeError("Prometheus query failed")
    return payload


def _metric_series() -> list[dict[str, str]]:
    query = urllib.parse.urlencode({"match[]": METRIC_NAME})
    status, payload = _request_json(f"http://prometheus:9090/api/v1/series?{query}")
    if status != 200 or payload.get("status") != "success":
        raise RuntimeError("Prometheus series query failed")
    data = payload.get("data")
    if not isinstance(data, list):
        raise RuntimeError("Prometheus series response is invalid")
    return [item for item in data if isinstance(item, dict)]


def _receiver_events() -> list[dict[str, Any]]:
    status, payload = _request_json("http://receiver:8080/events")
    if status != 200:
        raise RuntimeError("local alert receiver is unavailable")
    events = payload.get("events")
    if not isinstance(events, list):
        raise RuntimeError("local alert receiver response is invalid")
    return [event for event in events if isinstance(event, dict)]


def _has_alert(events: list[dict[str, Any]], status: str) -> bool:
    return any(
        event.get("status") == status
        and any(
            isinstance(alert, dict) and alert.get("alertname") == ALERT_NAME
            for alert in event.get("alerts", [])
        )
        for event in events
    )


def _alert_count(events: list[dict[str, Any]], status: str) -> int:
    return sum(
        1
        for event in events
        if event.get("status") == status
        and any(
            isinstance(alert, dict) and alert.get("alertname") == ALERT_NAME
            for alert in event.get("alerts", [])
        )
    )


def _events_with_status(status: str) -> list[dict[str, Any]] | None:
    events = _receiver_events()
    return events if _has_alert(events, status) else None


def _events_with_count(status: str, count: int) -> list[dict[str, Any]] | None:
    events = _receiver_events()
    return events if _alert_count(events, status) >= count else None


def _assert_safe_metric_labels(series: list[dict[str, str]]) -> None:
    if not series:
        raise RuntimeError("CSight HTTP metric series was not stored")
    for labels in series:
        for key, value in labels.items():
            normalized_key = key.casefold()
            if any(part in normalized_key for part in FORBIDDEN_LABEL_PARTS):
                raise RuntimeError(f"forbidden metric label key: {key}")
            if value == CORRELATION_ID or UUID_PATTERN.search(value):
                raise RuntimeError(f"identifier-like metric label value in {key}")


def run_inside(phase: str) -> dict[str, Any]:
    if phase == "firing":
        _poll(
            "CSight emitter",
            lambda: True if _request_json("http://emitter:8000/health/live")[0] == 200 else None,
        )
        status, payload, response_headers = _request_json_response(
            "http://emitter:8000/health/live",
            headers={
                "X-Correlation-ID": CORRELATION_ID,
                "traceparent": f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01",
            },
        )
        if status != 200 or payload.get("status") != "ok":
            raise RuntimeError("instrumented CSight HTTP request failed")
        normalized_response_headers = {
            key.casefold(): value for key, value in response_headers.items()
        }
        if normalized_response_headers.get("x-correlation-id") != CORRELATION_ID:
            raise RuntimeError("correlation identifier did not round-trip")

        def observed_metric() -> dict[str, Any] | None:
            result = _prometheus_query(f"sum({METRIC_NAME})")
            rows = result.get("data", {}).get("result", [])
            return result if rows and float(rows[0]["value"][1]) >= 1 else None

        metric_result = _poll("stored CSight HTTP metric", observed_metric)
        series = _metric_series()
        _assert_safe_metric_labels(series)
        events = _poll(
            "firing alert delivery",
            lambda: _events_with_status("firing"),
        )
        return {
            "phase": phase,
            "http_status": status,
            "correlation_header_round_trip": True,
            "metric_query_result_count": len(metric_result["data"]["result"]),
            "metric_series": series,
            "metric_labels_safe": True,
            "firing_alert_delivered": _has_alert(events, "firing"),
        }

    if phase == "recovery":
        status, payload = _request_json(
            "http://emitter:8000/health/live",
            headers={"X-Correlation-ID": RECOVERY_CORRELATION_ID},
        )
        if status != 200 or payload.get("status") != "ok":
            raise RuntimeError("CSight request failed after Collector recovery")

        def recovered_metric() -> dict[str, Any] | None:
            result = _prometheus_query(f"sum({METRIC_NAME})")
            rows = result.get("data", {}).get("result", [])
            return result if rows and float(rows[0]["value"][1]) >= 1 else None

        _poll("recovered CSight HTTP metric", recovered_metric)
        events = _poll(
            "refiring alert after recovery",
            lambda: _events_with_count("firing", 2),
            timeout_seconds=60.0,
        )
        return {
            "phase": phase,
            "http_after_collector_recovery_status": status,
            "metric_after_collector_recovery_received": True,
            "alert_refired_after_recovery": _alert_count(events, "firing") >= 2,
        }

    status, payload = _request_json(
        "http://emitter:8000/health/live",
        headers={"X-Correlation-ID": "otel-collector-outage-v1"},
    )
    if status != 200 or payload.get("status") != "ok":
        raise RuntimeError("Collector outage changed the CSight HTTP outcome")
    events = _poll(
        "resolved alert delivery",
        lambda: _events_with_status("resolved"),
        timeout_seconds=60.0,
    )
    return {
        "phase": phase,
        "http_during_collector_outage_status": status,
        "http_during_collector_outage_passed": True,
        "resolved_alert_delivered": _has_alert(events, "resolved"),
        "receiver_acknowledged": True,
    }


def _compose_command(repo_root: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        PROJECT_NAME,
        "--file",
        str(repo_root / "infra/observability/compose.observability-qualification.yml"),
    ]


def _run(
    command: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: float = 180.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_checker(compose: list[str], repo_root: Path, phase: str) -> dict[str, Any]:
    result = _run(
        [
            *compose,
            "--profile",
            "tools",
            "run",
            "--rm",
            "--no-deps",
            "checker",
            "/qualification/qualify_observability.py",
            "--inside",
            phase,
        ],
        cwd=repo_root,
        check=False,
        timeout=120.0,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"qualification checker {phase} failed: {detail}")
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"qualification checker returned no JSON: {result.stderr[-1000:]}")
    return json.loads(lines[-1])


def _trace_evidence(collector_logs: str) -> dict[str, bool]:
    checks = {
        "http_span_received": "HTTP /health/live" in collector_logs,
        "known_trace_received": TRACE_ID in collector_logs,
        "correlation_attribute_received": (
            "csight.correlation_id" in collector_logs and CORRELATION_ID in collector_logs
        ),
        "recovery_correlation_received": RECOVERY_CORRELATION_ID in collector_logs,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Collector trace evidence incomplete: {checks}")
    return checks


def run_host(output_dir: Path) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    compose = _compose_command(repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    firing: dict[str, Any] | None = None
    resolved: dict[str, Any] | None = None
    recovery: dict[str, Any] | None = None
    collector_logs = ""
    error: str | None = None
    try:
        _run(
            [
                *compose,
                "up",
                "--detach",
                "collector",
                "prometheus",
                "alertmanager",
                "receiver",
                "emitter",
            ],
            cwd=repo_root,
        )
        firing = _run_checker(compose, repo_root, "firing")
        _run([*compose, "stop", "--timeout", "5", "collector"], cwd=repo_root)
        resolved = _run_checker(compose, repo_root, "resolved")
        _run([*compose, "start", "collector"], cwd=repo_root)
        recovery = _run_checker(compose, repo_root, "recovery")
        collector_logs = _run([*compose, "logs", "--no-color", "collector"], cwd=repo_root).stdout
        trace = _trace_evidence(collector_logs)
        status = "PASS"
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as caught:
        error = f"{type(caught).__name__}: {caught}"
        status = "FAIL"
        try:
            collector_logs = _run(
                [*compose, "logs", "--no-color", "collector"],
                cwd=repo_root,
                check=False,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            collector_logs = ""
        trace = {
            "http_span_received": False,
            "known_trace_received": False,
            "correlation_attribute_received": False,
            "recovery_correlation_received": False,
        }
    finally:
        _run(
            [*compose, "down", "--volumes", "--remove-orphans", "--timeout", "5"],
            cwd=repo_root,
            check=False,
        )

    report = {
        "schema_version": "observability-qualification/1.0.0",
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "scope": "isolated-local-collector-prometheus-alertmanager-receiver",
        "images": {
            "collector": "sha256:89107a3a8f4636a396927edf7025bb9614b8da2d92f4cc3f43109e8d115736e2",
            "prometheus": "sha256:63805ebb8d2b3920190daf1cb14a60871b16fd38bed42b857a3182bc621f4996",
            "alertmanager": (
                "sha256:27c475db5fb156cab31d5c18a4251ac7ed567746a2483ff264516437a39b15ba"
            ),
        },
        "trace": trace,
        "metric_and_firing": firing,
        "outage_and_resolution": resolved,
        "recovery": recovery,
        "external_notification_sent": False,
        "operator_paging_destination_qualified": False,
        "error": error,
    }
    report_path = output_dir / "qualification_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    safe_log_path = output_dir / "collector_trace_evidence.log"
    safe_lines = [
        line
        for line in collector_logs.splitlines()
        if any(
            marker in line
            for marker in (
                "HTTP /health/live",
                TRACE_ID,
                CORRELATION_ID,
                RECOVERY_CORRELATION_ID,
            )
        )
    ]
    safe_log_path.write_text("\n".join(safe_lines) + "\n", encoding="utf-8")
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside", choices=("firing", "resolved", "recovery"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("local-data/observability-qualification/latest"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.inside is not None:
        print(json.dumps(run_inside(args.inside), sort_keys=True))
        return 0
    report = run_host(args.output_dir.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
