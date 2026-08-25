"""RabbitMQ readiness adapter using Celery's Kombu transport layer."""

from math import ceil

from kombu import Connection


class RabbitMQReadinessProbe:
    name = "rabbitmq"

    def __init__(self, url: str, *, timeout_seconds: float) -> None:
        self._url = url
        self._timeout_seconds = max(1, ceil(timeout_seconds))

    def check(self) -> bool:
        connection = Connection(self._url, connect_timeout=self._timeout_seconds)
        try:
            connection.ensure_connection(max_retries=0, timeout=self._timeout_seconds)
            return bool(connection.connected)
        finally:
            connection.release()
