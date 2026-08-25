"""Minimal asynchronous message publishing boundary."""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class MessageQueue(Protocol):
    def publish(
        self,
        *,
        topic: str,
        payload: Mapping[str, object],
        correlation_id: str,
    ) -> str:
        """Publish a reference-only payload and return its message identifier."""
        ...

    def is_ready(self) -> bool: ...
