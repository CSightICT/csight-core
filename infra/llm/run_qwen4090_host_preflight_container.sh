#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../.." && pwd)"
candidate_id="${1:-}"
runtime_env="${2:-${script_dir}/.env.llm}"
mode="${3:-strict}"

case "${candidate_id}" in
  qwen38-27b-awq-int4-community-vllm028)
    runner_image="vllm/vllm-openai:v0.28.0@sha256:61fc8a896b0a4fbbbdc063bc4b0dbc25ce98e02b5050c24aeb7830ac02039b14"
    ;;
  qwen3-8b-fp8-official-vllm026)
    runner_image="vllm/vllm-openai:v0.26.0@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"
    ;;
  *)
    echo "candidate is not an allowlisted runnable Shadow profile" >&2
    exit 2
    ;;
esac

if [[ "${mode}" != "strict" && "${mode}" != "collect-unpinned" && "${mode}" != "shadow" ]]; then
  echo "mode must be strict, collect-unpinned, or shadow" >&2
  exit 2
fi
if [[ ! -f "${runtime_env}" || -L "${runtime_env}" ]]; then
  echo "runtime env must be a regular non-symlink file" >&2
  exit 2
fi
runtime_env="$(cd -- "$(dirname -- "${runtime_env}")" && pwd)/$(basename -- "${runtime_env}")"

read_env_path() {
  local name="$1"
  local value
  value="$(sed -n "s/^${name}=//p" "${runtime_env}")"
  if [[ -z "${value}" || "${value}" != /* || "${value}" == *:* || "${value}" == *$'\n'* ]]; then
    echo "${name} must be one safe absolute host path" >&2
    exit 2
  fi
  printf '%s' "${value}"
}

model_cache="$(read_env_path LLM_MODEL_CACHE_DIR)"
dependency_lock="$(read_env_path QWEN4090_DEPENDENCY_LOCK_FILE)"
sbom="$(read_env_path QWEN4090_SBOM_FILE)"
output_dir="$(read_env_path QWEN4090_PREFLIGHT_OUTPUT_DIR)"

for input_path in "${model_cache}" "${dependency_lock}" "${sbom}" "${output_dir}"; do
  if [[ ! -e "${input_path}" || -L "${input_path}" ]]; then
    echo "required preflight path is missing or unsafe" >&2
    exit 2
  fi
done

optional_mounts=()
for optional_name in QWEN4090_QUANTIZATION_RECIPE_FILE QWEN4090_CALIBRATION_MANIFEST_FILE; do
  optional_path="$(sed -n "s/^${optional_name}=//p" "${runtime_env}")"
  if [[ -z "${optional_path}" ]]; then
    continue
  fi
  if [[ "${optional_path}" != /* || "${optional_path}" == *:* || ! -f "${optional_path}" || -L "${optional_path}" ]]; then
    echo "${optional_name} must be one safe regular file" >&2
    exit 2
  fi
  optional_mounts+=(-v "${optional_path}:${optional_path}:ro")
done

docker_socket="/var/run/docker.sock"
docker_binary="$(command -v docker)"
if [[ ! -S "${docker_socket}" || -z "${docker_binary}" ]]; then
  echo "Docker socket or CLI is unavailable" >&2
  exit 2
fi

uid="$(id -u)"
gid="$(id -g)"
socket_gid="$(stat -c %g "${docker_socket}")"
arguments=(
  run --rm --pull=never
  --network host
  --pid host
  --gpus all
  --user "${uid}:${gid}"
  --group-add "${socket_gid}"
  -e PYTHONPATH=/work
  -w /work
  --entrypoint python3
  -v "${docker_binary}:/usr/bin/docker:ro"
  -v "${docker_socket}:${docker_socket}"
  -v "${repo_root}:/work:ro"
  -v "${runtime_env}:${runtime_env}:ro"
  -v "${model_cache}:${model_cache}:ro"
  -v "${dependency_lock}:${dependency_lock}:ro"
  -v "${sbom}:${sbom}:ro"
  -v "${output_dir}:${output_dir}:rw"
  "${optional_mounts[@]}"
  "${runner_image}"
  scripts/preflight_qwen4090_host.py
  --candidate-id "${candidate_id}"
  --runtime-env "${runtime_env}"
)
if [[ "${mode}" == "collect-unpinned" ]]; then
  arguments+=(--collect-unpinned)
elif [[ "${mode}" == "shadow" ]]; then
  arguments+=(--allow-shadow-provenance-incomplete)
fi

exec docker "${arguments[@]}"
