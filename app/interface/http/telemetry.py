"""HTTP tracing and metrics at the FastAPI adapter boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter

from fastapi import FastAPI, Request
from starlette.responses import Response

from app.adapters.telemetry import TelemetryRuntime


async def _http_telemetry_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    runtime = _runtime(request)
    method = request.method
    correlation_id = _correlation_id(request)
    carrier = {
        name: value
        for name in ("traceparent", "tracestate")
        if (value := request.headers.get(name)) is not None
    }
    status_code = 500
    route = "unmatched"
    started_at = perf_counter()
    runtime.start_http_request(method=method)
    with runtime.start_http_span(
        method=method,
        carrier=carrier,
        correlation_id=correlation_id,
    ) as span:
        try:
            response = await call_next(request)
        except Exception as error:
            route = _route_template(request)
            runtime.finish_http_span(
                span,
                route=route,
                status_code=status_code,
                error_type=type(error).__name__,
            )
            raise
        else:
            status_code = response.status_code
            route = _route_template(request)
            runtime.finish_http_span(
                span,
                route=route,
                status_code=status_code,
            )
            return response
        finally:
            runtime.finish_http_request(
                method=method,
                route=route,
                status_code=status_code,
                duration_ms=(perf_counter() - started_at) * 1000,
            )


def register_http_telemetry_middleware(
    app: FastAPI,
    *,
    runtime: TelemetryRuntime,
) -> None:
    """Install before correlation middleware so correlation remains outermost."""

    if runtime.enabled:
        app.middleware("http")(_http_telemetry_middleware)


def _runtime(request: Request) -> TelemetryRuntime:
    value = getattr(request.app.state, "telemetry_runtime", None)
    if not isinstance(value, TelemetryRuntime):
        raise RuntimeError("telemetry runtime is unavailable")
    return value


def _correlation_id(request: Request) -> str | None:
    value = getattr(request.state, "correlation_id", None)
    return value if isinstance(value, str) else None


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


__all__ = ["register_http_telemetry_middleware"]
