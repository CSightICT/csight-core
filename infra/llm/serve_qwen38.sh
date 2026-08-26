#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
env_file="${1:-${script_dir}/.env.llm}"

if [[ ! -f "${env_file}" ]]; then
  echo "missing private runtime env file: ${env_file}" >&2
  exit 2
fi

for required_name in LLM_BIND_ADDRESS LLM_API_KEY; do
  if ! grep -Eq "^${required_name}=.+" "${env_file}"; then
    echo "${required_name} must be set in the private runtime env file" >&2
    exit 2
  fi
done

docker compose \
  --env-file "${env_file}" \
  -f "${script_dir}/compose.llm.yml" \
  config --quiet
docker compose \
  --env-file "${env_file}" \
  -f "${script_dir}/compose.llm.yml" \
  up --detach --wait qwen38
