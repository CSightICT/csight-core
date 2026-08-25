"""Standard-library implementations of application runtime ports."""

from datetime import UTC, datetime
from uuid import uuid4


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class Uuid4Generator:
    def new_id(self) -> str:
        return str(uuid4())
