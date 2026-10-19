"""No database/network access is needed to reject unsafe integration targets."""

import pytest

from scripts.integration_database_safety import require_disposable_database

pytestmark = pytest.mark.unit
NAME = "csight_integration_0123456789abcdef"


@pytest.mark.parametrize(
    "database", ["csight", "postgres", "csight-pilot", "csight_integration_bad"]
)
def test_shared_and_unapproved_databases_are_rejected(database: str) -> None:
    with pytest.raises(ValueError, match="shared databases"):
        require_disposable_database(f"postgresql://localhost/{database}", NAME)


@pytest.mark.parametrize("capability", [None, "", "csight", "csight_integration_ffffffffffffffff"])
def test_exact_runner_capability_is_required(capability: str | None) -> None:
    with pytest.raises(ValueError):
        require_disposable_database(f"postgresql://localhost/{NAME}", capability)


def test_disposable_postgresql_is_accepted() -> None:
    require_disposable_database(f"postgresql+psycopg://localhost/{NAME}", NAME)


@pytest.mark.parametrize("url", [None, "invalid", "sqlite:///csight", "mysql://localhost/" + NAME])
def test_invalid_urls_are_rejected_without_credentials(url: str | None) -> None:
    with pytest.raises(ValueError):
        require_disposable_database(url, NAME)
