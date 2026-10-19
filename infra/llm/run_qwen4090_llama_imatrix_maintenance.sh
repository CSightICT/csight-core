#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "${ALLOW_LLAMA_IMATRIX_MAINTENANCE:-}" != "YES" ]]; then
  echo "set ALLOW_LLAMA_IMATRIX_MAINTENANCE=YES only for an approved maintenance window" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${CSIGHT_PYTHON_BIN:-python3}"
evidence_tool="${CSIGHT_IMATRIX_EVIDENCE_TOOL:-${script_dir}/qwen4090_imatrix_maintenance.py}"
vlm_compose_file="${CSIGHT_VLM_COMPOSE_FILE:-}"
vlm_restore_env="${CSIGHT_VLM_RESTORE_ENV:-}"
vlm_service="${CSIGHT_VLM_SERVICE:-qwen38-vlm}"
vlm_container="${CSIGHT_VLM_CONTAINER:-csight-kaputt-vlm-qwen38-vlm-1}"
vlm_health_url="${CSIGHT_VLM_HEALTH_URL:-}"
expected_vlm_image="${CSIGHT_EXPECTED_VLM_IMAGE:-}"
tool_image="${LLAMA_CPP_TOOL_IMAGE_ID:-}"
build_manifest="${LLAMA_CPP_BUILD_MANIFEST:-}"
build_manifest_digest="${LLAMA_CPP_BUILD_MANIFEST_DIGEST:-}"
q8_helper="${LLAMA_IMATRIX_Q8_HELPER:-}"
q8_digest="${LLAMA_IMATRIX_Q8_DIGEST:-}"
calibration_corpus="${LLAMA_IMATRIX_CALIBRATION_CORPUS:-}"
calibration_digest="${LLAMA_IMATRIX_CALIBRATION_DIGEST:-}"
output_root="${LLAMA_IMATRIX_OUTPUT_ROOT:-}"
evidence_root="${LLAMA_IMATRIX_EVIDENCE_ROOT:-}"
context_size="${LLAMA_IMATRIX_CONTEXT_SIZE:-512}"
batch_size="${LLAMA_IMATRIX_BATCH_SIZE:-512}"
ubatch_size="${LLAMA_IMATRIX_UBATCH_SIZE:-128}"
chunks="${LLAMA_IMATRIX_CHUNKS:--1}"
minimum_mem_available_kib=$((50 * 1024 * 1024))

if ! command -v "${python_bin}" >/dev/null 2>&1; then
  echo "CSIGHT_PYTHON_BIN is unavailable" >&2
  exit 2
fi
for required in \
  "${evidence_tool}" "${vlm_compose_file}" "${vlm_restore_env}" \
  "${build_manifest}" "${q8_helper}" "${calibration_corpus}"; do
  if [[ -z "${required}" || ! -f "${required}" || -L "${required}" ]]; then
    echo "a required maintenance input is missing or unsafe" >&2
    exit 2
  fi
