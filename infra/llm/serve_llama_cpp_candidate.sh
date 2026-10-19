#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../.." && pwd)"
candidate_id="${1:-}"
runtime_env="${2:-}"
service_name="qwen38-llama-cpp"

file_identity() {
  local path="$1" metadata
  if metadata="$(stat -c '%u:%a' "${path}" 2>/dev/null)"; then
    printf '%s\n' "${metadata}"
    return 0
  fi
  stat -f '%u:%Lp' "${path}" 2>/dev/null
}

case "${candidate_id}" in
  qwen38-27b-csight-q4-k-m-llama-cpp|qwen38-27b-csight-q5-k-s-llama-cpp) ;;
  *) echo "candidate is not allowlisted by matrix v2" >&2; exit 2 ;;
esac
if [[ -z "${runtime_env}" || "${runtime_env}" != /* || ! -f "${runtime_env}" || -L "${runtime_env}" ]]; then
  echo "second argument must be an absolute private regular environment file" >&2
  exit 2
fi
runtime_env_stat="$(file_identity "${runtime_env}")"
if [[ "${runtime_env_stat}" != "$(id -u):600" ]]; then
  echo "runtime environment file must be caller-owned with mode 600" >&2
  exit 2
fi

docker_bin="$(command -v docker)"
if [[ -z "${docker_bin}" || "${docker_bin}" != /* ]]; then
  echo "an absolute Docker CLI path is required" >&2
  exit 2
fi

umask 077
rendered_compose="$(mktemp "${TMPDIR:-/tmp}/csight-llama-cpp-compose.XXXXXX.json")"
container_inspect="$(mktemp "${TMPDIR:-/tmp}/csight-llama-cpp-inspect.XXXXXX.json")"
compose_source=(
  env -i PATH="${PATH}" "${docker_bin}" compose
  --env-file "${runtime_env}" -f "${script_dir}/compose.llama-cpp.yml"
)
compose_runtime=(env -i PATH="${PATH}" "${docker_bin}" compose -f "${rendered_compose}")
container_started=0

cleanup() {
  local status="$?"
  trap - EXIT HUP INT TERM
  if (( status != 0 && container_started == 1 )); then
    "${compose_runtime[@]}" down >/dev/null 2>&1 || true
  fi
  rm -f -- "${rendered_compose}" "${container_inspect}"
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

"${compose_source[@]}" config --format json >"${rendered_compose}"
chmod 600 "${rendered_compose}" "${container_inspect}"

preflight=(
  "${repo_root}/.venv/bin/python" "${repo_root}/scripts/preflight_qwen4090_gguf_host.py"
  --candidate-id "${candidate_id}"
  --runtime-env "${runtime_env}"
  --compose-config "${rendered_compose}"
)

if [[ "${DRY_RUN:-}" == "1" ]]; then
  "${preflight[@]}" --config-only
  echo "LLAMA_CPP_SHADOW_CONFIG_VALID candidate=${candidate_id}"
  exit 0
fi
if [[ "${ALLOW_LLAMA_CPP_SERVE:-}" != "YES" ]]; then
  echo "set ALLOW_LLAMA_CPP_SERVE=YES only after GGUF host preflight passes" >&2
  exit 2
fi

"${preflight[@]}"
container_started=1
"${compose_runtime[@]}" up --detach --wait "${service_name}"
container_id="$("${compose_runtime[@]}" ps --quiet "${service_name}")"
if [[ ! "${container_id}" =~ ^[0-9a-f]{12,64}$ ]]; then
  echo "the exact llama.cpp service container could not be identified" >&2
  exit 2
fi
"${docker_bin}" inspect "${container_id}" >"${container_inspect}"
"${preflight[@]}" --post-start-container-inspect "${container_inspect}"
echo "LLAMA_CPP_SHADOW_STARTED candidate=${candidate_id}"
