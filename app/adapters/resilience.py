"""Process-local provider bulkhead primitives and port-preserving wrappers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from time import monotonic
from typing import TypeVar

from app.platform.analysis import (
    AnalysisProviderError,
    LLMAnalysisRequest,
    LLMCaseExtraction,
    LLMProviderUnavailableError,
    ProviderMetadata,
    VisionAnalysisRequest,
    VisionAnalysisResult,
    VisionProviderUnavailableError,
    VisionTask,
)
from app.platform.analysis.llm_v2 import (
    LLMTextExtractionRequestV2,
    LLMTextExtractionResponseV2,
)
from app.platform.analysis.prompts import PromptManifest
from app.platform.analysis.schemas import LLMTextExtractionRequest, LLMTextExtractionResponse
from app.platform.grounding import GroundedExplanationInput, GroundedExplanationResponse
from app.platform.query_builder import PolicyQueryBuilderInput, PolicyQueryBuilderResponse
from app.ports.llm import LLMProvider
from app.ports.vision import VisionProvider

ResultT = TypeVar("ResultT")


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(RuntimeError):
    """Raised locally before a provider call while its circuit is open."""


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    state: CircuitState
    consecutive_failures: int
    retry_after_seconds: float | None


class CircuitBreaker:
    """Small thread-safe breaker for timeout/429/5xx-style provider failures."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        open_seconds: float = 30.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if open_seconds <= 0:
            raise ValueError("open_seconds must be positive")
        self._failure_threshold = failure_threshold
        self._open_seconds = open_seconds
        self._clock = clock
        self._lock = Lock()
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False

    def before_call(self) -> None:
        with self._lock:
            if self._opened_at is None:
                return
            elapsed = max(0.0, self._clock() - self._opened_at)
            if elapsed < self._open_seconds:
                raise CircuitOpenError("provider circuit is open")
            if self._half_open_probe_in_flight:
                raise CircuitOpenError("provider circuit half-open probe is in progress")
            self._half_open_probe_in_flight = True

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_probe_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if (
                self._half_open_probe_in_flight
                or self._consecutive_failures >= self._failure_threshold
            ):
                self._opened_at = self._clock()
            self._half_open_probe_in_flight = False

    def snapshot(self) -> CircuitSnapshot:
        with self._lock:
            if self._opened_at is None:
                return CircuitSnapshot(
                    state=CircuitState.CLOSED,
                    consecutive_failures=self._consecutive_failures,
                    retry_after_seconds=None,
                )
            remaining = max(0.0, self._open_seconds - (self._clock() - self._opened_at))
            state = CircuitState.OPEN if remaining > 0 else CircuitState.HALF_OPEN
            return CircuitSnapshot(
                state=state,
                consecutive_failures=self._consecutive_failures,
                retry_after_seconds=remaining,
            )


class CircuitBreakingLLMProvider:
    """Preserve the LLM port while failing fast during a transient outage."""

    def __init__(self, provider: LLMProvider, *, breaker: CircuitBreaker) -> None:
        self._provider = provider
        self._breaker = breaker

    @property
    def provider_metadata(self) -> ProviderMetadata:
        return self._provider.provider_metadata

    @property
    def circuit_snapshot(self) -> CircuitSnapshot:
        return self._breaker.snapshot()

    def extract_case(self, request: LLMAnalysisRequest) -> LLMCaseExtraction:
        return self._call(lambda: self._provider.extract_case(request))

    def extract_text(
        self,
        request: LLMTextExtractionRequest,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponse:
        return self._call(lambda: self._provider.extract_text(request, prompt))

    def extract_text_v2(
        self,
        request: LLMTextExtractionRequestV2,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponseV2:
        return self._call(lambda: self._provider.extract_text_v2(request, prompt))

    def build_policy_queries(
        self,
        request: PolicyQueryBuilderInput,
        prompt: PromptManifest,
    ) -> PolicyQueryBuilderResponse:
        return self._call(lambda: self._provider.build_policy_queries(request, prompt))

    def explain_policy_grounded(
        self,
        request: GroundedExplanationInput,
        prompt: PromptManifest,
    ) -> GroundedExplanationResponse:
        return self._call(lambda: self._provider.explain_policy_grounded(request, prompt))

    def _call(self, operation: Callable[[], ResultT]) -> ResultT:
        try:
            self._breaker.before_call()
        except CircuitOpenError:
            raise LLMProviderUnavailableError(
                provider=self.provider_metadata.provider,
                message="the provider circuit is open after repeated transient failures",
            ) from None
        try:
            result = operation()
        except AnalysisProviderError as error:
            if error.retryable:
                self._breaker.record_failure()
            else:
                self._breaker.record_success()
            raise
        except Exception:
            # Query-builder and grounding schema guards deliberately raise their
            # technology-neutral domain errors. They are terminal outcomes, not
            # provider outages, and must also release a half-open probe.
            self._breaker.record_success()
            raise
        self._breaker.record_success()
        return result


class CircuitBreakingVisionProvider:
    """Preserve the Vision port while failing fast during a transient outage."""

    def __init__(self, provider: VisionProvider, *, breaker: CircuitBreaker) -> None:
        self._provider = provider
        self._breaker = breaker

    @property
    def provider_metadata(self) -> ProviderMetadata:
        return self._provider.provider_metadata

    @property
    def analysis_task(self) -> VisionTask:
        return self._provider.analysis_task

    @property
    def circuit_snapshot(self) -> CircuitSnapshot:
        return self._breaker.snapshot()

    def analyze_image(
        self,
        request: VisionAnalysisRequest,
        *,
        image: bytes,
    ) -> VisionAnalysisResult:
        try:
            self._breaker.before_call()
        except CircuitOpenError:
            raise VisionProviderUnavailableError(
                provider=self.provider_metadata.provider,
                message="the provider circuit is open after repeated transient failures",
            ) from None
        try:
            result = self._provider.analyze_image(request, image=image)
        except AnalysisProviderError as error:
            if error.retryable:
                self._breaker.record_failure()
            else:
                self._breaker.record_success()
            raise
        self._breaker.record_success()
        return result


__all__ = [
    "CircuitBreaker",
    "CircuitBreakingLLMProvider",
    "CircuitBreakingVisionProvider",
    "CircuitOpenError",
    "CircuitSnapshot",
    "CircuitState",
]
