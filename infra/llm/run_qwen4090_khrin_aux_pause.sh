#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly -a KHRIN_AUX_ALLOWLIST=(
  counsel-rag-api-1
  counsel-rag-embedding-worker-1-1
  counsel-rag-embedding-worker-2-1
  counsel-rag-gpu-staging-api-1
  counsel-rag-neo4j-1
  counsel-rag-policy-support-worker-1-1
  counsel-rag-policy-support-worker-2-1
  counsel-rag-redis-1
  counsel-rag-router-worker-1-1
  counsel-rag-router-worker-2-1
  counsel-rag-staging-api-1
  counsel-rag-stt-v2-stt-staging-api-1
)

if [[ "${1:-}" == "--print-allowlist" ]]; then
  printf '%s\n' "${KHRIN_AUX_ALLOWLIST[@]}"
  exit 0
fi
if [[ "$#" -ne 0 || "${ALLOW_KHRIN_AUXILIARY_PAUSE:-}" != "YES" ]]; then
  echo "set ALLOW_KHRIN_AUXILIARY_PAUSE=YES for an approved Khrin maintenance window" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
watchdog_script="${CSIGHT_KHRIN_WATCHDOG_SCRIPT:-${script_dir}/qwen4090_khrin_aux_restore_watchdog.sh}"
maintenance_script="${CSIGHT_IMATRIX_MAINTENANCE_SCRIPT:-${script_dir}/run_qwen4090_llama_imatrix_maintenance.sh}"
evidence_root="${CSIGHT_KHRIN_AUX_EVIDENCE_ROOT:-}"
requested="${CSIGHT_KHRIN_PAUSE_CONTAINERS:-}"
tool_image="${LLAMA_CPP_TOOL_IMAGE_ID:-}"

