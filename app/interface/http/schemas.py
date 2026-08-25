"""Public Sprint 0 HTTP response contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ports.readiness import ProbeStatus


class HTTPContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LiveResponse(HTTPContract):
    status: Literal["ok"] = "ok"
    service: str


class ReadyResponse(HTTPContract):
    status: Literal["ok", "unavailable"]
    service: str
    dependencies: dict[str, ProbeStatus]


class SystemInfoResponse(HTTPContract):
    service: str
    version: str
    environment: str
    api_schema_version: str


class ErrorDetail(HTTPContract):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    correlation_id: str | None = None


class ErrorResponse(HTTPContract):
    error: ErrorDetail
