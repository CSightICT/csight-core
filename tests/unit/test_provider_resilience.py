"""Circuit breaker and provider lifetime release gates."""

from __future__ import annotations

import pytest

from app.adapters.resilience import CircuitBreaker, CircuitOpenError, CircuitState
from app.bootstrap.dependencies import build_llm_provider
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.unit


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_circuit_opens_after_threshold_and_allows_exactly_one_probe() -> None:
    clock = _Clock()
    breaker = CircuitBreaker(failure_threshold=2, open_seconds=30.0, clock=clock)

    breaker.before_call()
    breaker.record_failure()
    assert breaker.snapshot().state is CircuitState.CLOSED

    breaker.before_call()
    breaker.record_failure()
    snapshot = breaker.snapshot()
    assert snapshot.state is CircuitState.OPEN
    assert snapshot.consecutive_failures == 2
    assert snapshot.retry_after_seconds == 30.0

    with pytest.raises(CircuitOpenError):
        breaker.before_call()

    clock.now = 30.0
    assert breaker.snapshot().state is CircuitState.HALF_OPEN
    breaker.before_call()
    with pytest.raises(CircuitOpenError):
        breaker.before_call()

    breaker.record_success()
    assert breaker.snapshot().state is CircuitState.CLOSED


def test_failed_half_open_probe_restarts_cooldown() -> None:
    clock = _Clock()
    breaker = CircuitBreaker(failure_threshold=1, open_seconds=30.0, clock=clock)
    breaker.record_failure()
    clock.now = 30.0

    breaker.before_call()
    breaker.record_failure()
    clock.now = 45.0

    snapshot = breaker.snapshot()
    assert snapshot.state is CircuitState.OPEN
    assert snapshot.retry_after_seconds == 15.0


def test_remote_provider_client_is_reused_only_for_same_process_settings() -> None:
    first_settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="test",
        llm_provider="vllm",
        llm_base_url="http://127.0.0.1:9999/v1",
    )
    second_settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="test",
        llm_provider="vllm",
        llm_base_url="http://127.0.0.1:9999/v1",
    )

    first = build_llm_provider(first_settings)

    assert build_llm_provider(first_settings) is first
    assert build_llm_provider(second_settings) is not first
