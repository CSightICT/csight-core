"""Settings validation and secret-handling tests."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.bootstrap.settings import Settings
from app.platform.tenant import Role
from tests.unit.test_model_activation_gguf import (
    gguf_manifest_fixture,
    gguf_runtime_identity_fixture,
)

pytestmark = pytest.mark.unit


def test_defaults_use_mock_providers_without_infrastructure_secrets() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.llm_provider == "mock"
    assert settings.vision_provider == "mock"
    assert settings.vision_mock_mode == "success_single_defect"
    assert settings.vision_task == "QUALITY_AND_DEFECT_DETECTION"
    assert settings.vision_assessment_expected_threshold is None
    assert settings.database_url is None
    assert settings.database_password_file is None
    assert settings.database_runtime_role == "legacy_owner"
    assert settings.database_rls_required is False
    assert settings.rabbitmq_url is None
    assert settings.jwt_secret_key is None
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_token_expire_minutes == 30
    assert settings.legacy_password_enabled is True
    assert settings.oidc_enabled is False
    assert settings.oidc_is_configured is False
    assert settings.oidc_allow_insecure_http is False
    assert settings.oidc_session_absolute_timeout_seconds == 8 * 60 * 60
    assert settings.oidc_session_idle_timeout_seconds == 30 * 60
    assert settings.oidc_session_expiry_warning_seconds == 5 * 60
    assert settings.signed_intake_enabled is False
    assert settings.signed_intake_sources == {}
    assert settings.signed_intake_is_configured is False
    assert settings.signed_intake_clock_skew_seconds == 300
    assert settings.signed_intake_max_body_bytes == 128 * 1024
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
    assert settings.sensitive_payload_retention_policy_version_value == "development/30d"
    assert settings.sensitive_payload_retention_days_value == 30
    assert settings.llm_api_key is None
    assert settings.llm_model_id == "csight-mock-llm"
    assert settings.llm_model_version == "0.1.0"
    assert settings.llm_model_revision is None
    assert settings.model_release_enforcement is False
    assert settings.model_route_enforcement is False
    assert settings.model_route_deployment_id is None
    assert settings.model_release_signing_public_key_file is None
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


def test_signed_intake_configuration_is_tenant_bound_and_requires_rls_outside_local(
    tmp_path: Path,
) -> None:
    source = {
        "crm-key-1": {
            "source_id": "customer-crm",
            "tenant_id": "00000000-0000-4000-8000-000000000101",
            "actor_user_id": "00000000-0000-4000-8000-000000000102",
            "provenance": "signed/crm/v1",
            "public_key_file": str(tmp_path / "crm-public.pem"),
        }
    }
    local = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr("postgresql+psycopg://api@db/csight"),
        signed_intake_enabled=True,
        signed_intake_sources=source,
        sensitive_payload_retention_policy_version="pilot/30d",
        sensitive_payload_retention_days=30,
    )
    assert local.signed_intake_is_configured is True
    assert str(local.signed_intake_sources["crm-key-1"].tenant_id).endswith("0101")

    with pytest.raises(ValidationError, match="RLS-enforced API database role"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="pilot",
            database_url=SecretStr("postgresql+psycopg://owner@db/csight"),
            signed_intake_enabled=True,
            signed_intake_sources=source,
            sensitive_payload_retention_policy_version="pilot/30d",
            sensitive_payload_retention_days=30,
        )


@pytest.mark.parametrize("provider", ["vllm", "llama_cpp", "mlx"])
def test_non_local_llm_requires_signed_release_enforcement(provider: str) -> None:
    with pytest.raises(ValidationError, match="Non-local LLM requires"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="pilot",
            llm_provider=provider,  # pyright: ignore[reportArgumentType]
            llm_base_url="https://llm.example.test/v1",
        )


def test_non_local_environment_rejects_legacy_password_auth() -> None:
    with pytest.raises(ValidationError, match="must be false outside local/test"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="pilot",
            legacy_password_auth_enabled=True,
        )

    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="pilot",
    )
    assert settings.legacy_password_enabled is False


def test_signed_release_enforcement_requires_exact_runtime_identity(tmp_path: Path) -> None:
    public_key = tmp_path / "release-key.pem"
    public_key.write_text("placeholder", encoding="utf-8")
    with pytest.raises(ValidationError, match="exact 40-character commit hash"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            database_url=SecretStr("postgresql+psycopg://worker@db/csight"),
            llm_provider="vllm",
            llm_base_url="https://llm.example.test/v1",
            model_release_enforcement=True,
            model_release_signing_public_key_file=public_key,
            model_release_signing_key_id="release-key-1",
            llm_model_revision="floating-main",
            llm_artifact_content_digest="sha256:" + "a" * 64,
            llm_runtime_image_digest="sha256:" + "b" * 64,
            llm_dependency_lock_digest="sha256:" + "c" * 64,
            llm_sbom_digest="sha256:" + "d" * 64,
        )


def test_non_local_llama_cpp_accepts_complete_signed_runtime_identity(tmp_path: Path) -> None:
    identity = gguf_runtime_identity_fixture(gguf_manifest_fixture())
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="pilot",
        database_url=SecretStr("postgresql+psycopg://worker@db/csight"),
        llm_provider="llama_cpp",
        llm_base_url="http://100.64.0.20:18000/v1",
        model_release_enforcement=True,
        model_release_signing_public_key_file=tmp_path / "release-key.pem",
        model_release_signing_key_id="release-key-1",
        llm_model_id=identity.served_model_name,
        llm_model_version=identity.model_version,
        llm_model_revision=identity.artifact_revision,
        llm_gguf_runtime_identity=identity,
    )

    assert settings.llm_provider == "llama_cpp"
    assert settings.model_release_enforcement is True
    assert settings.llm_gguf_runtime_identity == identity


def test_model_route_enforcement_is_role_aware_and_requires_signed_release(
    tmp_path: Path,
) -> None:
    release = {
        "database_url": SecretStr("postgresql+psycopg://runtime@db/csight"),
        "database_rls_required": True,
        "llm_provider": "vllm",
        "llm_base_url": "https://llm.example.test/v1",
        "model_release_enforcement": True,
        "model_release_signing_public_key_file": tmp_path / "release-key.pem",
        "model_release_signing_key_id": "release-key-1",
        "llm_model_revision": "a" * 40,
        "llm_artifact_content_digest": "sha256:" + "b" * 64,
        "llm_runtime_image_digest": "sha256:" + "c" * 64,
        "llm_dependency_lock_digest": "sha256:" + "d" * 64,
        "llm_sbom_digest": "sha256:" + "e" * 64,
    }
    api = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        **release,
        database_runtime_role="api",
        model_route_enforcement=True,
    )
    worker = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        **release,
        database_runtime_role="worker",
        model_route_enforcement=True,
        model_route_deployment_id="onprem-4090-primary",
    )

    assert api.model_route_deployment_id is None
    assert worker.model_route_deployment_id == "onprem-4090-primary"

    with pytest.raises(ValidationError, match="requires MODEL_RELEASE_ENFORCEMENT"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            database_runtime_role="api",
            model_route_enforcement=True,
        )
    with pytest.raises(ValidationError, match="Worker MODEL_ROUTE_ENFORCEMENT requires"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            **release,
            database_runtime_role="worker",
            model_route_enforcement=True,
        )
    with pytest.raises(ValidationError, match="API process must not receive"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            **release,
            database_runtime_role="api",
            model_route_enforcement=True,
            model_route_deployment_id="onprem-4090-primary",
        )
    with pytest.raises(ValidationError, match="may only be set"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            model_route_deployment_id="onprem-4090-primary",
        )


def test_rls_required_rejects_owner_and_migration_profiles() -> None:
    with pytest.raises(ValidationError, match="requires an api, worker, or dispatcher"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            database_rls_required=True,
            database_runtime_role="legacy_owner",
        )

    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr("postgresql+psycopg://runtime@db/csight"),
        database_rls_required=True,
        database_runtime_role="api",
    )
    assert settings.database_runtime_role == "api"


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


def test_database_password_file_injects_and_escapes_secret(tmp_path: Path) -> None:
    password_file = tmp_path / "database-password"
    password_file.write_text("p@ss:word/with%reserved\n", encoding="utf-8")

    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr("postgresql+psycopg://runtime@db:5432/csight"),
        database_password_file=password_file,
    )

    resolved = settings.database_url_value
    assert resolved is not None
    assert "p%40ss%3Aword%2Fwith%25reserved" in resolved
    assert "p@ss:word" not in repr(settings)


def test_database_password_file_contract_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing-password"
    with pytest.raises(ValidationError, match="cannot be read"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            database_url=SecretStr("postgresql+psycopg://runtime@db:5432/csight"),
            database_password_file=missing,
            database_runtime_role="api",
            database_rls_required=True,
        )

    password_file = tmp_path / "database-password"
    password_file.write_text("separate-secret", encoding="utf-8")
    with pytest.raises(ValidationError, match="must omit its password"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            database_url=SecretStr("postgresql+psycopg://runtime:inline@db:5432/csight"),
            database_password_file=password_file,
        )


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


def test_oidc_environment_mapping_is_typed_secret_redacted_and_fully_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:secret@db:5432/csight")
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.example.test")
    monkeypatch.setenv("OIDC_CLIENT_ID", "csight-client")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "private-client-secret")
    monkeypatch.setenv("OIDC_AUTHORIZATION_ENDPOINT", "https://idp.example.test/authorize")
    monkeypatch.setenv("OIDC_TOKEN_ENDPOINT", "https://idp.example.test/token")
    monkeypatch.setenv("OIDC_JWKS_URI", "https://idp.example.test/jwks")
    monkeypatch.setenv(
        "OIDC_REDIRECT_URI",
        "https://csight.example.test/auth/oidc/callback",
    )
    monkeypatch.setenv(
        "OIDC_GROUP_MAPPINGS",
        '{"idp/reviewers":{"tenant_slug":"tenant-a","allowed_roles":["REVIEWER"]}}',
    )
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.oidc_is_configured is True
    assert settings.oidc_group_mappings["idp/reviewers"].allowed_roles == {Role.REVIEWER}
    assert settings.oidc_client_secret_value == "private-client-secret"
    assert "private-client-secret" not in repr(settings)


def test_oidc_callback_timeout_and_https_contracts_fail_closed() -> None:
    with pytest.raises(ValidationError, match="/auth/oidc/callback"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            oidc_redirect_uri="https://csight.example.test/wrong-callback",
        )
    with pytest.raises(ValidationError, match="idle and warning"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            oidc_session_absolute_timeout_seconds=300,
            oidc_session_idle_timeout_seconds=301,
        )
    insecure = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        oidc_enabled=True,
        database_url=SecretStr("postgresql+psycopg://user:secret@db:5432/csight"),
        oidc_issuer="http://idp.example.test",
        oidc_client_id="csight-client",
        oidc_authorization_endpoint="http://idp.example.test/authorize",
        oidc_token_endpoint="http://idp.example.test/token",
        oidc_jwks_uri="http://idp.example.test/jwks",
        oidc_redirect_uri="http://csight.example.test/auth/oidc/callback",
        oidc_group_mappings={
            "idp/reviewers": {
                "tenant_slug": "tenant-a",
                "allowed_roles": ["REVIEWER"],
            }
        },
    )
    assert insecure.oidc_is_configured is False
    assert "OIDC_HTTPS_ENDPOINTS" in insecure.oidc_configuration_missing


def test_oidc_insecure_http_requires_explicit_local_or_test_opt_in() -> None:
    values = {
        "oidc_enabled": True,
        "database_url": SecretStr("postgresql+psycopg://user:secret@db:5432/csight"),
        "oidc_issuer": "http://idp.test:8080/realms/csight",
        "oidc_client_id": "csight-client",
        "oidc_authorization_endpoint": "http://127.0.0.1:18080/authorize",
        "oidc_token_endpoint": "http://keycloak:8080/token",
        "oidc_jwks_uri": "http://keycloak:8080/jwks",
        "oidc_redirect_uri": "http://127.0.0.1:18000/auth/oidc/callback",
        "oidc_group_mappings": {
            "idp/reviewers": {
                "tenant_slug": "tenant-a",
                "allowed_roles": ["REVIEWER"],
            }
        },
        "oidc_allow_insecure_http": True,
    }

    qualification = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="test",
        **values,
    )
    assert qualification.oidc_is_configured is True

    with pytest.raises(ValidationError, match="only be enabled in local/test"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="production",
            **values,
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


def test_clamav_scanner_requires_host_and_normalizes_configuration() -> None:
    with pytest.raises(ValidationError, match="CLAMAV_HOST"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            evidence_malware_scanner="clamav",
        )

    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        evidence_image_sanitization_enabled=True,
        evidence_malware_scanner=" CLAMAV ",
        clamav_host=" scanner.internal ",
    )

    assert settings.evidence_malware_scanner == "clamav"
    assert settings.clamav_host == "scanner.internal"


def test_sensitive_payload_retention_is_explicit_outside_local_and_paired() -> None:
    production = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="production",
    )
    assert production.sensitive_payload_retention_policy_version_value is None
    assert production.sensitive_payload_retention_days_value is None

    with pytest.raises(ValidationError, match="must be configured together"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            sensitive_payload_retention_days=90,
        )

    configured = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="production",
        sensitive_payload_retention_policy_version=" customer-a/90d ",
        sensitive_payload_retention_days=90,
    )
    assert configured.sensitive_payload_retention_policy_version_value == "customer-a/90d"
    assert configured.sensitive_payload_retention_days_value == 90


def test_retention_automation_requires_explicit_tenant_policy_and_strict_nonlocal_db() -> None:
    tenant_id = "00000000-0000-4000-8000-000000000001"
    disabled = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        privacy_lifecycle_tenant_id=" ",
    )
    assert disabled.privacy_lifecycle_tenant_id is None

    with pytest.raises(ValidationError, match="PRIVACY_LIFECYCLE_TENANT_ID"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            privacy_lifecycle_automation_enabled=True,
            sensitive_payload_retention_policy_version="customer/90d",
            sensitive_payload_retention_days=90,
            database_url=SecretStr("postgresql+psycopg://runtime@db/csight"),
        )

    with pytest.raises(ValidationError, match="explicit"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            privacy_lifecycle_automation_enabled=True,
            privacy_lifecycle_tenant_id=tenant_id,
            database_url=SecretStr("postgresql+psycopg://runtime@db/csight"),
        )

    with pytest.raises(ValidationError, match="RLS-enforced API"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="pilot",
            privacy_lifecycle_automation_enabled=True,
            privacy_lifecycle_tenant_id=tenant_id,
            sensitive_payload_retention_policy_version="customer/90d",
            sensitive_payload_retention_days=90,
            database_url=SecretStr("postgresql+psycopg://runtime@db/csight"),
        )

    configured = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="pilot",
        privacy_lifecycle_automation_enabled=True,
        privacy_lifecycle_tenant_id=tenant_id,
        sensitive_payload_retention_policy_version="customer/90d",
        sensitive_payload_retention_days=90,
        database_url=SecretStr("postgresql+psycopg://runtime@db/csight"),
        database_runtime_role="api",
        database_rls_required=True,
    )
    assert str(configured.privacy_lifecycle_tenant_id) == tenant_id


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


def test_llama_cpp_provider_requires_base_url_and_is_allowlisted() -> None:
    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            llm_provider="llama_cpp",
        )
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        llm_provider=" LLAMA_CPP ",
        llm_base_url="http://100.64.0.20:18000/v1",
    )
    assert settings.llm_provider == "llama_cpp"
    assert settings.llm_base_url_value == "http://100.64.0.20:18000/v1"


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
    with pytest.raises(ValidationError, match=r"mock.*vllm.*llama_cpp.*mlx"):
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
    "values",
    [
        {
            "vision_mock_mode": "binary_candidate",
            "vision_task": "ANY_DEFECT_CLASSIFICATION",
        },
        {
            "vision_provider": "remote",
            "vision_base_url": "https://vision.internal",
            "vision_task": "ANY_DEFECT_CLASSIFICATION",
        },
    ],
)
def test_binary_vision_requires_an_explicit_expected_threshold(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="VISION_ASSESSMENT_EXPECTED_THRESHOLD"):
        Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


def test_binary_vision_accepts_report_frozen_threshold_only_when_explicit() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        vision_mock_mode="binary_below_threshold",
        vision_task="ANY_DEFECT_CLASSIFICATION",
        vision_assessment_expected_threshold="0.8984375",
    )

    assert settings.vision_assessment_expected_threshold == 0.8984375


@pytest.mark.parametrize(
    "values",
    [
        {
            "vision_mock_mode": "success_single_defect",
            "vision_task": "ANY_DEFECT_CLASSIFICATION",
        },
        {
            "vision_mock_mode": "binary_candidate",
            "vision_task": "QUALITY_AND_DEFECT_DETECTION",
            "vision_assessment_expected_threshold": 0.8984375,
        },
    ],
)
def test_mock_vision_mode_and_task_must_describe_the_same_contract(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="VISION_MOCK_MODE and VISION_TASK"):
        Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


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
