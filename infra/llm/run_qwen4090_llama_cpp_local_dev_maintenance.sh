#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  echo "usage: $0 CANDIDATE_ID RUNTIME_ENV EVIDENCE_ROOT -- DEV_COMMAND [ARG ...]" >&2
  exit 2
}

[[ "$#" -ge 5 ]] || usage
candidate_id="$1"
candidate_runtime_env="$2"
evidence_root="$3"
[[ "$4" == "--" ]] || usage
shift 4
dev_command=("$@")

if [[ "${ALLOW_VLM_MAINTENANCE:-}" != "YES" ]]; then
  echo "set ALLOW_VLM_MAINTENANCE=YES only for an approved VLM maintenance window" >&2
  exit 2
fi
case "${candidate_id}" in
  qwen38-27b-csight-q4-k-m-llama-cpp|qwen38-27b-csight-q5-k-s-llama-cpp) ;;
  *) echo "candidate is not allowlisted for DEV_LOCAL" >&2; exit 2 ;;
esac

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
launcher="${script_dir}/serve_llama_cpp_local_dev.sh"
watchdog="${script_dir}/qwen4090_local_dev_restore_watchdog.sh"
local_dev_python_bin="${CSIGHT_LOCAL_DEV_PYTHON_BIN:-}"
vlm_name="${CSIGHT_VLM_CONTAINER:-csight-kaputt-vlm-qwen38-vlm-1}"
expected_vlm_image="${CSIGHT_EXPECTED_VLM_IMAGE:-}"
expected_vlm_image_id="${CSIGHT_EXPECTED_VLM_IMAGE_ID:-}"
expected_vlm_config_hash="${CSIGHT_EXPECTED_VLM_CONFIG_HASH:-}"
expected_vlm_model_id="${CSIGHT_EXPECTED_VLM_MODEL_ID:-csight-qwen3.8-27b-vlm}"

for executable in "${launcher}" "${watchdog}"; do
  [[ -f "${executable}" && ! -L "${executable}" && -x "${executable}" ]] || {
    echo "required protected executable is missing or unsafe" >&2
    exit 2
  }
