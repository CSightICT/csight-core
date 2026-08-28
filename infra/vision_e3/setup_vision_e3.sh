#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_python="${VISION_E3_PYTHON:-3.12}"
runtime_venv="${repo_root}/.venv-vision-e3"

uv venv "${runtime_venv}" --python "${runtime_python}" --allow-existing
uv pip install --python "${runtime_venv}/bin/python" \
  -r "${repo_root}/infra/vision_e3/requirements.lock.txt"
"${runtime_venv}/bin/python" -c \
  'import importlib.metadata as m; print("torch=" + m.version("torch")); print("transformers=" + m.version("transformers"))'
