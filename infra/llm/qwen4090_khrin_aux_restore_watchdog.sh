#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  echo "usage: $0 monitor|restore-now|launch-maintenance STATE_DIR [MAINTENANCE_SCRIPT]" >&2
  exit 2
}

[[ "$#" -ge 2 ]] || usage
mode="$1"
state_dir="$2"

if [[ "${state_dir}" != /* || ! -d "${state_dir}" || -L "${state_dir}" ]]; then
  echo "watchdog state directory must be an absolute, real directory" >&2
  exit 2
fi
if [[ "$(stat -c '%u:%a' "${state_dir}")" != "$(id -u):700" ]]; then
  echo "watchdog state directory must be owner-only mode 700" >&2
  exit 2
fi

snapshot_file="${state_dir}/containers.tsv"
event_file="${state_dir}/restore-events.tsv"
complete_file="${state_dir}/restore.complete"
owner_pid_file="${state_dir}/owner.pid"
owner_ticks_file="${state_dir}/owner.start_ticks"
child_pid_file="${state_dir}/maintenance.pid"
child_ticks_file="${state_dir}/maintenance.start_ticks"
child_command_file="${state_dir}/maintenance.command"

private_regular_file() {
  local path="$1"
  [[ -f "${path}" && ! -L "${path}" ]] \
    && [[ "$(stat -c '%u:%a' "${path}")" == "$(id -u):600" ]]
}

process_start_ticks() {
  local pid="$1"
  local stat_line remainder
  [[ "${pid}" =~ ^[1-9][0-9]*$ && -r "/proc/${pid}/stat" ]] || return 1
  IFS= read -r stat_line <"/proc/${pid}/stat" || return 1
  remainder="${stat_line##*) }"
  awk '{print $20}' <<<"${remainder}"
}

process_matches() {
  local pid="$1"
  local expected_ticks="$2"
  local observed_ticks
  observed_ticks="$(process_start_ticks "${pid}")" || return 1
  [[ "${observed_ticks}" == "${expected_ticks}" ]]
}

append_event() {
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" >>"${event_file}"
  chmod 600 "${event_file}"
}

current_health() {
  local name="$1"
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "${name}"
}

restore_containers() {
  local reason="$1"
  local failure=0
  local name expected_id expected_image_id expected_image_ref expected_health
  local observed_id observed_image_id observed_image_ref observed_running final_health
  local health_attempt

  private_regular_file "${snapshot_file}" || {
    echo "owner-only container snapshot is missing" >&2
    return 2
  }

  while IFS=$'\t' read -r \
    name expected_id expected_image_id expected_image_ref expected_health; do
    [[ -n "${name}" ]] || continue
    if [[ ! "${name}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ \
      || ! "${expected_id}" =~ ^[0-9a-f]{64}$ \
      || ! "${expected_image_id}" =~ ^sha256:[0-9a-f]{64}$ \
      || ! "${expected_image_ref}" =~ ^[a-zA-Z0-9._/@:+-]+$ \
      || ! "${expected_health}" =~ ^(none|starting|healthy|unhealthy)$ ]]; then
      append_event "${reason}" "${name:-invalid}" "INVALID_SNAPSHOT" "unknown"
      failure=1
      continue
    fi

    observed_id="$(docker inspect --format '{{.Id}}' "${name}" 2>/dev/null || true)"
    observed_image_id="$(docker inspect --format '{{.Image}}' "${name}" 2>/dev/null || true)"
    observed_image_ref="$(docker inspect --format '{{.Config.Image}}' "${name}" 2>/dev/null || true)"
    if [[ "${observed_id}" != "${expected_id}" \
      || "${observed_image_id}" != "${expected_image_id}" \
      || "${observed_image_ref}" != "${expected_image_ref}" ]]; then
      append_event "${reason}" "${name}" "IDENTITY_MISMATCH_NOT_STARTED" "unknown"
      failure=1
      continue
    fi

    observed_running="$(docker inspect --format '{{.State.Running}}' "${name}")"
    if [[ "${observed_running}" != "true" ]]; then
      docker start "${name}" >/dev/null || {
        append_event "${reason}" "${name}" "START_FAILED" "unknown"
        failure=1
        continue
      }
    fi
    if [[ "$(docker inspect --format '{{.State.Running}}' "${name}")" != "true" ]]; then
      append_event "${reason}" "${name}" "NOT_RUNNING_AFTER_START" "unknown"
      failure=1
      continue
    fi
    if [[ "$(docker inspect --format '{{.Id}}' "${name}")" != "${expected_id}" \
      || "$(docker inspect --format '{{.Image}}' "${name}")" != "${expected_image_id}" ]]; then
      append_event "${reason}" "${name}" "IDENTITY_CHANGED_AFTER_START" "unknown"
      failure=1
      continue
    fi
    final_health="$(current_health "${name}")"
    if [[ "${expected_health}" == "healthy" ]]; then
      for health_attempt in {1..24}; do
        [[ "${final_health}" == "healthy" ]] && break
        sleep 5
        final_health="$(current_health "${name}")"
      done
    fi
    if [[ "${expected_health}" == "healthy" && "${final_health}" != "healthy" ]]; then
      append_event "${reason}" "${name}" "HEALTHY_BASELINE_NOT_RESTORED" "${final_health}"
      failure=1
      continue
    fi
    if [[ "${expected_health}" == "healthy" ]]; then
      append_event "${reason}" "${name}" "RESTORED_HEALTHY" "${final_health}"
    else
      # A container that was already unhealthy/starting is restored to running only.
      # Its health is recorded verbatim and is never upgraded to a healthy claim.
      append_event "${reason}" "${name}" "RESTORED_RUNNING_BASELINE_${expected_health^^}" \
        "${final_health}"
    fi
  done <"${snapshot_file}"

  return "${failure}"
}

case "${mode}" in
  launch-maintenance)
    [[ "$#" -eq 3 ]] || usage
    maintenance_script="$3"
    if [[ "${maintenance_script}" != /* || ! -f "${maintenance_script}" \
      || -L "${maintenance_script}" ]]; then
      echo "maintenance script must be an absolute, real file" >&2
      exit 2
    fi
    printf '%s\n' "$$" >"${child_pid_file}"
    process_start_ticks "$$" >"${child_ticks_file}"
    printf '%s\n' "${maintenance_script}" >"${child_command_file}"
    chmod 600 "${child_pid_file}" "${child_ticks_file}" "${child_command_file}"
    exec bash "${maintenance_script}"
    ;;
  restore-now)
    [[ "$#" -eq 2 ]] || usage
    restore_containers "PARENT_TRAP"
    ;;
  monitor)
    [[ "$#" -eq 2 ]] || usage
    private_regular_file "${owner_pid_file}" || exit 2
    private_regular_file "${owner_ticks_file}" || exit 2
    owner_pid="$(<"${owner_pid_file}")"
    owner_ticks="$(<"${owner_ticks_file}")"
    while [[ ! -f "${complete_file}" ]] && process_matches "${owner_pid}" "${owner_ticks}"; do
      sleep 2
    done
    [[ -f "${complete_file}" ]] && exit 0

    append_event "WATCHDOG" "wrapper" "OWNER_LOST" "unknown"
    if private_regular_file "${child_pid_file}" \
      && private_regular_file "${child_ticks_file}" \
      && private_regular_file "${child_command_file}"; then
      child_pid="$(<"${child_pid_file}")"
      child_ticks="$(<"${child_ticks_file}")"
      child_command="$(<"${child_command_file}")"
      if process_matches "${child_pid}" "${child_ticks}" \
        && tr '\0' '\n' <"/proc/${child_pid}/cmdline" | grep -Fqx -- "${child_command}"; then
        child_pgid="$(ps -o pgid= -p "${child_pid}" | tr -d ' ')"
        if [[ "${child_pgid}" == "${child_pid}" ]]; then
          kill -HUP -- "-${child_pgid}" 2>/dev/null || true
        fi
        for _ in {1..180}; do
          process_matches "${child_pid}" "${child_ticks}" || break
          sleep 1
        done
        if process_matches "${child_pid}" "${child_ticks}"; then
          append_event "WATCHDOG" "maintenance" "STILL_RUNNING_AUX_NOT_RESTORED" "unknown"
          exit 91
        fi
      fi
    fi
    if restore_containers "WATCHDOG"; then
      : >"${complete_file}"
      chmod 600 "${complete_file}"
      exit 0
    fi
    exit 90
    ;;
  *) usage ;;
esac
