#!/bin/sh
set -eu
curl --fail --silent "${RERANKER_BASE_URL:-http://127.0.0.1:8092}/health" >/dev/null
curl --fail --silent "${RERANKER_BASE_URL:-http://127.0.0.1:8092}/v1/models" >/dev/null
