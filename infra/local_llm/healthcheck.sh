#!/usr/bin/env bash
set -euo pipefail

runtime_host="${LOCAL_LLM_HOST:-127.0.0.1}"
runtime_port="${LOCAL_LLM_PORT:-8080}"
base_url="http://${runtime_host}:${runtime_port}"

curl --fail --silent --show-error "${base_url}/health"
printf '\n'
curl --fail --silent --show-error "${base_url}/v1/models"
printf '\n'
