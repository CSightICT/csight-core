#!/usr/bin/env bash
set -euo pipefail

runtime_host="${VISION_E3_HOST:-127.0.0.1}"
runtime_port="${VISION_E3_PORT:-8093}"
if [[ -n "${VISION_E3_API_KEY:-}" ]]; then
  curl --fail --silent --show-error \
    --header "Authorization: Bearer ${VISION_E3_API_KEY}" \
    "http://${runtime_host}:${runtime_port}/health"
else
  curl --fail --silent --show-error "http://${runtime_host}:${runtime_port}/health"
fi
printf '\n'
