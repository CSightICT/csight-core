"""Fail closed before integration fixtures can mutate a shared demo database."""

import re

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def require_disposable_database(database_url: str | None, authorized_name: str | None) -> None:
    """Require the official runner's exact randomly named disposable database."""
    message = "Use scripts/run_integration_tests.py; shared databases are not test targets."
    if not authorized_name or not re.fullmatch(r"csight_integration_[0-9a-f]{16}", authorized_name):
        raise ValueError(message)
    try:
        url = make_url(database_url or "")
    except (ArgumentError, TypeError, ValueError):
        raise ValueError(message) from None
    if not url.drivername.startswith("postgresql") or url.database != authorized_name:
        raise ValueError(message)
