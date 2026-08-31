#!/bin/zsh

# Separate, fail-closed controller for the qualified limited-pilot profile.
# It never builds, migrates, backs up, restores, cleans Docker data, or removes volumes.

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h}"
PILOT_ENV_FILE="${CSIGHT_PILOT_ENV_FILE:-${PROJECT_ROOT}/infra/pilot/.env.pilot}"
CORE_COMPOSE_FILE="${PROJECT_ROOT}/infra/compose.core.yml"
RLS_COMPOSE_FILE="${PROJECT_ROOT}/infra/compose.rls.yml"
EVIDENCE_COMPOSE_FILE="${PROJECT_ROOT}/infra/evidence/compose.evidence-security.yml"
PILOT_COMPOSE_FILE="${PROJECT_ROOT}/infra/pilot/compose.pilot.yml"
PREFLIGHT_SCRIPT="${PROJECT_ROOT}/scripts/preflight_pilot_runtime.py"

fail() {
  print -u2 -- "CSight pilot control: $1"
  exit 2
}

require_project() {
  local required
  for required in \
    "${CORE_COMPOSE_FILE}" \
    "${RLS_COMPOSE_FILE}" \
    "${EVIDENCE_COMPOSE_FILE}" \
    "${PILOT_COMPOSE_FILE}" \
    "${PREFLIGHT_SCRIPT}"; do
    [[ -f "${required}" ]] || fail "required pilot file is missing"
  done
  [[ -f "${PILOT_ENV_FILE}" ]] || fail "copy .env.pilot.example to .env.pilot first"
}

resolve_binary() {
  local name="$1"
  local resolved
  resolved="$(command -v "${name}" 2>/dev/null || true)"
  [[ -n "${resolved}" ]] || fail "${name} is not installed"
  print -r -- "${resolved}"
}

run_clean() {
  local -a clean_environment
  clean_environment=(env -i "PATH=${PATH}" "HOME=${HOME}")
  [[ -n "${DOCKER_CONFIG:-}" ]] && clean_environment+=("DOCKER_CONFIG=${DOCKER_CONFIG}")
  [[ -n "${DOCKER_HOST:-}" ]] && clean_environment+=("DOCKER_HOST=${DOCKER_HOST}")
  [[ -n "${DOCKER_CONTEXT:-}" ]] && clean_environment+=("DOCKER_CONTEXT=${DOCKER_CONTEXT}")
  [[ -n "${XDG_RUNTIME_DIR:-}" ]] && clean_environment+=("XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR}")
  "${clean_environment[@]}" "$@"
}

compose_command() {
  local docker_bin="$1"
  shift
  run_clean \
    "${docker_bin}" compose \
    --env-file "${PILOT_ENV_FILE}" \
    --file "${CORE_COMPOSE_FILE}" \
    --file "${RLS_COMPOSE_FILE}" \
    --file "${EVIDENCE_COMPOSE_FILE}" \
    --file "${PILOT_COMPOSE_FILE}" \
    --profile pilot-maintenance \
    "$@"
}

run_preflight() {
  local uv_bin="$1"
  (
    cd "${PROJECT_ROOT}"
    run_clean "${uv_bin}" run python "${PREFLIGHT_SCRIPT}" --env-file "${PILOT_ENV_FILE}"
  )
}

start_pilot() {
  local uv_bin docker_bin
  uv_bin="$(resolve_binary uv)"
  docker_bin="$(resolve_binary docker)"
  run_preflight "${uv_bin}"
  compose_command "${docker_bin}" up --detach --wait --no-build
  print -- "CSight 제한 운영 파일럿이 준비되었습니다."
}

show_status() {
  local docker_bin
  docker_bin="$(resolve_binary docker)"
  compose_command "${docker_bin}" ps
}

show_config() {
  local docker_bin
  docker_bin="$(resolve_binary docker)"
  compose_command "${docker_bin}" config --quiet
  print -- "Pilot Compose 구성이 유효합니다. 실제 시작 전 preflight도 통과해야 합니다."
}

stop_pilot() {
  local docker_bin
  docker_bin="$(resolve_binary docker)"
  compose_command "${docker_bin}" stop
  print -- "CSight 제한 운영 파일럿을 멈췄습니다. Named Volume은 보존했습니다."
}

require_project

case "${1:-status}" in
  preflight)
    run_preflight "$(resolve_binary uv)"
    ;;
  config)
    show_config
    ;;
  start)
    start_pilot
    ;;
  status)
    show_status
    ;;
  stop)
    stop_pilot
    ;;
  *)
    fail "usage: csight_pilot_control.sh {preflight|config|start|status|stop}"
    ;;
esac
