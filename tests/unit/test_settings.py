"""Settings validation and secret-handling tests."""

import pytest
from pydantic import SecretStr, ValidationError

from app.bootstrap.settings import Settings

pytestmark = pytest.mark.unit


def test_defaults_use_mock_providers_without_infrastructure_secrets() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.llm_provider == "mock"
    assert settings.vision_provider == "mock"
    assert settings.database_url is None
    assert settings.rabbitmq_url is None
    assert settings.minio_access_key is None
    assert settings.minio_secret_key is None


def test_settings_normalize_environment_values_and_hide_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("LLM_PROVIDER", " MOCK ")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db:5432/csight")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.log_level == "WARNING"
    assert settings.llm_provider == "mock"
    assert settings.database_url_value is not None
    assert "password" not in repr(settings)


def test_partial_minio_credentials_are_rejected() -> None:
    with pytest.raises(ValidationError, match="configured together"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            minio_endpoint="minio:9000",
            minio_access_key=SecretStr("access-only"),
        )


def test_non_mock_provider_requires_base_url() -> None:
    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            llm_provider="vllm",
        )
