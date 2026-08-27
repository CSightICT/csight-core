#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_python="${LOCAL_LLM_PYTHON:-3.12}"
runtime_venv="${repo_root}/.venv-local-llm"

uv venv "${runtime_venv}" --python "${runtime_python}"
uv pip install --python "${runtime_venv}/bin/python" \
  -r "${repo_root}/infra/local_llm/requirements.lock.txt"
"${runtime_venv}/bin/python" -c \
  'import importlib.metadata as m; print("mlx=" + m.version("mlx")); print("mlx-vlm=" + m.version("mlx-vlm"))'
