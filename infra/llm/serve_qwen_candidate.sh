#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../.." && pwd)"
candidate_id="${1:-}"
env_file="${2:-${script_dir}/.env.llm}"
base_compose="${script_dir}/compose.llm.yml"

case "${candidate_id}" in
  qwen38-27b-awq-int4-community-vllm028)
    expected_model_id="csight-qwen3.8-27b-vllm028-shadow"
    tooling_image="vllm/vllm-openai:v0.28.0@sha256:61fc8a896b0a4fbbbdc063bc4b0dbc25ce98e02b5050c24aeb7830ac02039b14"
    ;;
  qwen3-8b-fp8-official-vllm026)
    expected_model_id="csight-qwen3-8b-fp8-shadow"
    tooling_image="vllm/vllm-openai:v0.26.0@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"
    ;;
  *)
    echo "candidate is not an allowlisted runnable Shadow profile: ${candidate_id:-<empty>}" >&2
    exit 2
    ;;
esac

profile_file="${script_dir}/candidates/${candidate_id}.compose.json"
for required_file in "${env_file}" "${base_compose}" "${profile_file}"; do
  if [[ ! -f "${required_file}" || -L "${required_file}" ]]; then
    echo "required regular file is missing or unsafe: ${required_file}" >&2
    exit 2
  fi
done
for required_name in LLM_BIND_ADDRESS LLM_API_KEY; do
  if ! grep -Eq "^${required_name}=.+" "${env_file}"; then
    echo "${required_name} must be set in the private runtime env file" >&2
    exit 2
  fi
done

cd "${repo_root}"
tooling_mode="${QWEN4090_TOOLING_MODE:-host}"
case "${tooling_mode}" in
  host)
    uv run python scripts/verify_qwen4090_compose_profiles.py >/dev/null
    ;;
  container)
    docker run --rm --pull=never --network none \
      -e PYTHONPATH=/work \
      -w /work \
      --entrypoint python3 \
      -v "${repo_root}:/work:ro" \
      "${tooling_image}" \
      scripts/verify_qwen4090_compose_profiles.py >/dev/null
    ;;
  *)
    echo "QWEN4090_TOOLING_MODE must be host or container" >&2
    exit 2
    ;;
esac

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "SHADOW_CANDIDATE_VALID candidate=${candidate_id} model=${expected_model_id}"
  exit 0
fi

# A live start is fail-closed until the exact GPU host, private bind, runtime image, staged
# snapshot, lock, SBOM and recipe match the frozen matrix. Shadow may retain only an explicitly
# undisclosed upstream calibration revision; release assessment still rejects that provenance gap.
if [[ "${tooling_mode}" == "container" ]]; then
  "${script_dir}/run_qwen4090_host_preflight_container.sh" \
    "${candidate_id}" "${env_file}" shadow >/dev/null
else
  uv run python scripts/preflight_qwen4090_host.py \
    --candidate-id "${candidate_id}" \
    --runtime-env "${env_file}" \
    --allow-shadow-provenance-incomplete >/dev/null
fi

docker compose \
  --env-file "${env_file}" \
  -f "${base_compose}" \
  -f "${profile_file}" \
  config --quiet
docker compose \
  --env-file "${env_file}" \
  -f "${base_compose}" \
  -f "${profile_file}" \
  up --detach --wait qwen38

docker compose \
  --env-file "${env_file}" \
  -f "${base_compose}" \
  -f "${profile_file}" \
  exec -T -e "CSIGHT_EXPECTED_MODEL_ID=${expected_model_id}" qwen38 python3 - <<'PY'
import json
import os
import urllib.request

expected = os.environ["CSIGHT_EXPECTED_MODEL_ID"]
request = urllib.request.Request(
    "http://127.0.0.1:8000/v1/models",
    headers={"Authorization": f"Bearer {os.environ['VLLM_API_KEY']}"},
)
with urllib.request.urlopen(request, timeout=30) as response:
    payload = json.load(response)
model_ids = {item.get("id") for item in payload.get("data", [])}
if model_ids != {expected}:
    raise SystemExit("served model alias canary failed")
print(f"SHADOW_MODEL_CANARY_PASS model={expected}")
PY

echo "SHADOW_CANDIDATE_READY candidate=${candidate_id}"
