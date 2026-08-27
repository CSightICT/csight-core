"""Framework-free errors shared by leased asynchronous application flows."""

from __future__ import annotations

from datetime import datetime


class ExecutionLeaseActiveError(RuntimeError):
    """A duplicate delivery arrived while another execution lease is active."""

    def __init__(self, *, retry_at: datetime) -> None:
        super().__init__("The asynchronous run already has an active execution lease.")
        self.retry_at = retry_at


class AsyncEventIntegrityError(RuntimeError):
    """A broker delivery does not match its durable request event."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ExecutionAttemptsExhaustedError(RuntimeError):
    """A run was durably failed after its bounded worker-loss recoveries."""

    def __init__(self, *, code: str) -> None:
        super().__init__("The asynchronous run exhausted its execution recovery attempts.")
        self.code = code


__all__ = [
    "AsyncEventIntegrityError",
    "ExecutionAttemptsExhaustedError",
    "ExecutionLeaseActiveError",
]
