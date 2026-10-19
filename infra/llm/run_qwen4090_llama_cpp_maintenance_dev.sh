#!/usr/bin/env bash
set -euo pipefail

if [[ "${ALLOW_VLM_MAINTENANCE:-}" != "YES" ]]; then
  echo "set ALLOW_VLM_MAINTENANCE=YES only for an approved VLM maintenance window" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
candidate_id="${1:-}"
candidate_env="${2:-}"
vlm_compose_file="${CSIGHT_VLM_COMPOSE_FILE:-}"
vlm_restore_env="${CSIGHT_VLM_RESTORE_ENV:-}"
vlm_service="${CSIGHT_VLM_SERVICE:-qwen38-vlm}"
vlm_health_url="${CSIGHT_VLM_HEALTH_URL:-}"
expected_vlm_image="${CSIGHT_EXPECTED_VLM_IMAGE:-}"
minimum_mem_available_kib=$((50 * 1024 * 1024))

for path in "${candidate_env}" "${vlm_compose_file}" "${vlm_restore_env}"; do
  if [[ -z "${path}" || "${path}" != /* || ! -f "${path}" || -L "${path}" ]]; then
    echo "candidate and restoration inputs must be absolute regular files" >&2
    exit 2
  fi
done
for private_env in "${candidate_env}" "${vlm_restore_env}"; do
  if [[ "$(stat -c '%u:%a' "${private_env}")" != "$(id -u):600" ]]; then
    echo "candidate and restoration environments must be owner-only mode 600" >&2
    exit 2
  fi
done
if [[ ! "${expected_vlm_image}" =~ @sha256:[0-9a-f]{64}$ || -z "${vlm_health_url}" ]]; then
  echo "digest-pinned VLM identity and health URL are required" >&2
  exit 2
fi

vlm_compose=(docker compose --env-file "${vlm_restore_env}" -f "${vlm_compose_file}")
expected_vlm_image_id="$(docker image inspect --format '{{.Id}}' "${expected_vlm_image}")"

require_running_vlm_identity() {
  local container_id configured_image running_image_id
  container_id="$("${vlm_compose[@]}" ps --quiet "${vlm_service}")"
  if [[ ! "${container_id}" =~ ^[0-9a-f]{12,64}$ ]]; then
    echo "the protected VLM container is not running" >&2
    return 1
  fi
  if [[ "$(docker inspect --format '{{.State.Running}}' "${container_id}")" != "true" ]]; then
    echo "the protected VLM container is not in the running state" >&2
    return 1
  fi
  configured_image="$(docker inspect --format '{{.Config.Image}}' "${container_id}")"
  running_image_id="$(docker inspect --format '{{.Image}}' "${container_id}")"
  if [[ "${configured_image}" != "${expected_vlm_image}" \
    || "${running_image_id}" != "${expected_vlm_image_id}" ]]; then
    echo "the running VLM does not match the digest-pinned restoration contract" >&2
    return 1
  fi
}

require_running_vlm_identity
curl --fail --silent --show-error --max-time 10 "${vlm_health_url}" >/dev/null

restore_vlm() {
  local original_status="$?"
  trap - EXIT INT TERM
  docker compose --env-file "${candidate_env}" -f "${script_dir}/compose.llama-cpp.yml" down >/dev/null 2>&1 || true
  "${vlm_compose[@]}" up --detach --wait "${vlm_service}"
  if ! require_running_vlm_identity \
    || ! curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 5 \
      --max-time 10 "${vlm_health_url}" >/dev/null; then
    echo "the protected VLM could not be restored to its exact healthy identity" >&2
    exit 90
  fi
  echo "VLM_RESTORED_HEALTHY"
  exit "${original_status}"
}
trap restore_vlm EXIT
trap 'exit 130' INT TERM

"${vlm_compose[@]}" stop "${vlm_service}"

mem_available_kib="$(
  awk '$1 == "MemAvailable:" { print $2; found = 1; exit } END { if (!found) exit 1 }' \
    /proc/meminfo
)" || {
  echo "unable to read MemAvailable after stopping the VLM" >&2
  exit 75
}
if [[ ! "${mem_available_kib}" =~ ^[0-9]+$ ]] \
  || (( mem_available_kib < minimum_mem_available_kib )); then
  echo "post-VLM-stop MemAvailable is below the required 50 GiB" >&2
  exit 75
fi
echo "POST_VLM_STOP_MEMORY_READY minimum_gib=50"

ALLOW_LLAMA_CPP_SERVE=YES "${script_dir}/serve_llama_cpp_candidate.sh" \
  "${candidate_id}" "${candidate_env}"
echo "LLAMA_CPP_SHADOW_MAINTENANCE_READY candidate=${candidate_id}"
