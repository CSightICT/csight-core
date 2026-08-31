"""Measure local read-only operator API latency with independent authenticated clients.

This is a baseline collector, not a limited-pilot qualification verdict. It never
creates cases, decisions, actions, or other business records and accepts only a
loopback API URL.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import urllib3

from app.bootstrap.settings import Settings


@dataclass(frozen=True, slots=True)
class EndpointSample:
    endpoint: str
    elapsed_ms: float
    status: int
    contract_valid: bool


def nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _login(
    pool: urllib3.PoolManager,
    *,
    base_url: str,
    tenant_slug: str,
    email: str,
    password: str,
    timeout_seconds: float,
) -> str:
    response = pool.request(
        "POST",
        f"{base_url}/api/v1/auth/token",
        json={"tenant_slug": tenant_slug, "email": email, "password": password},
        timeout=timeout_seconds,
        retries=False,
    )
    if response.status != 200:
        raise RuntimeError(f"local authentication returned HTTP {response.status}")
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("local authentication omitted the access token")
    return token


def _measure_client(
    *,
    pool: urllib3.PoolManager,
    token: str,
    base_url: str,
    requests_per_endpoint: int,
    timeout_seconds: float,
    start: threading.Barrier,
) -> tuple[EndpointSample, ...]:
    start.wait(timeout=timeout_seconds)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    samples: list[EndpointSample] = []
    for _ in range(requests_per_endpoint):
        for endpoint in ("/api/v1/operator/cases", "/api/v1/operator/reviews"):
            started_at = time.perf_counter()
            response = pool.request(
                "GET",
                f"{base_url}{endpoint}",
                headers=headers,
                timeout=timeout_seconds,
                retries=False,
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            contract_valid = False
            if response.status == 200:
                payload = response.json()
                contract_valid = (
                    isinstance(payload, dict)
                    and isinstance(payload.get("items"), list)
                    and isinstance(payload.get("counts"), dict)
                    and "next_cursor" in payload
                )
            samples.append(
                EndpointSample(
                    endpoint=endpoint,
                    elapsed_ms=elapsed_ms,
                    status=response.status,
                    contract_valid=contract_valid,
                )
            )
    return tuple(samples)


def _summary(samples: Sequence[EndpointSample]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for endpoint in ("/api/v1/operator/cases", "/api/v1/operator/reviews"):
        endpoint_samples = [sample for sample in samples if sample.endpoint == endpoint]
        successful = [
            sample.elapsed_ms
            for sample in endpoint_samples
            if sample.status == 200 and sample.contract_valid
        ]
        output[endpoint] = {
            "request_count": len(endpoint_samples),
            "success_count": len(successful),
            "error_count": len(endpoint_samples) - len(successful),
            "p50_ms": round(statistics.median(successful), 3) if successful else None,
            "p95_ms": round(nearest_rank_percentile(successful, 0.95), 3) if successful else None,
            "max_ms": round(max(successful), 3) if successful else None,
        }
    return output


def run(
    *,
    settings: Settings,
    base_url: str,
    concurrent_clients: int,
    requests_per_endpoint: int,
    timeout_seconds: float,
    tenant_slug: str,
    email: str,
) -> dict[str, Any]:
    if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("the benchmark accepts only an explicit loopback API URL")
    if not 1 <= concurrent_clients <= 100:
        raise ValueError("concurrent_clients must be between 1 and 100")
    if not 1 <= requests_per_endpoint <= 100:
        raise ValueError("requests_per_endpoint must be between 1 and 100")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    password = settings.development_seed_reviewer_password
    if password is None:
        raise ValueError("DEVELOPMENT_SEED_REVIEWER_PASSWORD is required")

    pools = [urllib3.PoolManager(num_pools=1, maxsize=2) for _ in range(concurrent_clients)]
    tokens = [
        _login(
            pool,
            base_url=base_url,
            tenant_slug=tenant_slug,
            email=email,
            password=password.get_secret_value(),
            timeout_seconds=timeout_seconds,
        )
        for pool in pools
    ]
    start = threading.Barrier(concurrent_clients)

    def measure(values: tuple[urllib3.PoolManager, str]) -> tuple[EndpointSample, ...]:
        return _measure_client(
            pool=values[0],
            token=values[1],
            base_url=base_url,
            requests_per_endpoint=requests_per_endpoint,
            timeout_seconds=timeout_seconds,
            start=start,
        )

    with ThreadPoolExecutor(max_workers=concurrent_clients) as executor:
        batches = tuple(
            executor.map(
                measure,
                zip(pools, tokens, strict=True),
            )
        )
    samples = tuple(sample for batch in batches for sample in batch)
    endpoints = _summary(samples)
    eligible_read_latency = all(
        result["error_count"] == 0
        and isinstance(result["p95_ms"], float)
        and result["p95_ms"] <= 500
        for result in endpoints.values()
    )
    return {
        "schema_version": "operator_read_baseline/1.0.0",
        "scope": "LOCAL_LEGACY_BEARER_READ_ONLY_BASELINE_NOT_OIDC_OR_PILOT_QUALIFICATION",
        "recorded_at": datetime.now(UTC).isoformat(),
        "concurrent_clients": concurrent_clients,
        "requests_per_endpoint_per_client": requests_per_endpoint,
        "endpoints": endpoints,
        "read_p95_budget_ms": 500,
        "read_latency_budget_met": eligible_read_latency,
        "mutations_performed": 0,
        "business_side_effects_performed": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrent-clients", type=int, default=20)
    parser.add_argument("--requests-per-endpoint", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=10)
    parser.add_argument("--tenant-slug", default="csight-demo")
    parser.add_argument("--email", default="reviewer@csight.demo")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = run(
            settings=Settings(_env_file=arguments.env_file),  # pyright: ignore[reportCallIssue]
            base_url=arguments.base_url.rstrip("/"),
            concurrent_clients=arguments.concurrent_clients,
            requests_per_endpoint=arguments.requests_per_endpoint,
            timeout_seconds=arguments.timeout_seconds,
            tenant_slug=arguments.tenant_slug,
            email=arguments.email,
        )
    except (OSError, ValueError, RuntimeError, urllib3.exceptions.HTTPError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["read_latency_budget_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
