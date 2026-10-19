#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  echo "usage: $0 monitor|restore-now STATE_DIR" >&2
  exit 2
}

[[ "$#" -eq 2 ]] || usage
mode="$1"
state_dir="$2"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose_file="${script_dir}/compose.llama-cpp-local-dev.yml"
project_name="csight-qwen38-local-dev"

if [[ "${state_dir}" != /* || ! -d "${state_dir}" || -L "${state_dir}" \
  || "$(stat -c '%u:%a' "${state_dir}")" != "$(id -u):700" ]]; then
  echo "watchdog state directory must be caller-owned mode 700" >&2
  exit 2
fi

snapshot_file="${state_dir}/vlm.tsv"
runtime_env_file="${state_dir}/candidate-runtime-env.path"
owner_pid_file="${state_dir}/owner.pid"
owner_ticks_file="${state_dir}/owner.start_ticks"
complete_file="${state_dir}/restore.complete"
event_file="${state_dir}/restore-events.tsv"
restore_lock_file="${state_dir}/restore.lock"

for command in docker flock; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "required watchdog command is unavailable: ${command}" >&2
    exit 2
  }
done

private_regular_file() {
  local path="$1"
  [[ -f "${path}" && ! -L "${path}" ]] \
    && [[ "$(stat -c '%u:%a' "${path}")" == "$(id -u):600" ]]
}

process_start_ticks() {
  local pid="$1" stat_line remainder
  [[ "${pid}" =~ ^[1-9][0-9]*$ && -r "/proc/${pid}/stat" ]] || return 1
  IFS= read -r stat_line <"/proc/${pid}/stat" || return 1
  remainder="${stat_line##*) }"
  awk '{print $20}' <<<"${remainder}"
}

process_matches() {
  local pid="$1" expected_ticks="$2" observed_ticks
  observed_ticks="$(process_start_ticks "${pid}")" || return 1
  [[ "${observed_ticks}" == "${expected_ticks}" ]]
}

append_event() {
  printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" \
    >>"${event_file}"
  chmod 600 "${event_file}"
}

load_snapshot() {
  private_regular_file "${snapshot_file}" || return 1
  IFS=$'\t' read -r \
    vlm_id vlm_name expected_image_id expected_image_ref expected_config_hash \
    expected_restart_count expected_oom expected_model_id <"${snapshot_file}"
  [[ "${vlm_id}" =~ ^[0-9a-f]{64}$ \
    && "${vlm_name}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ \
    && "${expected_image_id}" =~ ^sha256:[0-9a-f]{64}$ \
    && "${expected_image_ref}" =~ ^[a-zA-Z0-9._/@:+-]+$ \
    && "${expected_config_hash}" =~ ^[0-9a-f]{64}$ \
    && "${expected_restart_count}" =~ ^[0-9]+$ \
    && "${expected_oom}" == "false" \
    && "${expected_model_id}" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/+:-]*$ ]]
}

load_runtime_env() {
  private_regular_file "${runtime_env_file}" || return 1
  IFS= read -r candidate_runtime_env <"${runtime_env_file}"
  [[ "${candidate_runtime_env}" == /* && -f "${candidate_runtime_env}" \
    && ! -L "${candidate_runtime_env}" \
    && "$(stat -c '%u:%a' "${candidate_runtime_env}")" == "$(id -u):600" ]]
}

candidate_down() {
  load_runtime_env || return 1
  docker compose \
    --project-name "${project_name}" \
    --env-file "${candidate_runtime_env}" \
    -f "${compose_file}" \
    down --remove-orphans >/dev/null 2>&1 || return 1
  [[ -z "$(docker ps --all --quiet \
    --filter "label=com.docker.compose.project=${project_name}")" ]]
}

validate_exact_vlm() {
  local observed_id observed_image_id observed_image_ref observed_config_hash
  local observed_running observed_restart_count observed_oom observed_health
  observed_id="$(docker inspect --format '{{.Id}}' "${vlm_name}" 2>/dev/null || true)"
  observed_image_id="$(docker inspect --format '{{.Image}}' "${vlm_name}" 2>/dev/null || true)"
  observed_image_ref="$(docker inspect --format '{{.Config.Image}}' "${vlm_name}" 2>/dev/null || true)"
  observed_config_hash="$(docker inspect --format \
    '{{index .Config.Labels "com.docker.compose.config-hash"}}' "${vlm_name}" 2>/dev/null || true)"
  observed_running="$(docker inspect --format '{{.State.Running}}' "${vlm_name}" 2>/dev/null || true)"
  observed_restart_count="$(docker inspect --format '{{.RestartCount}}' "${vlm_name}" 2>/dev/null || true)"
  observed_oom="$(docker inspect --format '{{.State.OOMKilled}}' "${vlm_name}" 2>/dev/null || true)"
  observed_health="$(docker inspect --format \
    '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "${vlm_name}" 2>/dev/null || true)"
  [[ "${observed_id}" == "${vlm_id}" \
    && "${observed_image_id}" == "${expected_image_id}" \
    && "${observed_image_ref}" == "${expected_image_ref}" \
    && "${observed_config_hash}" == "${expected_config_hash}" \
    && "${observed_running}" == "true" \
    && "${observed_restart_count}" == "${expected_restart_count}" \
    && "${observed_oom}" == "false" \
    && "${observed_health}" == "healthy" ]]
}

authenticated_vlm_canary() {
  docker exec -e CSIGHT_EXPECTED_MODEL_ID="${expected_model_id}" "${vlm_id}" \
    python3 -c '
import json
import os
import urllib.request

key = os.environ.get("VLLM_API_KEY", "")
expected = os.environ["CSIGHT_EXPECTED_MODEL_ID"]
if len(key) < 16:
    raise SystemExit(2)
request = urllib.request.Request(
    "http://127.0.0.1:8000/v1/models",
    headers={"Authorization": f"Bearer {key}"},
)
with urllib.request.urlopen(request, timeout=10) as response:
    content = response.read(1024 * 1024 + 1)
if len(content) > 1024 * 1024:
    raise SystemExit(2)
document = json.loads(content)
if [item.get("id") for item in document.get("data", [])] != [expected]:
    raise SystemExit(2)
' >/dev/null
}

restore_resources() (
  local reason="$1" attempt
  exec 9>"${restore_lock_file}" || return 1
  chmod 600 "${restore_lock_file}"
  flock -x 9 || return 1
  load_snapshot || {
    append_event "${reason}" "INVALID_VLM_SNAPSHOT"
    return 1
  }
  if ! candidate_down; then
    append_event "${reason}" "CANDIDATE_CLEANUP_FAILED"
    return 1
  fi
  append_event "${reason}" "CANDIDATE_REMOVED"
  if [[ "$(docker inspect --format '{{.Id}}' "${vlm_name}" 2>/dev/null || true)" != "${vlm_id}" ]]; then
    append_event "${reason}" "VLM_IDENTITY_MISSING"
    return 1
  fi
  if [[ "$(docker inspect --format '{{.State.Running}}' "${vlm_name}")" != "true" ]]; then
    docker start "${vlm_id}" >/dev/null || {
      append_event "${reason}" "VLM_START_FAILED"
      return 1
    }
  fi
  for attempt in {1..600}; do
    if validate_exact_vlm && authenticated_vlm_canary; then
      append_event "${reason}" "VLM_RESTORED_EXACT_HEALTHY"
      return 0
    fi
    sleep 5
  done
  append_event "${reason}" "VLM_RESTORE_TIMEOUT"
  return 1
)

case "${mode}" in
  restore-now)
    restore_resources "PARENT_TRAP"
    ;;
  monitor)
    private_regular_file "${owner_pid_file}" || exit 2
    private_regular_file "${owner_ticks_file}" || exit 2
    owner_pid="$(<"${owner_pid_file}")"
    owner_ticks="$(<"${owner_ticks_file}")"
    while [[ ! -f "${complete_file}" ]] && process_matches "${owner_pid}" "${owner_ticks}"; do
      sleep 2
    done
    [[ -f "${complete_file}" ]] && exit 0
    append_event "WATCHDOG" "OWNER_LOST"
    restore_resources "WATCHDOG"
    ;;
  *) usage ;;
esac