done
for absolute_path in \
  "${evidence_tool}" "${vlm_compose_file}" "${vlm_restore_env}" "${build_manifest}" "${q8_helper}" \
  "${calibration_corpus}" "${output_root}" "${evidence_root}"; do
  if [[ "${absolute_path}" != /* ]]; then
    echo "all maintenance paths must be absolute" >&2
    exit 2
  fi
done
if [[ "$(stat -c '%u:%a' "${vlm_restore_env}")" != "$(id -u):600" ]]; then
  echo "VLM restoration environment must be owner-only mode 600" >&2
  exit 2
fi
if [[ "$(stat -c '%u:%a' "${evidence_tool}")" != "$(id -u):600" ]]; then
  echo "standalone evidence tool must be owner-only mode 600" >&2
  exit 2
fi
if [[ ! "${expected_vlm_image}" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "CSIGHT_EXPECTED_VLM_IMAGE must be digest pinned" >&2
  exit 2
fi
if [[ -z "${vlm_health_url}" ]]; then
  echo "CSIGHT_VLM_HEALTH_URL is required" >&2
  exit 2
fi
if [[ ! "${tool_image}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "LLAMA_CPP_TOOL_IMAGE_ID must be an exact local Docker image ID" >&2
  exit 2
fi
for digest in "${q8_digest}" "${calibration_digest}" "${build_manifest_digest}"; do
  if [[ ! "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "Q8 helper, calibration corpus, and build manifest require exact SHA-256 digests" >&2
    exit 2
  fi
done
for value in "${context_size}" "${batch_size}" "${ubatch_size}"; do
  if [[ ! "${value}" =~ ^[0-9]+$ ]]; then
    echo "imatrix context, batch, and ubatch must be integers" >&2
    exit 2
  fi
done
if [[ "${chunks}" != "-1" && ! "${chunks}" =~ ^[0-9]+$ ]]; then
  echo "imatrix chunks must be -1 or a bounded positive integer" >&2
  exit 2
fi
if (( context_size < 128 || context_size > 4096 \
      || batch_size < 32 || batch_size > 2048 \
      || ubatch_size < 32 || ubatch_size > 512 \
      || ubatch_size > batch_size \
      || (chunks != -1 && (chunks < 1 || chunks > 2048)) )); then
  echo "imatrix context/batch/chunk settings exceed the bounded maintenance profile" >&2
  exit 2
fi

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
output_dir="${output_root}/${run_id}"
evidence_dir="${evidence_root}/${run_id}"
mkdir --mode=700 "${output_dir}" "${evidence_dir}"
output_file="${output_dir}/qwen38-27b-imatrix.gguf"
log_file="${evidence_dir}/llama-imatrix.log"
preflight_file="${evidence_dir}/preflight.json"
evidence_file="${evidence_dir}/evidence.json"
printf 'LLAMA_IMATRIX_PROTECTED_RUN run_id=%s\n' "${run_id}" >"${log_file}"

"${python_bin}" "${evidence_tool}" preflight \
  --q8-helper "${q8_helper}" \
  --q8-digest "${q8_digest}" \
  --calibration-corpus "${calibration_corpus}" \
  --calibration-digest "${calibration_digest}" \
  --build-manifest "${build_manifest}" \
  --build-manifest-digest "${build_manifest_digest}" \
  --tool-image "${tool_image}" \
  --output-root "${output_root}" \
  --evidence-root "${evidence_root}" \
  --context-size "${context_size}" \
  --batch-size "${batch_size}" \
  --ubatch-size "${ubatch_size}" \
  --chunks "${chunks}" \
  --report "${preflight_file}" >/dev/null

expected_imatrix_binary_digest="$(
  "${python_bin}" -c \
    'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["imatrix_binary_digest"])' \
    "${preflight_file}"
)"
docker image inspect "${tool_image}" >/dev/null
observed_imatrix_binary_digest="sha256:$(
  docker run --rm --pull=never --network none --read-only \
    --cap-drop ALL --security-opt no-new-privileges \
    --entrypoint /usr/bin/sha256sum "${tool_image}" /app/llama-imatrix \
    | awk '{print $1}'
)"
if [[ "${observed_imatrix_binary_digest}" != "${expected_imatrix_binary_digest}" ]]; then
  echo "llama-imatrix binary does not match the build manifest" >&2
  exit 2
fi

backend_probe_output=""
if ! backend_probe_output="$(
  docker run --rm --pull=never --network none --gpus all --read-only \
    --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
    --entrypoint /app/llama-imatrix "${tool_image}" --list-devices 2>&1
)"; then
  echo "llama.cpp backend discovery probe failed before the protected services were stopped" >&2
  exit 2
fi
if ! grep -Fq "Available devices:" <<<"${backend_probe_output}" \
  || grep -Fq "  (none)" <<<"${backend_probe_output}" \
  || ! grep -Eq '^  CUDA[0-9]+:' <<<"${backend_probe_output}"; then
  echo "llama.cpp image did not expose a CUDA device through its dynamic backend" >&2
  exit 2
fi
unset backend_probe_output

if [[ "$(docker inspect --format '{{.State.Running}}' "${vlm_container}" 2>/dev/null)" != "true" ]]; then
  echo "the protected VLM container is not running" >&2
  exit 2
fi
if [[ "$(docker inspect --format '{{.Config.Image}}' "${vlm_container}")" != "${expected_vlm_image}" ]]; then
  echo "the running VLM image does not match the restoration contract" >&2
  exit 2
fi
curl --fail --silent --show-error --max-time 10 "${vlm_health_url}" >/dev/null

vlm_compose=(docker compose --env-file "${vlm_restore_env}" -f "${vlm_compose_file}")
container_name="csight-llama-imatrix-${run_id,,}"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cleanup_and_restore() {
  local original_status="$?"
  local restore_status=0
  local finalize_status=0
  local restored=false
  local finished_at
  trap - EXIT INT TERM
  set +e
  docker rm --force "${container_name}" >/dev/null 2>&1 || true
  "${vlm_compose[@]}" up --detach --wait "${vlm_service}"
  restore_status="$?"
  if [[ "${restore_status}" -eq 0 ]]; then
    curl --fail --silent --show-error --retry 12 --retry-all-errors \
      --retry-delay 5 --max-time 10 "${vlm_health_url}" >/dev/null
    restore_status="$?"
  fi
  if [[ "${restore_status}" -eq 0 ]]; then
    restored=true
  fi
  if [[ -e "${output_file}" || -L "${output_file}" ]]; then
    if [[ -f "${output_file}" && ! -L "${output_file}" ]]; then
      chmod 600 "${output_file}" || original_status=77
    else
      original_status=77
    fi
  fi
  finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "${python_bin}" "${evidence_tool}" finalize \
    --preflight-report "${preflight_file}" \
    --output-file "${output_file}" \
    --log-file "${log_file}" \
    --evidence-file "${evidence_file}" \
    --run-exit-code "${original_status}" \
    --vlm-restored "${restored}" \
    --started-at "${started_at}" \
    --finished-at "${finished_at}" \
    --context-size "${context_size}" \
    --batch-size "${batch_size}" \
    --ubatch-size "${ubatch_size}" \
    --chunks "${chunks}" >/dev/null
  finalize_status="$?"
  echo "LLAMA_IMATRIX_LOG path=${log_file}"
  echo "LLAMA_IMATRIX_EVIDENCE path=${evidence_file}"
  if [[ "${restore_status}" -ne 0 ]]; then
    echo "VLM restoration failed; operator attention is required" >&2
    exit 90
  fi
  echo "VLM_RESTORED_HEALTHY"
  if [[ "${original_status}" -eq 0 && "${finalize_status}" -ne 0 ]]; then
    exit 76
  fi
  exit "${original_status}"
}

trap cleanup_and_restore EXIT
trap 'exit 129' HUP
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

uid="$(id -u)"
gid="$(id -g)"
run_status=0
docker run --name "${container_name}" --pull=never --network none --gpus all \
  --cpus 16 --memory 56g --memory-swap 56g --pids-limit 1024 \
  --user "${uid}:${gid}" --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:size=1g,mode=1777 \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e NO_PROXY='*' \
  -v "${q8_helper}:/inputs/helper-q8.gguf:ro" \
  -v "${calibration_corpus}:/inputs/calibration.txt:ro" \
  -v "${output_dir}:/output:rw" \
  --entrypoint /app/llama-imatrix \
  "${tool_image}" \
  --model /inputs/helper-q8.gguf \
  --file /inputs/calibration.txt \
  --output-file /output/qwen38-27b-imatrix.gguf \
  --output-format gguf \
  --no-ppl --parse-special --process-output \
  --output-frequency 1000000 --save-frequency 0 \
  --ctx-size "${context_size}" \
  --batch-size "${batch_size}" \
  --ubatch-size "${ubatch_size}" \
  --chunks "${chunks}" \
  --threads 16 \
  --threads-batch 16 \
  --n-gpu-layers auto \
  --flash-attn on >>"${log_file}" 2>&1 || run_status="$?"
exit "${run_status}"
