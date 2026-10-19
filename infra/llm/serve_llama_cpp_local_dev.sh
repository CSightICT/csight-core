#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../.." && pwd)"
candidate_id="${1:-}"
runtime_env="${2:-}"
project_name="csight-qwen38-local-dev"
service_name="qwen38-llama-cpp"
python_bin="${CSIGHT_LOCAL_DEV_PYTHON_BIN:-${repo_root}/.venv/bin/python}"
post_start_evidence="${CSIGHT_LOCAL_DEV_POST_START_EVIDENCE:-}"

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
  *) echo "candidate is not allowlisted for DEV_LOCAL" >&2; exit 2 ;;
esac
if [[ -z "${runtime_env}" || "${runtime_env}" != /* || ! -f "${runtime_env}" \
  || -L "${runtime_env}" ]]; then
  echo "second argument must be an absolute private regular environment file" >&2
  exit 2
fi
if [[ "${python_bin}" != /* || ! -f "${python_bin}" || ! -x "${python_bin}" ]]; then
  echo "CSIGHT_LOCAL_DEV_PYTHON_BIN must be an absolute executable regular file" >&2
  exit 2
fi
python_identity="$(file_identity "${python_bin}")"
python_uid="${python_identity%%:*}"
python_mode="${python_identity##*:}"
if [[ ! "${python_uid}" =~ ^[0-9]+$ || ! "${python_mode}" =~ ^[0-7]{3,4}$ \
  || ( "${python_uid}" != "0" && "${python_uid}" != "$(id -u)" ) \
  || $(( 8#${python_mode} & 8#022 )) -ne 0 ]]; then
  echo "CSIGHT_LOCAL_DEV_PYTHON_BIN must be root/caller owned and not group/world writable" >&2
  exit 2
fi
runtime_env_stat="$(file_identity "${runtime_env}")"
if [[ "${runtime_env_stat}" != "$(id -u):600" ]]; then
  echo "runtime environment file must be caller-owned with mode 600" >&2
  exit 2
fi

process_start_ticks() {
  local pid="$1" stat_line remainder
  [[ "${pid}" =~ ^[1-9][0-9]*$ && -r "/proc/${pid}/stat" ]] || return 1
  IFS= read -r stat_line <"/proc/${pid}/stat" || return 1
  remainder="${stat_line##*) }"
  awk '{print $20}' <<<"${remainder}"
}

require_live_restore_guard() {
  local guard="${CSIGHT_LOCAL_DEV_RESTORE_GUARD:-}"
  local key value observed_ticks
  local guard_candidate="" owner_pid="" owner_ticks="" watchdog_pid="" watchdog_ticks=""
  local -A seen=()
  if [[ -z "${guard}" || "${guard}" != /* || ! -f "${guard}" || -L "${guard}" ]]; then
    echo "a protected maintenance restore guard is required for DEV_LOCAL start" >&2
    return 1
  fi
  if [[ "$(stat -c '%u:%a' "${guard}")" != "$(id -u):600" ]]; then
    echo "restore guard must be caller-owned with mode 600" >&2
    return 1
  fi
  while IFS='=' read -r key value; do
    [[ -n "${key}" && -n "${value}" && -z "${seen[${key}]:-}" ]] || return 1
    seen["${key}"]=1
    case "${key}" in
      schema_version)
        [[ "${value}" == "csight_local_dev_restore_guard/1.0.0" ]] || return 1
        ;;
      candidate_id) guard_candidate="${value}" ;;
      owner_pid) owner_pid="${value}" ;;
      owner_start_ticks) owner_ticks="${value}" ;;
      watchdog_pid) watchdog_pid="${value}" ;;
      watchdog_start_ticks) watchdog_ticks="${value}" ;;
      *) return 1 ;;
    esac
  done <"${guard}"
  [[ "${#seen[@]}" -eq 6 && "${guard_candidate}" == "${candidate_id}" ]] || return 1
  [[ "${owner_pid}" == "${PPID}" ]] || return 1
  observed_ticks="$(process_start_ticks "${owner_pid}")" || return 1
  [[ "${observed_ticks}" == "${owner_ticks}" ]] || return 1
  observed_ticks="$(process_start_ticks "${watchdog_pid}")" || return 1
  [[ "${observed_ticks}" == "${watchdog_ticks}" ]] || return 1
}

docker_bin="$(command -v docker)"
if [[ -z "${docker_bin}" || "${docker_bin}" != /* ]]; then
  echo "an absolute Docker CLI path is required" >&2
  exit 2
fi
timeout_bin="$(command -v timeout)"
if [[ -z "${timeout_bin}" || "${timeout_bin}" != /* ]]; then
  echo "an absolute timeout command is required for bounded failure evidence" >&2
  exit 2
fi

rendered_compose="$(mktemp "${TMPDIR:-/tmp}/csight-local-dev-compose.XXXXXX.json")"
container_inspect="$(mktemp "${TMPDIR:-/tmp}/csight-local-dev-inspect.XXXXXX.json")"
compose_source=(
  env -i PATH="${PATH}" "${docker_bin}" compose
  --project-name "${project_name}"
  --env-file "${runtime_env}"
  -f "${script_dir}/compose.llama-cpp-local-dev.yml"
)
compose_runtime=(
  env -i PATH="${PATH}" "${docker_bin}" compose
  --project-name "${project_name}"
  -f "${rendered_compose}"
)
container_started=0
post_start_temporary=""
post_start_failure=""
startup_log=""

capture_startup_log() {
  [[ -n "${startup_log}" && ! -e "${startup_log}" && ! -L "${startup_log}" ]] || return 0
  "${timeout_bin}" --signal=KILL 10s \
    "${compose_runtime[@]}" logs --no-color --timestamps --tail 1000 "${service_name}" \
    >"${startup_log}" 2>&1 || true
  chmod 600 "${startup_log}" || true
}

cleanup() {
  local status="$?"
  trap - EXIT HUP INT TERM
  set +e
  if (( status != 0 && container_started == 1 )); then
    capture_startup_log
    "${compose_runtime[@]}" down --remove-orphans >/dev/null 2>&1 || true
  fi
  rm -f -- "${rendered_compose}" "${container_inspect}"
  if [[ -n "${post_start_temporary}" ]]; then
    rm -f -- "${post_start_temporary}"
  fi
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

"${compose_source[@]}" config --format json >"${rendered_compose}"
chmod 600 "${rendered_compose}" "${container_inspect}"
preflight=(
  "${python_bin}"
  "${repo_root}/scripts/preflight_qwen4090_local_gguf_dev.py"
  --candidate-id "${candidate_id}"
  --runtime-env "${runtime_env}"
  --compose-config "${rendered_compose}"
)

if [[ "${DRY_RUN:-}" == "1" ]]; then
  "${preflight[@]}" --config-only
  echo "LLAMA_CPP_DEV_LOCAL_CONFIG_VALID candidate=${candidate_id}"
  exit 0
fi
if [[ "${ALLOW_LLAMA_CPP_LOCAL_DEV:-}" != "YES" ]]; then
  echo "set ALLOW_LLAMA_CPP_LOCAL_DEV=YES only inside a protected maintenance window" >&2
  exit 2
fi
if ! require_live_restore_guard; then
  echo "DEV_LOCAL start refused because the independent restoration guard is invalid" >&2
  exit 2
fi
if [[ "${post_start_evidence}" != /* || -L "${post_start_evidence}" \
  || -e "${post_start_evidence}" ]]; then
  echo "CSIGHT_LOCAL_DEV_POST_START_EVIDENCE must be a fresh absolute path" >&2
  exit 2
fi
post_start_parent="$(dirname -- "${post_start_evidence}")"
post_start_parent_identity="$(file_identity "${post_start_parent}")"
if [[ ! -d "${post_start_parent}" || -L "${post_start_parent}" \
  || "${post_start_parent_identity}" != "$(id -u):700" ]]; then
  echo "post-start evidence parent must be caller-owned mode 700" >&2
  exit 2
fi
startup_log="${post_start_parent}/local-dev-startup.log"
post_start_failure="${post_start_parent}/local-dev-post-start-failure.json"
if [[ -e "${startup_log}" || -L "${startup_log}" \
  || -e "${post_start_failure}" || -L "${post_start_failure}" ]]; then
  echo "local Dev failure evidence paths must be fresh" >&2
  exit 2
fi

"${preflight[@]}"
container_started=1
if ! "${compose_runtime[@]}" up --detach --wait "${service_name}"; then
  echo "DEV_LOCAL llama.cpp startup failed; private log=${startup_log}" >&2
  exit 1
fi
container_id="$("${compose_runtime[@]}" ps --quiet "${service_name}")"
if [[ ! "${container_id}" =~ ^[0-9a-f]{12,64}$ ]]; then
  echo "the exact DEV_LOCAL llama.cpp container could not be identified" >&2
  exit 2
fi
"${docker_bin}" inspect "${container_id}" >"${container_inspect}"
post_start_temporary="$(mktemp "${post_start_parent}/.post-start.XXXXXX")"
if ! "${preflight[@]}" --post-start-container-inspect "${container_inspect}" \
  >"${post_start_temporary}"; then
  chmod 600 "${post_start_temporary}"
  ln "${post_start_temporary}" "${post_start_failure}"
  echo "DEV_LOCAL post-start validation failed; private report=${post_start_failure}" >&2
  exit 2
fi
chmod 600 "${post_start_temporary}"
ln "${post_start_temporary}" "${post_start_evidence}"
rm -f -- "${post_start_temporary}"
post_start_temporary=""
if command -v sha256sum >/dev/null 2>&1; then
  post_start_digest="sha256:$(sha256sum "${post_start_evidence}" | awk '{print $1}')"
else
  post_start_digest="sha256:$(shasum -a 256 "${post_start_evidence}" | awk '{print $1}')"
fi
echo "LLAMA_CPP_DEV_LOCAL_STARTED candidate=${candidate_id} project=${project_name} post_start_evidence=${post_start_evidence} post_start_digest=${post_start_digest}"
