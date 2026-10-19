"""Shared protection against accidentally running integration fixtures on demo data."""

import os

import pytest

from app.bootstrap.settings import Settings
from scripts.integration_database_safety import require_disposable_database


def pytest_collection_finish(session: pytest.Session) -> None:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        return
    if not any(item.get_closest_marker("integration") for item in session.items):
        return
    try:
        require_disposable_database(
            Settings().database_url_value, os.getenv("CSIGHT_DISPOSABLE_TEST_DATABASE")
        )
    except ValueError:
        raise pytest.UsageError(
            "Integration fixtures may not use the shared database. "
            "Run scripts/run_integration_tests.py instead."
        ) from None
