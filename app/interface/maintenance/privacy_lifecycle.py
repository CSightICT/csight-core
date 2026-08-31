"""Run bounded automatic sensitive-payload retention for one configured pilot tenant."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from types import FrameType
from typing import Protocol

from pydantic import ValidationError as SettingsValidationError

from app.adapters.persistence.tenant_context import (
    system_case_access_context,
    tenant_context,
)
from app.application.privacy_lifecycle import PurgeExpiredSensitivePayloads
from app.bootstrap.logging import configure_logging, get_logger
from app.bootstrap.privacy_lifecycle import build_sensitive_payload_retention_service
from app.bootstrap.settings import Settings, get_settings
from app.platform.privacy_lifecycle import LifecycleRunReport

logger = get_logger(__name__)
_DEFAULT_HEALTH_FILE = Path("/tmp/csight-privacy-lifecycle-health.json")


class _AutomatedPurgeService(Protocol):
    def execute_automated(self, *, tenant_id: str, limit: int) -> LifecycleRunReport: ...


@dataclass(frozen=True, slots=True)
class RetentionSweepResult:
    scanned_count: int
    applied_count: int
    already_applied_count: int
    blocked_count: int
    batch_count: int
    truncated: bool

    @property
    def passed(self) -> bool:
        return self.blocked_count == 0 and not self.truncated


def run_retention_sweep(
    service: _AutomatedPurgeService,
    *,
    tenant_id: str,
    batch_size: int,
    max_batches: int,
) -> RetentionSweepResult:
    """Drain bounded expired rows and stop on any fail-closed result."""

    if not tenant_id.strip():
        raise ValueError("tenant_id must not be blank")
    if not 1 <= batch_size <= 5000:
        raise ValueError("batch_size must be between 1 and 5000")
    if not 1 <= max_batches <= 100:
        raise ValueError("max_batches must be between 1 and 100")

    scanned = applied = already_applied = blocked = 0
    truncated = False
    for batch_index in range(1, max_batches + 1):
        with tenant_context(tenant_id), system_case_access_context():
            report = service.execute_automated(tenant_id=tenant_id, limit=batch_size)
        scanned += report.scanned_count
        applied += report.applied_count
        already_applied += report.already_applied_count
        blocked += report.blocked_count
        truncated = report.truncated
        if blocked or not truncated:
            return RetentionSweepResult(
                scanned_count=scanned,
                applied_count=applied,
                already_applied_count=already_applied,
                blocked_count=blocked,
                batch_count=batch_index,
                truncated=truncated,
            )
    return RetentionSweepResult(
        scanned_count=scanned,
        applied_count=applied,
        already_applied_count=already_applied,
        blocked_count=blocked,
        batch_count=max_batches,
        truncated=truncated,
    )


def _write_health(path: Path, result: RetentionSweepResult) -> None:
    payload = {
        "schema_version": "privacy_lifecycle_health/1.0.0",
        "status": "ok" if result.passed else "attention_required",
        "recorded_at_epoch": int(time.time()),
        **asdict(result),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _write_failure_health(path: Path) -> None:
    payload = {
        "schema_version": "privacy_lifecycle_health/1.0.0",
        "status": "error",
        "recorded_at_epoch": int(time.time()),
        "scanned_count": 0,
        "applied_count": 0,
        "already_applied_count": 0,
        "blocked_count": 0,
        "batch_count": 0,
        "truncated": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def retention_healthcheck(
    *,
    path: Path,
    interval_seconds: int,
    now_epoch: int | None = None,
) -> bool:
    """Require a recent successful sweep; the file contains aggregate counts only."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        recorded_at = int(payload["recorded_at_epoch"])
        status = str(payload["status"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False
    now = int(time.time()) if now_epoch is None else now_epoch
    maximum_age = max(interval_seconds * 2, 180)
    return status == "ok" and 0 <= now - recorded_at <= maximum_age


def run_automation_loop(
    service: _AutomatedPurgeService,
    *,
    tenant_id: str,
    batch_size: int,
    max_batches: int,
    interval_seconds: int,
    health_file: Path,
    once: bool,
    stop_event: Event,
) -> int:
    while not stop_event.is_set():
        try:
            result = run_retention_sweep(
                service,
                tenant_id=tenant_id,
                batch_size=batch_size,
                max_batches=max_batches,
            )
            _write_health(health_file, result)
        except Exception as error:
            try:
                _write_failure_health(health_file)
            except OSError as health_error:
                logger.error(
                    "privacy_retention_health_write_failed",
                    error_type=type(health_error).__name__,
                )
            logger.error(
                "privacy_retention_sweep_failed",
                error_type=type(error).__name__,
            )
            if once:
                return 1
        else:
            log = logger.info if result.passed else logger.warning
            log(
                "privacy_retention_sweep_completed"
                if result.passed
                else "privacy_retention_sweep_attention_required",
                scanned=result.scanned_count,
                applied=result.applied_count,
                already_applied=result.already_applied_count,
                blocked=result.blocked_count,
                batches=result.batch_count,
                truncated=result.truncated,
            )
            if once:
                return 0 if result.passed else 2
        stop_event.wait(interval_seconds)
    logger.info("privacy_retention_scheduler_stopped")
    return 0


def _install_signal_handlers(stop_event: Event) -> None:
    def request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info(
            "privacy_retention_scheduler_stop_requested",
            signal_name=signal.Signals(signum).name,
        )
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument(
        "--health-file",
        type=Path,
        default=_DEFAULT_HEALTH_FILE,
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    service: PurgeExpiredSensitivePayloads | None = None,
) -> int:
    arguments = _argument_parser().parse_args(argv)
    try:
        resolved_settings = settings or get_settings()
    except SettingsValidationError:
        configure_logging("INFO")
        get_logger(__name__).error("privacy_retention_configuration_invalid")
        return 1
    configure_logging(resolved_settings.log_level)
    if arguments.healthcheck:
        return (
            0
            if retention_healthcheck(
                path=arguments.health_file,
                interval_seconds=resolved_settings.privacy_lifecycle_interval_seconds,
            )
            else 1
        )
    if not resolved_settings.privacy_lifecycle_automation_enabled:
        logger.error("privacy_retention_automation_disabled")
        return 1
    tenant_id = resolved_settings.privacy_lifecycle_tenant_id
    if tenant_id is None:
        logger.error("privacy_retention_configuration_invalid")
        return 1
    try:
        resolved_service = service or build_sensitive_payload_retention_service(resolved_settings)
    except Exception as error:
        logger.error(
            "privacy_retention_composition_failed",
            error_type=type(error).__name__,
        )
        return 1
    stop_event = Event()
    _install_signal_handlers(stop_event)
    logger.info(
        "privacy_retention_scheduler_started",
        once=arguments.once,
        interval_seconds=resolved_settings.privacy_lifecycle_interval_seconds,
        batch_size=resolved_settings.privacy_lifecycle_batch_size,
        max_batches=resolved_settings.privacy_lifecycle_max_batches_per_sweep,
    )
    return run_automation_loop(
        resolved_service,
        tenant_id=str(tenant_id),
        batch_size=resolved_settings.privacy_lifecycle_batch_size,
        max_batches=resolved_settings.privacy_lifecycle_max_batches_per_sweep,
        interval_seconds=resolved_settings.privacy_lifecycle_interval_seconds,
        health_file=arguments.health_file,
        once=arguments.once,
        stop_event=stop_event,
    )


if __name__ == "__main__":
    raise SystemExit(main())
