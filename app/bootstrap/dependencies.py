"""Composition root for infrastructure probes and Sprint 0 application services."""

from collections.abc import Callable
from dataclasses import dataclass
from os import getpid

from app.adapters.llm import MLXLLMProvider, MockLLMProvider, VLLMLLMProvider
from app.adapters.messaging import RabbitMQReadinessProbe
from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.readiness import PostgresReadinessProbe
from app.adapters.resilience import (
    CircuitBreaker,
    CircuitBreakingLLMProvider,
    CircuitBreakingVisionProvider,
)
from app.adapters.storage import MinioReadinessProbe
from app.adapters.vision import MockVisionProvider, RemoteVisionProvider
from app.application.analyze_case import AnalyzeCase
from app.bootstrap.settings import Settings
from app.platform.analysis import VisionTask
from app.platform.model_activation import ModelReleaseTask
from app.ports.llm import LLMProvider
from app.ports.readiness import DependencyProbe, ReadinessService
from app.ports.vision import VisionProvider


class ProviderConfigurationError(RuntimeError):
    """Raised when a configured provider has no installed Sprint 0 adapter."""


@dataclass(slots=True)
class _ProviderCacheEntry:
    settings: Settings
    provider: object


_PROCESS_PROVIDER_CACHE: dict[tuple[int, str], _ProviderCacheEntry] = {}


def _cached_process_provider(
    *,
    kind: str,
    settings: Settings,
    factory: Callable[[], object],
) -> object:
    """Reuse a provider only inside the process that constructed it.

    The PID key prevents a prefork worker from inheriting a parent's connection
    pool.  Settings identity prevents tests or application instances with a
    different configuration from sharing credentials or circuit state.
    """

    key = (getpid(), kind)
    existing = _PROCESS_PROVIDER_CACHE.get(key)
    if existing is not None and existing.settings is settings:
        return existing.provider
    provider = factory()
    _PROCESS_PROVIDER_CACHE[key] = _ProviderCacheEntry(settings=settings, provider=provider)
    return provider


