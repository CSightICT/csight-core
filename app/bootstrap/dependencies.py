"""Composition root for infrastructure probes and Sprint 0 application services."""

from dataclasses import dataclass

from app.adapters.llm import MLXLLMProvider, MockLLMProvider, VLLMLLMProvider
from app.adapters.messaging import RabbitMQReadinessProbe
from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.readiness import PostgresReadinessProbe
from app.adapters.storage import MinioReadinessProbe
from app.adapters.vision import MockVisionProvider, RemoteVisionProvider
from app.application.analyze_case import AnalyzeCase
from app.bootstrap.settings import Settings
from app.ports.llm import LLMProvider
from app.ports.readiness import DependencyProbe, ReadinessService
from app.ports.vision import VisionProvider


class ProviderConfigurationError(RuntimeError):
    """Raised when a configured provider has no installed Sprint 0 adapter."""


@dataclass(frozen=True, slots=True)
class _UnavailableReadinessProbe:
    name: str

    def check(self) -> bool:
        return False


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

    return ReadinessService(probes=tuple(probes))


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider(
            model_name=settings.llm_model_id,
            model_version=settings.llm_model_version,
            model_revision=settings.llm_model_revision or "deterministic",
        )
    if settings.llm_provider == "vllm":
        base_url = settings.llm_base_url_value
        if base_url is None:
            raise ProviderConfigurationError("LLM_BASE_URL is required for the vLLM adapter")
        return VLLMLLMProvider(
            base_url=base_url,
            api_key=settings.llm_api_key_value,
            model_id=settings.llm_model_id,
            model_version=settings.llm_model_version,
            model_revision=settings.llm_model_revision,
            connect_timeout_seconds=settings.llm_connect_timeout_seconds,
            read_timeout_seconds=settings.llm_read_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
            max_output_chars=settings.llm_max_output_chars,
            max_input_chars=settings.llm_max_input_chars,
            temperature=settings.llm_temperature,
            tls_verify=settings.llm_tls_verify,
        )
    if settings.llm_provider == "mlx":
        base_url = settings.llm_base_url_value
        if base_url is None:
            raise ProviderConfigurationError("LLM_BASE_URL is required for the MLX adapter")
        return MLXLLMProvider(
            base_url=base_url,
            api_key=settings.llm_api_key_value,
            model_id=settings.llm_model_id,
            model_version=settings.llm_model_version,
            model_revision=settings.llm_model_revision,
            connect_timeout_seconds=settings.llm_connect_timeout_seconds,
            read_timeout_seconds=settings.llm_read_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
            max_output_chars=settings.llm_max_output_chars,
            max_input_chars=settings.llm_max_input_chars,
            temperature=settings.llm_temperature,
            tls_verify=settings.llm_tls_verify,
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
        )
    if settings.vision_provider == "remote":
        base_url = settings.vision_base_url_value
        if base_url is None:
            raise ProviderConfigurationError(
                "VISION_BASE_URL is required for the remote Vision adapter"
            )
        return RemoteVisionProvider(
            base_url=base_url,
            api_key=settings.vision_api_key_value,
            model_id=settings.vision_model_id,
            model_version=settings.vision_model_version,
            model_revision=settings.vision_model_revision,
            connect_timeout_seconds=settings.vision_connect_timeout_seconds,
            read_timeout_seconds=settings.vision_read_timeout_seconds,
            max_image_bytes=settings.vision_max_image_bytes,
            tls_verify=settings.vision_tls_verify,
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
