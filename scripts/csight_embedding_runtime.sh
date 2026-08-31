#!/bin/zsh

# Detached macOS runtime for the host-native policy retrieval embedding service.

emulate -L zsh
set -eu

readonly PROJECT_ROOT="${CSIGHT_CONTROL_PROJECT_ROOT:-${0:A:h:h}}"
readonly EMBEDDING_PORT="${EMBEDDING_PORT:-8091}"
readonly EMBEDDING_UVICORN="${PROJECT_ROOT}/.venv-embedding/bin/uvicorn"
readonly EMBEDDING_LOG_FILE="${PROJECT_ROOT}/.embedding-service.log"
readonly EMBEDDING_PID_FILE="${PROJECT_ROOT}/.embedding-service.pid"

[[ -x "${EMBEDDING_UVICORN}" ]] || {
  print -u2 -- "Embedding runtime not found: ${EMBEDDING_UVICORN}"
  exit 1
}

cd "${PROJECT_ROOT}"
exec >> "${EMBEDDING_LOG_FILE}" 2>&1
print -- "$$" > "${EMBEDDING_PID_FILE}"
exec /usr/bin/env EMBEDDING_PORT="${EMBEDDING_PORT}" \
  "${EMBEDDING_UVICORN}" infra.embedding.server:app \
  --host 127.0.0.1 --port "${EMBEDDING_PORT}" --no-access-log
