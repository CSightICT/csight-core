#!/usr/bin/env python3
"""Measure 20-client reads and synthetic model/decision queue isolation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.bootstrap.settings import Settings
from scripts.benchmark_operator_reads import nearest_rank_percentile
from scripts.benchmark_operator_reads import run as run_read_benchmark

PROJECT_NAME = "csight-queue-isolation-qualification"
READ_REPETITIONS = 3
DECISION_COUNT = 20


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    check: bool = True,
    timeout: float = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _compose(repo_root: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        PROJECT_NAME,
        "--file",
        str(repo_root / "infra/load/compose.queue-isolation-qualification.yml"),
    ]


def _compose_utility(
    compose: list[str], repo_root: Path, env: dict[str, str], command: str
) -> dict[str, object]:
    result = _run(
        [
            *compose,
            "--profile",
            "tools",
            "run",
            "--rm",
            "--no-deps",
            "utility",
            "/qualification/queue_isolation_tasks.py",
            command,
        ],
        cwd=repo_root,
        env=env,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    if not lines:
        raise RuntimeError("queue publisher did not return JSON")
    return json.loads(lines[-1])


def _events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise RuntimeError("queue evidence event is not an object")
        events.append(parsed)
    return events


def _wait_for(
    path: Path, event: str, count: int, timeout_seconds: float = 30
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        events = _events(path)
        if sum(item.get("event") == event for item in events) >= count:
            return events
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {event}")


def _prepare_output(output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, mode=0o777)
    output.chmod(0o777)


def _read_qualification(settings: Settings) -> dict[str, Any]:
    runs = [
        run_read_benchmark(
            settings=settings,
            base_url="http://127.0.0.1:8000",
            concurrent_clients=20,
            requests_per_endpoint=10,
            timeout_seconds=15,
            tenant_slug="csight-demo",
            email="reviewer@csight.demo",
        )
        for _ in range(READ_REPETITIONS)
    ]
    endpoint_results: dict[str, dict[str, object]] = {}
    for endpoint in ("/api/v1/operator/cases", "/api/v1/operator/reviews"):
        p95_values = [float(run["endpoints"][endpoint]["p95_ms"]) for run in runs]
        endpoint_results[endpoint] = {
            "run_p95_ms": p95_values,
            "worst_p95_ms": max(p95_values),
            "total_request_count": sum(
                int(run["endpoints"][endpoint]["request_count"]) for run in runs
            ),
            "total_error_count": sum(
                int(run["endpoints"][endpoint]["error_count"]) for run in runs
            ),
        }
    passed = all(
        result["total_error_count"] == 0 and float(result["worst_p95_ms"]) <= 500
        for result in endpoint_results.values()
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "scope": "current-demo-read-only-legacy-auth-not-pilot-oidc",
        "repetitions": READ_REPETITIONS,
        "concurrent_clients": 20,
        "requests_per_endpoint_per_client_per_run": 10,
        "endpoints": endpoint_results,
        "p95_budget_ms": 500,
        "mutations_performed": 0,
        "business_side_effects_performed": 0,
    }


def _queue_qualification(repo_root: Path, output: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["LOAD_EVIDENCE_DIR"] = os.fspath(output)
    compose = _compose(repo_root)
    event_path = output / "queue-events.ndjson"
    try:
        _run(
            [*compose, "up", "--detach", "--wait", "rabbitmq", "model-worker", "decision-worker"],
            cwd=repo_root,
            env=env,
        )
        model_publish = _compose_utility(compose, repo_root, env, "publish-models")
        model_events = _wait_for(event_path, "model_started", 1)
        if sum(event.get("event") == "model_started" for event in model_events) != 1:
            raise RuntimeError("model concurrency exceeded one")
        decision_publish = _compose_utility(compose, repo_root, env, "publish-decisions")
        events = _wait_for(event_path, "decision_completed", DECISION_COUNT)
        decision_starts = [event for event in events if event.get("event") == "decision_started"]
        waits = [float(event["queue_wait_ms"]) for event in decision_starts]
        decision_indices = [int(event["index"]) for event in decision_starts]
        if len(waits) != DECISION_COUNT:
            raise RuntimeError("decision queue lost a task")
        p95_ms = nearest_rank_percentile(waits, 0.95)
        model_started = sum(event.get("event") == "model_started" for event in events)
        model_completed = sum(event.get("event") == "model_completed" for event in events)
        passed = p95_ms <= 2000 and model_started == 1 and model_completed == 0
        return {
            "status": "PASS" if passed else "FAIL",
            "scope": "isolated-synthetic-rabbitmq-celery-routing-only",
            "model_publish": model_publish,
            "decision_publish": decision_publish,
            "model_worker_concurrency": 1,
            "decision_worker_concurrency": 2,
            "model_tasks_in_flight": 2,
            "model_started_while_measured": model_started,
            "model_completed_while_measured": model_completed,
            "decision_completed": DECISION_COUNT,
            "decision_queue_wait_p50_ms": round(nearest_rank_percentile(waits, 0.50), 3),
            "decision_queue_wait_p95_ms": round(p95_ms, 3),
            "decision_queue_wait_max_ms": round(max(waits), 3),
            "decision_queue_wait_p95_budget_ms": 2000,
            "lost_or_duplicate_decision_tasks": DECISION_COUNT - len(set(decision_indices)),
            "database_mutations": 0,
            "business_side_effects": 0,
        }
    finally:
        _run(
            [*compose, "down", "--volumes", "--remove-orphans", "--timeout", "5"],
            cwd=repo_root,
            env=env,
            check=False,
        )


def run(output: Path) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    _prepare_output(output)
    started_at = datetime.now(UTC)
    try:
        read_result = _read_qualification(
            Settings(_env_file=repo_root / ".env")  # pyright: ignore[reportCallIssue]
        )
        queue_result = _queue_qualification(repo_root, output)
        status = (
            "PASS"
            if read_result["status"] == "PASS" and queue_result["status"] == "PASS"
            else "FAIL"
        )
        error = None
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as caught:
        read_result = locals().get("read_result")
        queue_result = None
        status = "FAIL"
        error = f"{type(caught).__name__}: {caught}"
    report = {
        "schema_version": "csight.load_isolation_qualification/1.0.0",
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "read_qualification": read_result,
        "queue_isolation": queue_result,
        "twenty_terminal_workflows_qualified": False,
        "non_model_mutation_p95_qualified": False,
        "actual_model_provider_used": False,
        "error": error,
    }
    (output / "qualification-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    output.chmod(0o700)
    return report


def main() -> int:
    report = run(Path("local-data/load-isolation-qualification/latest").resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
