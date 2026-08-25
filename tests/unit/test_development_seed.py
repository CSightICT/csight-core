"""Unit tests for explicit development seed safeguards."""

import pytest
from pydantic import SecretStr

from app.bootstrap.seed import SeedConfigurationError, development_seed_passwords
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.unit


def _settings(*, environment: str = "local", enabled: bool = True) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment=environment,
        database_url=SecretStr("postgresql+psycopg://seed:masked@localhost/csight"),
        development_seed_enabled=enabled,
        development_seed_admin_password=SecretStr("a" * 16),
        development_seed_reviewer_password=SecretStr("r" * 16),
        development_seed_quality_viewer_password=SecretStr("q" * 16),
    )


@pytest.mark.parametrize("environment", ["production", "staging", "preview"])
def test_seed_is_refused_outside_local_and_test(environment: str) -> None:
    with pytest.raises(SeedConfigurationError, match="local or test"):
        development_seed_passwords(_settings(environment=environment))


def test_seed_requires_an_explicit_enable_flag() -> None:
    with pytest.raises(SeedConfigurationError, match="DEVELOPMENT_SEED_ENABLED"):
        development_seed_passwords(_settings(enabled=False))


def test_seed_requires_database_and_all_password_environment_values() -> None:
    missing_database = _settings().model_copy(update={"database_url": None})
    with pytest.raises(SeedConfigurationError, match="DATABASE_URL"):
        development_seed_passwords(missing_database)

    missing_password = _settings().model_copy(update={"development_seed_reviewer_password": None})
    with pytest.raises(SeedConfigurationError, match="REVIEWER_PASSWORD"):
        development_seed_passwords(missing_password)

    weak_password = _settings().model_copy(
        update={"development_seed_admin_password": SecretStr("short")}
    )
    with pytest.raises(SeedConfigurationError, match="12 characters"):
        development_seed_passwords(weak_password)


@pytest.mark.parametrize("environment", ["local", "test", " LOCAL "])
def test_allowed_seed_password_bundle_never_renders_plaintext(environment: str) -> None:
    passwords = development_seed_passwords(_settings(environment=environment))

    rendered = repr(passwords)
    assert "a" * 16 not in rendered
    assert "r" * 16 not in rendered
    assert "q" * 16 not in rendered
