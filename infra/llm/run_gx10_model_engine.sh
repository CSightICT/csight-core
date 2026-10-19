#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$#" -lt 1 || "$#" -gt 2 ]]; then
  echo "usage: run_gx10_model_engine.sh PHASE [RUN_ID]" >&2
  exit 2
fi

phase="$1"
run_id="${2:-}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
remote_runner="${script_dir}/gx10_remote_model_engine.sh"
ssh_target="${CSIGHT_GX10_SSH_TARGET:-aidi_lab@gx10-ade1}"
gx10_root="${CSIGHT_GX10_ROOT:-/home/aidi_lab/csight-gx10}"
compose_file="${CSIGHT_GX10_COMPOSE_FILE:-${gx10_root}/control/infra/llm/compose.llama-cpp-gx10.yml}"
runtime_env="${CSIGHT_GX10_RUNTIME_ENV:-${gx10_root}/runtime/gx10-q5.env}"
benchmark_script="${CSIGHT_GX10_BENCHMARK_SCRIPT:-${gx10_root}/control/scripts/benchmark_gx10_llama_cpp.py}"

case "${phase}" in
  status|report) mutation_gate="NO" ;;
  prepare|serve|canary|evaluate|stop)
    if [[ "${ALLOW_GX10_MUTATION:-}" != "YES" ]]; then
      echo "phase ${phase} requires ALLOW_GX10_MUTATION=YES after explicit approval" >&2
      exit 2
    fi
    mutation_gate="YES"
    ;;
  *) echo "unsupported GX10 phase" >&2; exit 2 ;;
esac

if [[ ! -f "${remote_runner}" || -L "${remote_runner}" ]]; then
  echo "reviewed GX10 remote runner is missing or unsafe" >&2
  exit 2
fi
if [[ "${phase}" != "status" && ! "${run_id}" =~ ^[0-9]{8}T[0-9]{6}[A-Z0-9_-]{0,32}$ ]]; then
  echo "non-status phases require a bounded append-only RUN_ID" >&2
  exit 2
fi

ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no \
  -o ConnectTimeout=10 "${ssh_target}" \
  "ALLOW_GX10_MUTATION=${mutation_gate} GX10_ROOT='${gx10_root}' GX10_RUN_ID='${run_id}' GX10_COMPOSE_FILE='${compose_file}' GX10_RUNTIME_ENV='${runtime_env}' GX10_BENCHMARK_SCRIPT='${benchmark_script}' bash -s -- '${phase}'" \
  <"${remote_runner}"
