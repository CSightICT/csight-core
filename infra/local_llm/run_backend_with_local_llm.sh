#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_venv="${repo_root}/.venv-local-llm"
model_artifact="${LOCAL_LLM_MODEL_ARTIFACT:-mlx-community/Qwen3.5-9B-MLX-4bit}"
model_revision="${LOCAL_LLM_MODEL_REVISION:-938d8919941c6e7efd3c7150eff7fe9d12afa631}"
model_snapshot="$("${runtime_venv}/bin/hf" download "${model_artifact}" \
  --revision "${model_revision}" --quiet)"
runtime_version="$("${runtime_venv}/bin/python" -c \
  'import importlib.metadata as m; print(m.version("mlx"))')"
server_runtime_version="$("${runtime_venv}/bin/python" -c \
  'import importlib.metadata as m; print(m.version("mlx-vlm"))')"

export LLM_PROVIDER=mlx
export LLM_BASE_URL="${LOCAL_LLM_BACKEND_BASE_URL:-http://127.0.0.1:8080/v1}"
export LLM_MODEL_ID="${model_snapshot}"
export LLM_MODEL_VERSION="Qwen3.5-9B-MLX-4bit"
export LLM_MODEL_REVISION="${model_revision}"
export LLM_CONNECT_TIMEOUT_SECONDS="${LLM_CONNECT_TIMEOUT_SECONDS:-10}"
export LLM_READ_TIMEOUT_SECONDS="${LLM_READ_TIMEOUT_SECONDS:-180}"
export LLM_MAX_OUTPUT_TOKENS="${LLM_MAX_OUTPUT_TOKENS:-512}"
export LLM_TEMPERATURE=0
export LLM_TLS_VERIFY=false
export EMBEDDING_BASE_URL="${EMBEDDING_BASE_URL:-http://127.0.0.1:8091}"
export LOCAL_LLM_MODEL_ARTIFACT="${model_artifact}"
export LOCAL_LLM_MODEL_REVISION="${model_revision}"
export LOCAL_LLM_RUNTIME_VERSION="${runtime_version}"
export LOCAL_LLM_SERVER_RUNTIME_VERSION="${server_runtime_version}"

exec "$@"
