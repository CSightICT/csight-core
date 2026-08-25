"""Message-broker adapters."""

from app.adapters.messaging.readiness import RabbitMQReadinessProbe

__all__ = ["RabbitMQReadinessProbe"]
