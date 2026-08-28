#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_venv="${repo_root}/.venv-vision-e3"
runtime_host="${VISION_E3_HOST:-127.0.0.1}"
runtime_port="${VISION_E3_PORT:-8093}"
checkpoint_path="${VISION_E3_CHECKPOINT_PATH:-}"
pid_file="${repo_root}/infra/vision_e3/.server.pid"

if [[ ! -x "${runtime_venv}/bin/python" ]]; then
  echo "E3 Vision runtime is missing; run make setup-vision-e3 first." >&2
  exit 1
fi
if [[ "${runtime_host}" != "127.0.0.1" && "${runtime_host}" != "::1" && "${runtime_host}" != "localhost" ]]; then
  echo "VISION_E3_HOST must remain loopback-only." >&2
  exit 1
fi
if [[ -z "${checkpoint_path}" ]]; then
  echo "VISION_E3_CHECKPOINT_PATH must point to E3_best_epoch10.pt outside Git." >&2
  exit 1
fi
if [[ ! -f "${checkpoint_path}" ]]; then
  echo "VISION_E3_CHECKPOINT_PATH is not a regular file." >&2
  exit 1
fi

python_pid="$$"
"${runtime_venv}/bin/python" -c \
  'from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.argv[2] + "\n", encoding="utf-8")' \
  "${pid_file}" "${python_pid}"

export PYTHONPATH="${repo_root}"
export VISION_E3_CHECKPOINT_PATH="${checkpoint_path}"
exec "${runtime_venv}/bin/python" -m uvicorn infra.vision_e3.app:app \
  --host "${runtime_host}" \
  --port "${runtime_port}" \
  --workers 1 \
  --no-access-log \
  --log-level info
