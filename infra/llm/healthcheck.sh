#!/usr/bin/env bash
set -euo pipefail

: "${LLM_BASE_URL:?Set the private vLLM base URL, including /v1}"
: "${LLM_API_KEY:?Set the vLLM API key}"

models_json="$(curl --fail --silent --show-error \
  --connect-timeout 5 \
  --max-time 30 \
  -H "Authorization: Bearer ${LLM_API_KEY}" \
  "${LLM_BASE_URL%/}/models")"

MODELS_JSON="${models_json}" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["MODELS_JSON"])
model_ids = {item.get("id") for item in payload.get("data", [])}
expected = "csight-qwen3.8-27b"
if expected not in model_ids:
    raise SystemExit(f"served model mismatch: expected {expected}")
print(f"healthy: {expected}")
PY
