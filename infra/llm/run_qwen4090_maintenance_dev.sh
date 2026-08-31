#!/usr/bin/env bash
set -euo pipefail

if [[ "${ALLOW_VLM_MAINTENANCE:-}" != "YES" ]]; then
  echo "set ALLOW_VLM_MAINTENANCE=YES only for an approved VLM maintenance window" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../.." && pwd)"
candidate_id="${1:-}"
candidate_env="${2:-}"
evaluation_env="${3:-}"
evaluator_image="${QWEN4090_EVALUATOR_IMAGE:-}"
result_root="${QWEN4090_RESULT_ROOT:-}"
vlm_compose_dir="${CSIGHT_VLM_COMPOSE_DIR:-}"
vlm_restore_env="${CSIGHT_VLM_RESTORE_ENV:-}"
vlm_health_url="${CSIGHT_VLM_HEALTH_URL:-}"
vlm_container="${CSIGHT_VLM_CONTAINER:-csight-kaputt-vlm-qwen38-vlm-1}"
vlm_service="${CSIGHT_VLM_SERVICE:-qwen38-vlm}"
expected_vlm_image="vllm/vllm-openai:v0.26.0@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"
vlm_compose_file="${vlm_compose_dir}/compose.vlm.yml"

case "${candidate_id}" in
  qwen38-27b-awq-int4-community-vllm028|qwen3-8b-fp8-official-vllm026) ;;
  *)
    echo "candidate is not an allowlisted Shadow profile" >&2
    exit 2
    ;;
esac

for required_file in "${candidate_env}" "${evaluation_env}" "${vlm_restore_env}" "${vlm_compose_file}"; do
  if [[ -z "${required_file}" || ! -f "${required_file}" || -L "${required_file}" ]]; then
    echo "a required private environment or Compose file is missing or unsafe" >&2
    exit 2
  fi
done
if [[ -z "${evaluator_image}" || -z "${result_root}" || -z "${vlm_health_url}" ]]; then
  echo "evaluator image, result root, and VLM health URL are required" >&2
  exit 2
fi
if [[ "${result_root}" != /* || "${result_root}" == *:* ]]; then
  echo "QWEN4090_RESULT_ROOT must be a safe absolute host path" >&2
  exit 2
fi
install -d -m 700 "${result_root}"

if [[ "$(docker inspect --format '{{.State.Running}}' "${vlm_container}" 2>/dev/null)" != "true" ]]; then
  echo "the expected VLM container is not running" >&2
  exit 2
fi
if [[ "$(docker inspect --format '{{.Config.Image}}' "${vlm_container}")" != "${expected_vlm_image}" ]]; then
  echo "the running VLM image identity does not match the restoration contract" >&2
  exit 2
fi
curl --fail --silent --show-error --max-time 10 "${vlm_health_url}" >/dev/null
docker image inspect "${evaluator_image}" >/dev/null

candidate_profile="${script_dir}/candidates/${candidate_id}.compose.json"

stop_candidate() {
  docker compose \
    --env-file "${candidate_env}" \
    -f "${script_dir}/compose.llm.yml" \
    -f "${candidate_profile}" \
    down --remove-orphans >/dev/null 2>&1 || true
}

restore_vlm() {
  local original_status="$?"
  local candidate_failure_log=""
  trap - EXIT INT TERM
  set +e
  if [[ "${original_status}" -ne 0 ]]; then
    umask 077
    candidate_failure_log="$(mktemp "${result_root}/${candidate_id}-failure.XXXXXX.log")"
    docker compose \
      --env-file "${candidate_env}" \
      -f "${script_dir}/compose.llm.yml" \
      -f "${candidate_profile}" \
      logs --no-color --tail 400 qwen38 >"${candidate_failure_log}" 2>&1 || true
    chmod 600 "${candidate_failure_log}"
    echo "CANDIDATE_FAILURE_LOG_WRITTEN candidate=${candidate_id}"
  fi
  stop_candidate
  docker compose \
    --env-file "${vlm_restore_env}" \
    -f "${vlm_compose_file}" \
    up --detach --wait "${vlm_service}"
  local compose_status="$?"
  curl --fail --silent --show-error --retry 12 --retry-all-errors \
    --retry-delay 5 --max-time 10 "${vlm_health_url}" >/dev/null
  local health_status="$?"
  if [[ "${compose_status}" -ne 0 || "${health_status}" -ne 0 ]]; then
    echo "VLM restoration failed; operator attention is required" >&2
    exit 90
  fi
  echo "VLM_RESTORED_HEALTHY"
  exit "${original_status}"
}

trap restore_vlm EXIT
trap 'exit 130' INT TERM

docker compose \
  --env-file "${vlm_restore_env}" \
  -f "${vlm_compose_file}" \
  stop "${vlm_service}"

QWEN4090_TOOLING_MODE=container \
  "${script_dir}/serve_qwen_candidate.sh" "${candidate_id}" "${candidate_env}"

uid="$(id -u)"
gid="$(id -g)"
docker run --rm --pull=never --network host --gpus all \
  --user "${uid}:${gid}" \
  -e HOME=/tmp \
  -e PYTHONPATH=/work \
  -v "${repo_root}:/work:ro" \
  -v "${evaluation_env}:${evaluation_env}:ro" \
  -v "${result_root}:/results:rw" \
  -w /work \
  --entrypoint /app/.venv/bin/python \
  "${evaluator_image}" \
  scripts/evaluate_extraction_v2_qwen.py \
  --candidate-id "${candidate_id}" \
  --env-file "${evaluation_env}" \
  --result-root /results \
  --split dev

echo "QWEN4090_DEV_FINISHED candidate=${candidate_id}"