@dataclass(frozen=True, slots=True)
class _UnavailableReadinessProbe:
    name: str

    def check(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class _ConfigurationReadinessProbe:
    name: str
    configured: bool

    def check(self) -> bool:
        return self.configured


def build_readiness_service(settings: Settings) -> ReadinessService:
    """Compose fail-closed probes for every mandatory Core dependency."""

    probes: list[DependencyProbe] = []

    if settings.database_url_value:
        probes.append(PostgresReadinessProbe(lambda: get_engine(settings)))
    else:
        probes.append(_UnavailableReadinessProbe(name="postgresql"))

    rabbitmq_url = settings.rabbitmq_url_value
    if rabbitmq_url:
        probes.append(
            RabbitMQReadinessProbe(
                rabbitmq_url,
                timeout_seconds=settings.readiness_timeout_seconds,
            )
        )
    else:
        probes.append(_UnavailableReadinessProbe(name="rabbitmq"))

    access_key = settings.minio_access_key_value
    secret_key = settings.minio_secret_key_value
    if settings.minio_endpoint and access_key and secret_key:
        try:
            minio_probe: DependencyProbe = MinioReadinessProbe(
                endpoint=settings.minio_endpoint,
                access_key=access_key,
                secret_key=secret_key,
                bucket=settings.minio_bucket,
                secure=settings.minio_secure,
                timeout_seconds=settings.readiness_timeout_seconds,
            )
        except Exception:
            minio_probe = _UnavailableReadinessProbe(name="minio")
        probes.append(minio_probe)
    else:
        probes.append(_UnavailableReadinessProbe(name="minio"))

    if settings.environment not in {"local", "test"}:
        probes.append(
            _ConfigurationReadinessProbe(
                name="oidc_configuration",
                configured=settings.oidc_is_configured,
            )
        )
        probes.append(
            _ConfigurationReadinessProbe(
                name="telemetry_configuration",
                configured=settings.otel_is_configured,
            )
        )

    return ReadinessService(probes=tuple(probes))


def build_llm_provider(
    settings: Settings,
    task: ModelReleaseTask = ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
) -> LLMProvider:
    task_runtime = settings.llm_task_runtimes.get(task)
    model_id = task_runtime.model_id if task_runtime is not None else settings.llm_model_id
    model_version = (
        task_runtime.model_version if task_runtime is not None else settings.llm_model_version
    )
    model_revision = (
        task_runtime.model_revision if task_runtime is not None else settings.llm_model_revision
    )
    base_url = (
        str(task_runtime.base_url).rstrip("/")
        if task_runtime is not None
        else settings.llm_base_url_value
    )
    connect_timeout = (
        task_runtime.connect_timeout_seconds
        if task_runtime is not None
        else settings.llm_connect_timeout_seconds
    )
    read_timeout = (
        task_runtime.read_timeout_seconds
        if task_runtime is not None
        else settings.llm_read_timeout_seconds
    )
    circuit_threshold = (
        task_runtime.circuit_failure_threshold
        if task_runtime is not None
        else settings.provider_circuit_failure_threshold
    )
    circuit_open_seconds = (
        task_runtime.circuit_open_seconds
        if task_runtime is not None
        else settings.provider_circuit_open_seconds
    )
    if settings.llm_provider == "mock":
        return MockLLMProvider(
            model_name=model_id,
            model_version=model_version,
            model_revision=model_revision or "deterministic",
        )
    if settings.llm_provider == "vllm":
        if base_url is None:
            raise ProviderConfigurationError("LLM_BASE_URL is required for the vLLM adapter")
        return _as_llm_provider(
            _cached_process_provider(
                kind=f"llm:{task.value}",
                settings=settings,
                factory=lambda: CircuitBreakingLLMProvider(
                    VLLMLLMProvider(
                        base_url=base_url,
                        api_key=settings.llm_api_key_value,
                        model_id=model_id,
                        model_version=model_version,
                        model_revision=model_revision,
                        connect_timeout_seconds=connect_timeout,
                        read_timeout_seconds=read_timeout,
                        max_output_tokens=settings.llm_max_output_tokens,
                        max_output_chars=settings.llm_max_output_chars,
                        max_input_chars=settings.llm_max_input_chars,
                        temperature=settings.llm_temperature,
                        tls_verify=settings.llm_tls_verify,
                    ),
                    breaker=CircuitBreaker(
                        failure_threshold=circuit_threshold,
                        open_seconds=circuit_open_seconds,
                    ),
                ),
            )
        )
    if settings.llm_provider == "mlx":
        if base_url is None:
            raise ProviderConfigurationError("LLM_BASE_URL is required for the MLX adapter")
        return _as_llm_provider(
            _cached_process_provider(
                kind=f"llm:{task.value}",
                settings=settings,
                factory=lambda: CircuitBreakingLLMProvider(
                    MLXLLMProvider(
                        base_url=base_url,
                        api_key=settings.llm_api_key_value,
                        model_id=model_id,
                        model_version=model_version,
                        model_revision=model_revision,
                        connect_timeout_seconds=connect_timeout,
                        read_timeout_seconds=read_timeout,
                        max_output_tokens=settings.llm_max_output_tokens,
                        max_output_chars=settings.llm_max_output_chars,
                        max_input_chars=settings.llm_max_input_chars,
                        temperature=settings.llm_temperature,
                        tls_verify=settings.llm_tls_verify,
                    ),
                    breaker=CircuitBreaker(
                        failure_threshold=circuit_threshold,
                        open_seconds=circuit_open_seconds,
                    ),
                ),
            )
        )
    raise ProviderConfigurationError(
        f"LLM provider adapter is not available: {settings.llm_provider!r}"
    )


def build_vision_provider(settings: Settings) -> VisionProvider:
    if settings.vision_provider == "mock":
        return MockVisionProvider(
            mode=settings.vision_mock_mode,
            model_name=settings.vision_model_id,
            model_version=settings.vision_model_version,
            analysis_task=VisionTask(settings.vision_task),
            assessment_threshold=settings.vision_assessment_expected_threshold,
        )
    if settings.vision_provider == "remote":
        base_url = settings.vision_base_url_value
        if base_url is None:
            raise ProviderConfigurationError(
                "VISION_BASE_URL is required for the remote Vision adapter"
            )
        return _as_vision_provider(
            _cached_process_provider(
                kind="vision",
                settings=settings,
                factory=lambda: CircuitBreakingVisionProvider(
                    RemoteVisionProvider(
                        base_url=base_url,
                        api_key=settings.vision_api_key_value,
                        model_id=settings.vision_model_id,
                        model_version=settings.vision_model_version,
                        model_revision=settings.vision_model_revision,
                        connect_timeout_seconds=settings.vision_connect_timeout_seconds,
                        read_timeout_seconds=settings.vision_read_timeout_seconds,
                        max_image_bytes=settings.vision_max_image_bytes,
                        analysis_task=VisionTask(settings.vision_task),
                        expected_assessment_threshold=(
                            settings.vision_assessment_expected_threshold
                        ),
                        tls_verify=settings.vision_tls_verify,
                    ),
                    breaker=CircuitBreaker(
                        failure_threshold=settings.provider_circuit_failure_threshold,
                        open_seconds=settings.provider_circuit_open_seconds,
                    ),
                ),
            )
        )
    raise ProviderConfigurationError(
        f"Vision provider adapter is not available: {settings.vision_provider!r}"
    )


def build_analyze_case(settings: Settings) -> AnalyzeCase:
    """Compose the technology-neutral analysis skeleton from provider ports."""

    return AnalyzeCase(
        llm_provider=build_llm_provider(settings),
        vision_provider=build_vision_provider(settings),
    )


def _as_llm_provider(value: object) -> LLMProvider:
    if not isinstance(value, LLMProvider):
        raise TypeError("cached provider does not implement the LLM port")
    return value


def _as_vision_provider(value: object) -> VisionProvider:
    if not isinstance(value, VisionProvider):
        raise TypeError("cached provider does not implement the Vision port")
    return value
