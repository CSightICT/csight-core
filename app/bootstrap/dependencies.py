"""Composition root for infrastructure probes and Sprint 0 application services."""

from dataclasses import dataclass

from app.adapters.llm import MockLLMProvider
from app.adapters.messaging import RabbitMQReadinessProbe
from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.readiness import PostgresReadinessProbe
from app.adapters.storage import MinioReadinessProbe
from app.adapters.vision import MockVisionProvider
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
        return MockLLMProvider()
    raise ProviderConfigurationError(
        f"LLM provider adapter is not available: {settings.llm_provider!r}"
    )


def build_vision_provider(settings: Settings) -> VisionProvider:
    if settings.vision_provider == "mock":
        return MockVisionProvider()
    raise ProviderConfigurationError(
        f"Vision provider adapter is not available: {settings.vision_provider!r}"
    )


def build_analyze_case(settings: Settings) -> AnalyzeCase:
    """Compose the technology-neutral analysis skeleton from provider ports."""

    return AnalyzeCase(
        llm_provider=build_llm_provider(settings),
        vision_provider=build_vision_provider(settings),
    )
