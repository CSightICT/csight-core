"""Settings validation and secret-handling tests."""

import pytest
from pydantic import SecretStr, ValidationError

from app.bootstrap.settings import Settings

pytestmark = pytest.mark.unit


def test_defaults_use_mock_providers_without_infrastructure_secrets() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.llm_provider == "mock"
    assert settings.vision_provider == "mock"
    assert settings.vision_mock_mode == "success_single_defect"
    assert settings.database_url is None
    assert settings.rabbitmq_url is None
    assert settings.jwt_secret_key is None
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_token_expire_minutes == 30
    assert settings.development_seed_enabled is False
    assert settings.development_seed_admin_password is None
    assert settings.development_seed_reviewer_password is None
    assert settings.development_seed_quality_viewer_password is None
    assert settings.minio_access_key is None
    assert settings.minio_secret_key is None
    assert settings.minio_region == "us-east-1"
    assert settings.minio_presigned_endpoint_value is None
    assert settings.minio_presigned_secure_value is False
    assert settings.signed_url_ttl_seconds == 900
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.allowed_image_mime_types == {"image/jpeg", "image/png", "image/webp"}
    assert settings.allowed_image_extensions == {"jpg", "jpeg", "png", "webp"}
    assert settings.max_image_pixels == 40_000_000
    assert settings.llm_api_key is None
    assert settings.llm_model_id == "csight-mock-llm"
    assert settings.llm_model_version == "0.1.0"
    assert settings.llm_model_revision is None
    assert settings.vision_model_revision is None
    assert settings.llm_connect_timeout_seconds == 5.0
    assert settings.llm_read_timeout_seconds == 120.0
    assert settings.llm_max_output_tokens == 1024
    assert settings.llm_max_output_chars == 20_000
    assert settings.llm_max_input_chars == 20_000
    assert settings.llm_temperature == 0.0
    assert settings.llm_tls_verify is True
    assert settings.analysis_task_soft_time_limit_seconds == 150
    assert settings.analysis_task_hard_time_limit_seconds == 180
    assert settings.analysis_stage_lease_seconds == 300
    assert settings.analysis_outbox_poll_interval_seconds == 1.0
    assert settings.analysis_outbox_batch_size == 100
    assert settings.analysis_outbox_claim_seconds == 30
    assert settings.analysis_outbox_max_attempts == 10
    assert settings.analysis_outbox_retry_base_seconds == 1.0
    assert settings.analysis_outbox_retry_max_seconds == 60.0


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
    assert "user:password" not in repr(settings)


def test_jwt_settings_normalize_and_hide_secret() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        jwt_secret_key=SecretStr("a-random-local-secret-with-at-least-32-bytes"),
        jwt_algorithm="hs256",
        jwt_issuer=" csight-test ",
        jwt_audience=" csight-clients ",
    )

    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_issuer == "csight-test"
    assert settings.jwt_audience == "csight-clients"
    assert settings.jwt_secret_key_value == "a-random-local-secret-with-at-least-32-bytes"
    assert "a-random-local-secret" not in repr(settings)


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            jwt_secret_key=SecretStr("too-short"),
        )


def test_development_seed_passwords_are_redacted() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        development_seed_admin_password=SecretStr("a" * 16),
        development_seed_reviewer_password=SecretStr("r" * 16),
        development_seed_quality_viewer_password=SecretStr("q" * 16),
    )

    rendered = repr(settings)
    assert "a" * 16 not in rendered
    assert "r" * 16 not in rendered
    assert "q" * 16 not in rendered


def test_partial_minio_credentials_are_rejected() -> None:
    with pytest.raises(ValidationError, match="configured together"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            minio_endpoint="minio:9000",
            minio_access_key=SecretStr("access-only"),
        )


def test_presigned_endpoint_can_differ_from_internal_endpoint() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        minio_endpoint=" minio:9000/ ",
        minio_presigned_endpoint=" evidence.example.test:443/ ",
        minio_access_key=SecretStr("access"),
        minio_secret_key=SecretStr("secret"),
        minio_secure=False,
        minio_presigned_secure=True,
    )

    assert settings.minio_endpoint == "minio:9000"
    assert settings.minio_presigned_endpoint_value == "evidence.example.test:443"
    assert settings.minio_presigned_secure_value is True


def test_presigned_endpoint_requires_internal_minio_configuration() -> None:
    with pytest.raises(ValidationError, match="MINIO_ENDPOINT"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            minio_presigned_endpoint="evidence.example.test:443",
        )


