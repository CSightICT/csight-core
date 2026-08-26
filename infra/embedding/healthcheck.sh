#!/bin/sh
set -eu
curl --fail --silent --show-error "${EMBEDDING_BASE_URL:-http://127.0.0.1:8091}/health"
