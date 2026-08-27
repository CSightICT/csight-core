#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_venv="${repo_root}/.venv-local-llm"
runtime_host="${LOCAL_LLM_HOST:-127.0.0.1}"
runtime_port="${LOCAL_LLM_PORT:-8080}"
model_artifact="${LOCAL_LLM_MODEL_ARTIFACT:-mlx-community/Qwen3.5-9B-MLX-4bit}"
model_revision="${LOCAL_LLM_MODEL_REVISION:-938d8919941c6e7efd3c7150eff7fe9d12afa631}"
max_output_tokens="${LOCAL_LLM_MAX_OUTPUT_TOKENS:-512}"
context_tokens="${LOCAL_LLM_CONTEXT_TOKENS:-4096}"
max_sequences="${LOCAL_LLM_MAX_NUM_SEQS:-1}"
pid_file="${repo_root}/infra/local_llm/.server.pid"

if [[ ! -x "${runtime_venv}/bin/python" ]]; then
  echo "Local LLM runtime is missing; run make setup-local-llm first." >&2
  exit 1
fi

model_snapshot="$("${runtime_venv}/bin/hf" download "${model_artifact}" \
  --revision "${model_revision}" --quiet)"
python_pid="$$"
"${runtime_venv}/bin/python" -c \
  'from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.argv[2] + "\n")' \
  "${pid_file}" "${python_pid}"

exec "${runtime_venv}/bin/python" -m mlx_vlm.server \
  --host "${runtime_host}" \
  --port "${runtime_port}" \
  --model "${model_snapshot}" \
  --max-tokens "${max_output_tokens}" \
  --max-kv-size "${context_tokens}" \
  --max-num-seqs "${max_sequences}" \
  --log-progress-interval 0 \
  --log-level INFO