for path in "${watchdog_script}" "${maintenance_script}"; do
  if [[ "${path}" != /* || ! -f "${path}" || -L "${path}" ]]; then
    echo "maintenance and watchdog scripts must be absolute, real files" >&2
    exit 2
  fi
done
if [[ "${evidence_root}" != /* || ! -d "${evidence_root}" || -L "${evidence_root}" \
  || "$(stat -c '%u:%a' "${evidence_root}")" != "$(id -u):700" ]]; then
  echo "CSIGHT_KHRIN_AUX_EVIDENCE_ROOT must be an owner-only mode 700 directory" >&2
  exit 2
fi
if [[ -z "${requested}" ]]; then
  echo "CSIGHT_KHRIN_PAUSE_CONTAINERS must name explicit allowlisted containers" >&2
  exit 2
fi
if [[ ! "${tool_image}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "LLAMA_CPP_TOOL_IMAGE_ID must be an exact local Docker image ID" >&2
  exit 2
fi
for command in docker nohup setsid ps; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "required command is unavailable: ${command}" >&2
    exit 2
  }
done

is_allowlisted() {
  local candidate="$1" allowed
  for allowed in "${KHRIN_AUX_ALLOWLIST[@]}"; do
    [[ "${candidate}" == "${allowed}" ]] && return 0
  done
  return 1
}

declare -a targets=()
declare -A seen=()
while IFS= read -r name; do
  [[ -n "${name}" ]] || continue
  if [[ ! "${name}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || ! is_allowlisted "${name}"; then
    echo "container is not in the Khrin auxiliary allowlist: ${name}" >&2
    exit 2
  fi
  [[ -z "${seen[${name}]:-}" ]] || {
    echo "duplicate container requested: ${name}" >&2
    exit 2
  }
  seen["${name}"]=1
  targets+=("${name}")
done <<<"${requested}"
[[ "${#targets[@]}" -gt 0 ]] || exit 2

backend_probe_output=""
if ! backend_probe_output="$(
  docker run --rm --pull=never --network none --gpus all --read-only \
    --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
    --entrypoint /app/llama-imatrix "${tool_image}" --list-devices 2>&1
)"; then
  echo "llama.cpp backend discovery probe failed before auxiliary services were stopped" >&2
  exit 2
fi
if ! grep -Fq "Available devices:" <<<"${backend_probe_output}" \
  || grep -Fq "  (none)" <<<"${backend_probe_output}" \
  || ! grep -Eq '^  CUDA[0-9]+:' <<<"${backend_probe_output}"; then
  echo "llama.cpp image did not expose a CUDA device through its dynamic backend" >&2
  exit 2
fi
unset backend_probe_output

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
state_dir="${evidence_root}/${run_id}"
mkdir --mode=700 "${state_dir}"
snapshot_file="${state_dir}/containers.tsv"
wrapper_log="${state_dir}/wrapper-events.tsv"
watchdog_log="${state_dir}/watchdog.log"
complete_file="${state_dir}/restore.complete"
: >"${snapshot_file}"
: >"${wrapper_log}"
: >"${watchdog_log}"
chmod 600 "${snapshot_file}" "${wrapper_log}" "${watchdog_log}"

for name in "${targets[@]}"; do
  running="$(docker inspect --format '{{.State.Running}}' "${name}" 2>/dev/null || true)"
  [[ "${running}" == "true" ]] || {
    echo "only already-running containers may be paused: ${name}" >&2
    exit 2
  }
  container_id="$(docker inspect --format '{{.Id}}' "${name}")"
  image_id="$(docker inspect --format '{{.Image}}' "${name}")"
  image_ref="$(docker inspect --format '{{.Config.Image}}' "${name}")"
  health="$(docker inspect --format \
    '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${name}")"
  if [[ ! "${container_id}" =~ ^[0-9a-f]{64}$ \
    || ! "${image_id}" =~ ^sha256:[0-9a-f]{64}$ \
    || ! "${image_ref}" =~ ^[a-zA-Z0-9._/@:+-]+$ \
    || ! "${health}" =~ ^(none|starting|healthy|unhealthy)$ ]]; then
    echo "unsafe container identity or health metadata: ${name}" >&2
    exit 2
  fi
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "${name}" "${container_id}" "${image_id}" "${image_ref}" "${health}" \
    >>"${snapshot_file}"
done

process_start_ticks() {
  local stat_line remainder
  IFS= read -r stat_line <"/proc/$$/stat"
  remainder="${stat_line##*) }"
  awk '{print $20}' <<<"${remainder}"
}
printf '%s\n' "$$" >"${state_dir}/owner.pid"
process_start_ticks >"${state_dir}/owner.start_ticks"
chmod 600 "${state_dir}/owner.pid" "${state_dir}/owner.start_ticks"

nohup setsid bash "${watchdog_script}" monitor "${state_dir}" \
  >>"${watchdog_log}" 2>&1 </dev/null &
watchdog_pid="$!"
sleep 1
kill -0 "${watchdog_pid}" 2>/dev/null || {
  echo "independent restoration watchdog did not start" >&2
  exit 2
}

child_pid=""
cleanup() {
  local original_status="$?" restore_status=0
  trap - EXIT HUP INT TERM
  set +e
  if [[ -n "${child_pid}" ]] && kill -0 "${child_pid}" 2>/dev/null; then
    kill -HUP -- "-${child_pid}" 2>/dev/null || true
    wait "${child_pid}" 2>/dev/null || true
  fi
  bash "${watchdog_script}" restore-now "${state_dir}"
  restore_status="$?"
  if [[ "${restore_status}" -eq 0 ]]; then
    : >"${complete_file}"
    chmod 600 "${complete_file}"
    wait "${watchdog_pid}" 2>/dev/null || true
    printf '%s\tRESTORED\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "${original_status}" >>"${wrapper_log}"
  else
    printf '%s\tRESTORE_FAILED_WATCHDOG_REMAINS\t%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${restore_status}" >>"${wrapper_log}"
    echo "auxiliary restoration failed; watchdog evidence: ${state_dir}" >&2
    exit 90
  fi
  echo "KHRIN_AUX_RESTORE_EVIDENCE path=${state_dir}"
  exit "${original_status}"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

for name in "${targets[@]}"; do
  docker stop --time 30 "${name}" >/dev/null
  if [[ "$(docker inspect --format '{{.State.Running}}' "${name}")" != "false" ]]; then
    echo "container did not stop: ${name}" >&2
    exit 75
  fi
done

setsid bash "${watchdog_script}" launch-maintenance "${state_dir}" \
  "${maintenance_script}" &
child_pid="$!"
wait "${child_pid}"