done
if [[ "${candidate_runtime_env}" != /* || ! -f "${candidate_runtime_env}" \
  || -L "${candidate_runtime_env}" \
  || "$(stat -c '%u:%a' "${candidate_runtime_env}")" != "$(id -u):600" ]]; then
  echo "candidate runtime env must be an absolute caller-owned mode-600 file" >&2
  exit 2
fi
if [[ "${evidence_root}" != /* || ! -d "${evidence_root}" || -L "${evidence_root}" \
  || "$(stat -c '%u:%a' "${evidence_root}")" != "$(id -u):700" ]]; then
  echo "evidence root must be an absolute caller-owned mode-700 directory" >&2
  exit 2
fi
if [[ ! "${expected_vlm_image}" =~ ^[a-zA-Z0-9._/@:+-]+$ \
  || ! "${expected_vlm_image_id}" =~ ^sha256:[0-9a-f]{64}$ \
  || ! "${expected_vlm_config_hash}" =~ ^[0-9a-f]{64}$ ]]; then
  echo "exact expected VLM image ref, image ID, and Compose config hash are required" >&2
  exit 2
fi
for command in awk docker flock nohup setsid ps; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "required command is unavailable: ${command}" >&2
    exit 2
  }
done

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

vlm_id="$(docker inspect --format '{{.Id}}' "${vlm_name}" 2>/dev/null || true)"
vlm_image_id="$(docker inspect --format '{{.Image}}' "${vlm_name}" 2>/dev/null || true)"
vlm_image_ref="$(docker inspect --format '{{.Config.Image}}' "${vlm_name}" 2>/dev/null || true)"
vlm_config_hash="$(docker inspect --format \
  '{{index .Config.Labels "com.docker.compose.config-hash"}}' "${vlm_name}" 2>/dev/null || true)"
vlm_running="$(docker inspect --format '{{.State.Running}}' "${vlm_name}" 2>/dev/null || true)"
vlm_health="$(docker inspect --format \
  '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
  "${vlm_name}" 2>/dev/null || true)"
vlm_restart_count="$(docker inspect --format '{{.RestartCount}}' "${vlm_name}" 2>/dev/null || true)"
vlm_oom="$(docker inspect --format '{{.State.OOMKilled}}' "${vlm_name}" 2>/dev/null || true)"
if [[ ! "${vlm_id}" =~ ^[0-9a-f]{64}$ \
  || "${vlm_image_id}" != "${expected_vlm_image_id}" \
  || "${vlm_image_ref}" != "${expected_vlm_image}" \
  || "${vlm_config_hash}" != "${expected_vlm_config_hash}" \
  || "${vlm_running}" != "true" \
  || "${vlm_health}" != "healthy" \
  || ! "${vlm_restart_count}" =~ ^[0-9]+$ \
  || "${vlm_oom}" != "false" ]]; then
  echo "the exact healthy VLM baseline is not available" >&2
  exit 2
fi

docker exec -e CSIGHT_EXPECTED_MODEL_ID="${expected_vlm_model_id}" "${vlm_id}" \
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

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
state_dir="${evidence_root}/${run_id}"
mkdir -m 700 "${state_dir}"
snapshot_file="${state_dir}/vlm.tsv"
runtime_path_file="${state_dir}/candidate-runtime-env.path"
owner_pid_file="${state_dir}/owner.pid"
owner_ticks_file="${state_dir}/owner.start_ticks"
guard_file="${state_dir}/restore.guard"
watchdog_log="${state_dir}/watchdog.log"
complete_file="${state_dir}/restore.complete"
post_start_evidence="${state_dir}/local-dev-post-start.json"

printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  "${vlm_id}" "${vlm_name}" "${vlm_image_id}" "${vlm_image_ref}" "${vlm_config_hash}" \
  "${vlm_restart_count}" "${vlm_oom}" "${expected_vlm_model_id}" >"${snapshot_file}"
printf '%s\n' "${candidate_runtime_env}" >"${runtime_path_file}"
printf '%s\n' "$$" >"${owner_pid_file}"
owner_stat="$(<"/proc/$$/stat")"
owner_remainder="${owner_stat##*) }"
awk '{print $20}' <<<"${owner_remainder}" >"${owner_ticks_file}"
: >"${watchdog_log}"
chmod 600 "${snapshot_file}" "${runtime_path_file}" "${owner_pid_file}" \
  "${owner_ticks_file}" "${watchdog_log}"

nohup setsid bash "${watchdog}" monitor "${state_dir}" \
  >>"${watchdog_log}" 2>&1 </dev/null &
watchdog_pid="$!"
sleep 1
kill -0 "${watchdog_pid}" 2>/dev/null || {
  echo "independent VLM restoration watchdog did not start" >&2
  exit 2
}
watchdog_stat="$(<"/proc/${watchdog_pid}/stat")"
watchdog_remainder="${watchdog_stat##*) }"
watchdog_ticks="$(awk '{print $20}' <<<"${watchdog_remainder}")"
{
  printf 'schema_version=csight_local_dev_restore_guard/1.0.0\n'
  printf 'candidate_id=%s\n' "${candidate_id}"
  printf 'owner_pid=%s\n' "$$"
  printf 'owner_start_ticks=%s\n' "$(<"${owner_ticks_file}")"
  printf 'watchdog_pid=%s\n' "${watchdog_pid}"
  printf 'watchdog_start_ticks=%s\n' "${watchdog_ticks}"
} >"${guard_file}"
chmod 600 "${guard_file}"

dev_pid=""
dev_ticks=""
cleanup() {
  local original_status="$?" restore_status=0
  trap - EXIT HUP INT TERM
  set +e
  if [[ -n "${dev_pid}" && -n "${dev_ticks}" ]] \
    && process_matches "${dev_pid}" "${dev_ticks}"; then
    kill -HUP -- "-${dev_pid}" 2>/dev/null || true
    wait "${dev_pid}" 2>/dev/null || true
  fi
  bash "${watchdog}" restore-now "${state_dir}"
  restore_status="$?"
  if [[ "${restore_status}" -eq 0 ]]; then
    : >"${complete_file}"
    chmod 600 "${complete_file}"
    wait "${watchdog_pid}" 2>/dev/null || true
    echo "DEV_LOCAL_VLM_RESTORED evidence=${state_dir}"
    exit "${original_status}"
  fi
  echo "exact VLM restoration failed; watchdog evidence: ${state_dir}" >&2
  exit 90
}

wait_with_live_watchdog() {
  local child_pid="$1" child_ticks="$2" child_status=0
  if ! process_matches "${watchdog_pid}" "${watchdog_ticks}"; then
    echo "independent VLM restoration watchdog exited before DEV_LOCAL child wait" >&2
    return 91
  fi
  while process_matches "${child_pid}" "${child_ticks}"; do
    if ! process_matches "${watchdog_pid}" "${watchdog_ticks}"; then
      echo "independent VLM restoration watchdog exited during DEV_LOCAL" >&2
      if process_matches "${child_pid}" "${child_ticks}"; then
        kill -HUP -- "-${child_pid}" 2>/dev/null || true
      fi
      wait "${child_pid}" 2>/dev/null || true
      dev_pid=""
      dev_ticks=""
      return 91
    fi
    sleep 2
  done
  if wait "${child_pid}"; then
    child_status=0
  else
    child_status="$?"
  fi
  dev_pid=""
  dev_ticks=""
  if ! process_matches "${watchdog_pid}" "${watchdog_ticks}"; then
    echo "independent VLM restoration watchdog exited after DEV_LOCAL child" >&2
    return 91
  fi
  return "${child_status}"
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if ! process_matches "${watchdog_pid}" "${watchdog_ticks}"; then
  echo "independent VLM restoration watchdog exited before maintenance" >&2
  exit 91
fi
docker stop --time 60 "${vlm_id}" >/dev/null
if [[ "$(docker inspect --format '{{.State.Running}}' "${vlm_name}")" != "false" ]]; then
  echo "protected VLM did not stop" >&2
  exit 75
fi

CSIGHT_LOCAL_DEV_RESTORE_GUARD="${guard_file}" \
CSIGHT_LOCAL_DEV_PYTHON_BIN="${local_dev_python_bin}" \
CSIGHT_LOCAL_DEV_POST_START_EVIDENCE="${post_start_evidence}" \
ALLOW_LLAMA_CPP_LOCAL_DEV=YES \
  setsid "${launcher}" "${candidate_id}" "${candidate_runtime_env}" &
dev_pid="$!"
dev_ticks="$(process_start_ticks "${dev_pid}")" || {
  echo "unable to bind DEV_LOCAL launcher to an exact process instance" >&2
  exit 91
}
wait_with_live_watchdog "${dev_pid}" "${dev_ticks}"

if ! process_matches "${watchdog_pid}" "${watchdog_ticks}"; then
  echo "independent VLM restoration watchdog exited before Dev evaluation wait" >&2
  exit 91
fi
setsid "${dev_command[@]}" &
dev_pid="$!"
dev_ticks="$(process_start_ticks "${dev_pid}")" || {
  echo "unable to bind Dev evaluation wait to an exact process instance" >&2
  exit 91
}
wait_with_live_watchdog "${dev_pid}" "${dev_ticks}"
echo "QWEN4090_DEV_LOCAL_COMMAND_FINISHED candidate=${candidate_id}"
