"""Run non-persistent health, completion, and constrained-JSON probes."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, cast


def _get(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return cast(dict[str, Any], json.load(response))


def _post(url: str, payload: dict[str, object]) -> tuple[dict[str, Any], float]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        body = cast(dict[str, Any], json.load(response))
    return body, time.perf_counter() - started


def main() -> int:
    host = os.getenv("LOCAL_LLM_HOST", "127.0.0.1")
    port = os.getenv("LOCAL_LLM_PORT", "8080")
    base_url = f"http://{host}:{port}"
    health = _get(f"{base_url}/health")
    model = str(health["loaded_model"])
    if not model:
        raise SystemExit("Local MLX health response has no loaded model")
    models = _get(f"{base_url}/v1/models")
    model_ids = {str(item["id"]) for item in models["data"]}
    if model not in model_ids:
        raise SystemExit("Loaded Local MLX model is absent from /v1/models")

    common: dict[str, object] = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": 128,
        "enable_thinking": False,
        "stream": False,
    }
    basic, basic_latency = _post(
        f"{base_url}/v1/chat/completions",
        {
            **common,
            "messages": [
                {"role": "system", "content": "Return only the requested marker."},
                {"role": "user", "content": "Return CSIGHT_LOCAL_MLX_OK"},
            ],
        },
    )
    content = str(basic["choices"][0]["message"]["content"])
    if "CSIGHT_LOCAL_MLX_OK" not in content:
        raise SystemExit("Basic Local MLX completion did not return its marker")

    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ok"]},
            "citations": {
                "type": "array",
                "items": {"type": "string", "enum": ["CIT-001"]},
                "minItems": 1,
                "maxItems": 1,
            },
        },
        "required": ["status", "citations"],
        "additionalProperties": False,
    }
    structured, structured_latency = _post(
        f"{base_url}/v1/chat/completions",
        {
            **common,
            "messages": [
                {"role": "system", "content": "Return only constrained JSON; no reasoning."},
                {"role": "user", "content": "Set status ok and cite CIT-001."},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "csight_probe", "strict": True, "schema": schema},
            },
        },
    )
    message = structured["choices"][0]["message"]
    parsed = json.loads(str(message["content"]))
    if parsed != {"status": "ok", "citations": ["CIT-001"]}:
        raise SystemExit("Structured Local MLX response failed its exact assertion")
    if message.get("reasoning_content") is not None or message.get("reasoning") is not None:
        raise SystemExit("Local MLX returned reasoning while thinking was disabled")
    print(
        json.dumps(
            {
                "qualification": "LOCAL_MLX_BASE_CONTRACT_PASS",
                "loaded_model": model,
                "configured_context_limit": health.get("configured_context_limit"),
                "basic_latency_seconds": round(basic_latency, 3),
                "structured_latency_seconds": round(structured_latency, 3),
                "reasoning_leakage": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
