#!/usr/bin/env python3
"""Synthetic Celery tasks for measuring model/decision queue isolation only."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import time
from pathlib import Path

from celery import Celery

MODEL_TASK = "qualification.model_sleep.v1"
DECISION_TASK = "qualification.decision_probe.v1"
MODEL_QUEUE = "model-qualification"
DECISION_QUEUE = "decision-qualification"
MODEL_DURATION_SECONDS = 120
DECISION_COUNT = 20

celery_app = Celery("csight-queue-isolation", broker=os.environ["QUALIFICATION_BROKER_URL"])
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    task_ignore_result=True,
    task_acks_late=True,
    task_acks_on_failure_or_timeout=False,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_routes={
        MODEL_TASK: {"queue": MODEL_QUEUE},
        DECISION_TASK: {"queue": DECISION_QUEUE},
    },
    task_soft_time_limit=150,
    task_time_limit=180,
)


def _evidence_path() -> Path:
    return Path(os.environ["QUALIFICATION_EVIDENCE_PATH"])


def _append_event(event: dict[str, object]) -> None:
    payload = json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
    path = _evidence_path()
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "a", encoding="utf-8", closefd=False) as stream:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            stream.write(payload)
            stream.flush()
            os.fsync(descriptor)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _require_index(payload: object, *, maximum: int) -> tuple[int, int]:
    if not isinstance(payload, dict) or set(payload) != {"index", "enqueued_ns"}:
        raise ValueError("qualification payload has invalid fields")
    index = payload["index"]
    enqueued_ns = payload["enqueued_ns"]
    if type(index) is not int or not 0 <= index < maximum:
        raise ValueError("qualification index is invalid")
    if type(enqueued_ns) is not int or enqueued_ns <= 0:
        raise ValueError("qualification timestamp is invalid")
    return index, enqueued_ns


@celery_app.task(name=MODEL_TASK)  # pyright: ignore[reportUntypedFunctionDecorator]
def model_sleep(payload: object) -> None:
    index, enqueued_ns = _require_index(payload, maximum=2)
    started_ns = time.time_ns()
    _append_event(
        {
            "event": "model_started",
            "index": index,
            "queue_wait_ms": round((started_ns - enqueued_ns) / 1_000_000, 3),
        }
    )
    time.sleep(MODEL_DURATION_SECONDS)
    _append_event({"event": "model_completed", "index": index})


@celery_app.task(name=DECISION_TASK)  # pyright: ignore[reportUntypedFunctionDecorator]
def decision_probe(payload: object) -> None:
    index, enqueued_ns = _require_index(payload, maximum=DECISION_COUNT)
    started_ns = time.time_ns()
    _append_event(
        {
            "event": "decision_started",
            "index": index,
            "queue_wait_ms": round((started_ns - enqueued_ns) / 1_000_000, 3),
        }
    )
    time.sleep(0.05)
    _append_event({"event": "decision_completed", "index": index})


def publish_models() -> dict[str, object]:
    for index in range(2):
        celery_app.send_task(
            MODEL_TASK,
            args=({"index": index, "enqueued_ns": time.time_ns()},),
            queue=MODEL_QUEUE,
        )
    return {"status": "PUBLISHED", "task_count": 2, "duration_seconds": MODEL_DURATION_SECONDS}


def publish_decisions() -> dict[str, object]:
    for index in range(DECISION_COUNT):
        celery_app.send_task(
            DECISION_TASK,
            args=({"index": index, "enqueued_ns": time.time_ns()},),
            queue=DECISION_QUEUE,
        )
    return {"status": "PUBLISHED", "task_count": DECISION_COUNT}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("publish-models", "publish-decisions"))
    command = parser.parse_args().command
    result = publish_models() if command == "publish-models" else publish_decisions()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