def test_minio_endpoint_rejects_url_schemes() -> None:
    with pytest.raises(ValidationError, match="without a scheme"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            minio_endpoint="http://minio:9000",
            minio_access_key=SecretStr("access"),
            minio_secret_key=SecretStr("secret"),
        )


def test_upload_limits_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            max_upload_bytes=0,
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            max_image_pixels=178_956_971,
        )


def test_image_allowlists_are_normalized_and_reject_unsupported_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_IMAGE_MIME_TYPES", " IMAGE/PNG ")
    monkeypatch.setenv("ALLOWED_IMAGE_EXTENSIONS", " .PNG ")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.allowed_image_mime_types == {"image/png"}
    assert settings.allowed_image_extensions == {"png"}
    with pytest.raises(ValidationError, match="JPEG, PNG, and WebP"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            allowed_image_mime_types="image/svg+xml",
        )


def test_vllm_provider_requires_base_url() -> None:
    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            llm_provider="vllm",
        )


def test_mlx_provider_requires_base_url_and_is_allowlisted() -> None:
    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            llm_provider="mlx",
        )
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        llm_provider=" MLX ",
        llm_base_url="http://host.docker.internal:8080/v1",
    )
    assert settings.llm_provider == "mlx"
    assert settings.llm_base_url_value == "http://host.docker.internal:8080/v1"


def test_vllm_settings_are_normalized_bounded_and_keep_api_key_secret() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        llm_provider=" VLLM ",
        llm_base_url="https://llm.example.test/root/",
        llm_api_key=SecretStr("private-vllm-api-key"),
        llm_model_id=" configured/model ",
        llm_model_version=" deployment-v2 ",
        llm_model_revision=" revision-17 ",
        llm_connect_timeout_seconds=3.5,
        llm_read_timeout_seconds=90,
        llm_max_output_tokens=2048,
        llm_max_output_chars=40_000,
        llm_max_input_chars=25_000,
        llm_temperature=0.1,
        llm_tls_verify=False,
    )

    assert settings.llm_provider == "vllm"
    assert settings.llm_base_url_value == "https://llm.example.test/root"
    assert settings.llm_api_key_value == "private-vllm-api-key"
    assert settings.llm_model_id == "configured/model"
    assert settings.llm_model_version == "deployment-v2"
    assert settings.llm_model_revision == "revision-17"
    assert settings.llm_connect_timeout_seconds == 3.5
    assert settings.llm_read_timeout_seconds == 90
    assert settings.llm_max_output_tokens == 2048
    assert settings.llm_max_output_chars == 40_000
    assert settings.llm_max_input_chars == 25_000
    assert settings.llm_temperature == 0.1
    assert settings.llm_tls_verify is False
    assert "private-vllm-api-key" not in repr(settings)


def test_llm_provider_is_allowlisted() -> None:
    with pytest.raises(ValidationError, match=r"mock.*vllm.*mlx"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            llm_provider="unknown-provider",
        )


def test_vision_optional_identity_accepts_empty_compose_values() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        vision_api_key="",
        vision_model_revision="",
        vision_model_id=" configured-vision ",
        vision_model_version=" revision-1 ",
        vision_mock_mode="permanent_error",
    )

    assert settings.vision_api_key is None
    assert settings.vision_model_revision is None
    assert settings.vision_model_id == "configured-vision"
    assert settings.vision_model_version == "revision-1"
    assert settings.vision_mock_mode == "permanent_error"


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "analysis_task_soft_time_limit_seconds": 180,
            "analysis_task_hard_time_limit_seconds": 180,
        },
        {
            "analysis_task_hard_time_limit_seconds": 300,
            "analysis_stage_lease_seconds": 300,
        },
    ],
)
def test_analysis_stage_lease_strictly_exceeds_hard_and_soft_limits(
    overrides: dict[str, int],
) -> None:
    with pytest.raises(ValidationError, match="ANALYSIS_STAGE_LEASE_SECONDS"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            **overrides,
        )


def test_outbox_retry_window_is_ordered_but_claim_is_independent_of_task_limit() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        analysis_outbox_claim_seconds=1,
        analysis_task_hard_time_limit_seconds=180,
    )
    assert settings.analysis_outbox_claim_seconds == 1

    with pytest.raises(ValidationError, match="ANALYSIS_OUTBOX_RETRY_MAX_SECONDS"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            analysis_outbox_retry_base_seconds=61,
            analysis_outbox_retry_max_seconds=60,
        )
