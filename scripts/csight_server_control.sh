#!/bin/zsh

# Double-clickable macOS controller backend for the local CSight demo stack.
# It deliberately preserves Docker named volumes when stopping.

emulate -L zsh
set -eu

export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

readonly PROJECT_ROOT="${CSIGHT_CONTROL_PROJECT_ROOT:-${0:A:h:h}}"
readonly ENV_FILE="${PROJECT_ROOT}/.env"
readonly COMPOSE_FILE="${PROJECT_ROOT}/infra/compose.core.yml"
readonly CONSOLE_URL="http://127.0.0.1:8080"
readonly API_READY_URL="http://127.0.0.1:8000/health/ready"
readonly WEB_READY_URL="http://127.0.0.1:8080/web-health"
readonly PUBLIC_READY_URL="https://doongdoong.org/web-health"
readonly TUNNEL_LAUNCH_LABEL="com.codex.team-sweeper-tunnel"
readonly TUNNEL_PLIST="${HOME}/Library/LaunchAgents/${TUNNEL_LAUNCH_LABEL}.plist"
readonly USER_GUI_DOMAIN="gui/$(/usr/bin/id -u)"
readonly EMBEDDING_PORT="8091"
readonly EMBEDDING_READY_URL="http://127.0.0.1:${EMBEDDING_PORT}/health"
readonly EMBEDDING_MODELS_URL="http://127.0.0.1:${EMBEDDING_PORT}/v1/models"
readonly EMBEDDING_PID_FILE="${PROJECT_ROOT}/.embedding-service.pid"
readonly EMBEDDING_LOG_FILE="${PROJECT_ROOT}/.embedding-service.log"
readonly EMBEDDING_UVICORN="${PROJECT_ROOT}/.venv-embedding/bin/uvicorn"
readonly EMBEDDING_RUNNER="${PROJECT_ROOT}/scripts/csight_embedding_runtime.sh"
readonly EMBEDDING_SCREEN_SESSION="csight-embedding"
readonly GX10_RUNNER="${PROJECT_ROOT}/scripts/csight_gx10_desktop.sh"

gx10_action() {
  /bin/zsh "${GX10_RUNNER}" "$1"
}

fail() {
  print -u2 -- "$1"
  exit 1
}

require_project() {
  [[ -f "${ENV_FILE}" ]] || fail "${ENV_FILE} 파일이 없습니다. 프로젝트 설정을 먼저 확인해 주세요."
  [[ -f "${COMPOSE_FILE}" ]] || fail "Docker Compose 설정을 찾을 수 없습니다."
  [[ -x "${EMBEDDING_UVICORN}" ]] || fail "정책 검색 엔진 실행 환경을 찾을 수 없습니다: ${EMBEDDING_UVICORN}"
  [[ -x "${EMBEDDING_RUNNER}" ]] || fail "정책 검색 엔진 시작 파일을 찾을 수 없습니다: ${EMBEDDING_RUNNER}"
  [[ -x /usr/bin/screen ]] || fail "macOS 기본 screen 실행 파일을 찾을 수 없습니다."
  [[ -f "${TUNNEL_PLIST}" ]] || fail "공개 시연 주소 실행 설정을 찾을 수 없습니다: ${TUNNEL_PLIST}"
}

find_docker() {
  command -v docker 2>/dev/null || fail "Docker가 설치되어 있지 않습니다. Docker Desktop을 설치해 주세요."
}

docker_is_ready() {
  local docker_bin="$1"
  "${docker_bin}" info >/dev/null 2>&1
}

ensure_docker() {
  local docker_bin="$1"
  if docker_is_ready "${docker_bin}"; then
    return
  fi

  /usr/bin/open -a Docker >/dev/null 2>&1 || fail "Docker Desktop을 열 수 없습니다."
  local attempt
  for attempt in {1..60}; do
    if docker_is_ready "${docker_bin}"; then
      return
    fi
    sleep 2
  done
  fail "Docker Desktop이 2분 안에 준비되지 않았습니다. Docker 상태를 확인한 뒤 다시 시도해 주세요."
}

compose_command() {
  local docker_bin="$1"
  shift
  if [[ -f "${PROJECT_ROOT}/.csight-internal-feedback" ]]; then
    /bin/zsh "${PROJECT_ROOT}/scripts/csight_internal_feedback.sh" compose "${docker_bin}" "$@"
    return
  fi
  "${docker_bin}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

embedding_is_ready() {
  /usr/bin/curl -fsS --max-time 3 "${EMBEDDING_READY_URL}" >/dev/null 2>&1 \
    && /usr/bin/curl -fsS --max-time 3 "${EMBEDDING_MODELS_URL}" >/dev/null 2>&1
}

public_route_is_ready() {
  /usr/bin/curl -fsS --max-time 5 "${PUBLIC_READY_URL}" >/dev/null 2>&1
}

tunnel_job_is_loaded() {
  /bin/launchctl print "${USER_GUI_DOMAIN}/${TUNNEL_LAUNCH_LABEL}" >/dev/null 2>&1
}

ensure_public_tunnel() {
  if public_route_is_ready; then
    print -- "공개 시연 주소: 이미 정상"
    return
  fi

  print -- "공개 시연 주소를 연결합니다."
  if tunnel_job_is_loaded; then
    /bin/launchctl kickstart -k "${USER_GUI_DOMAIN}/${TUNNEL_LAUNCH_LABEL}" \
      || fail "공개 시연 주소 연결을 다시 시작하지 못했습니다."
  else
    /bin/launchctl bootstrap "${USER_GUI_DOMAIN}" "${TUNNEL_PLIST}" \
      || fail "공개 시연 주소 연결을 시작하지 못했습니다."
  fi

  local attempt
  for attempt in {1..45}; do
    if public_route_is_ready; then
      print -- "공개 시연 주소: 정상"
      return
    fi
    sleep 1
  done
  fail "공개 시연 주소가 45초 안에 준비되지 않았습니다. 로컬 서버는 실행 중입니다."
}

stop_public_tunnel() {
  if tunnel_job_is_loaded; then
    /bin/launchctl bootout "${USER_GUI_DOMAIN}/${TUNNEL_LAUNCH_LABEL}"
    print -- "공개 시연 주소 연결을 껐습니다."
  else
    print -- "공개 시연 주소: 이미 정지됨"
  fi
}

embedding_screen_session_exists() {
  /usr/bin/screen -ls 2>/dev/null \
    | /usr/bin/grep -q "[.]${EMBEDDING_SCREEN_SESSION}[[:space:]]"
}

legacy_managed_embedding_pid() {
  [[ -f "${EMBEDDING_PID_FILE}" ]] || return 1
  local pid
  pid="$(/usr/bin/tr -d '[:space:]' < "${EMBEDDING_PID_FILE}")"
  case "${pid}" in
    ''|*[!0-9]*) return 1 ;;
  esac
  kill -0 "${pid}" >/dev/null 2>&1 || return 1
  local command_line
  command_line="$(/bin/ps -p "${pid}" -o command= 2>/dev/null || true)"
  [[ "${command_line}" == *"infra.embedding.server:app"* ]] || return 1
  print -- "${pid}"
}

start_embedding_if_needed() {
  if embedding_is_ready; then
    print -- "정책 검색 엔진: 이미 정상"
    return
  fi

  local pid=""
  if embedding_screen_session_exists; then
    print -- "정책 검색 엔진의 모델 로딩을 기다립니다."
  elif pid="$(legacy_managed_embedding_pid)"; then
    print -- "정책 검색 엔진의 모델 로딩을 기다립니다."
  else
    /bin/rm -f "${EMBEDDING_PID_FILE}"
    print -- "정책 검색 엔진을 시작합니다. 첫 시작은 모델 로딩에 시간이 걸릴 수 있습니다."
    /usr/bin/screen -dmS "${EMBEDDING_SCREEN_SESSION}" "${EMBEDDING_RUNNER}" \
      || fail "정책 검색 엔진을 시작하지 못했습니다. ${EMBEDDING_LOG_FILE}을 확인해 주세요."
  fi

  local attempt
  for attempt in {1..180}; do
    if embedding_is_ready; then
      print -- "정책 검색 엔진: 정상"
      return
    fi
    if ! embedding_screen_session_exists && ! legacy_managed_embedding_pid >/dev/null; then
      fail "정책 검색 엔진이 모델 로딩 중 종료됐습니다. ${EMBEDDING_LOG_FILE}을 확인해 주세요."
    fi
    sleep 1
  done
  fail "정책 검색 엔진이 3분 안에 준비되지 않았습니다. ${EMBEDDING_LOG_FILE}을 확인해 주세요."
}

stop_managed_embedding() {
  if embedding_screen_session_exists; then
    /usr/bin/screen -S "${EMBEDDING_SCREEN_SESSION}" -X quit
    sleep 1
    stop_managed_embedding
    return
  fi

  local pid=""
  if pid="$(legacy_managed_embedding_pid)"; then
    kill -TERM "${pid}"
    local attempt
    for attempt in {1..20}; do
      if ! kill -0 "${pid}" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    if kill -0 "${pid}" >/dev/null 2>&1; then
      fail "정책 검색 엔진이 20초 안에 종료되지 않았습니다. 강제 종료하지 않았습니다."
    fi
    /bin/rm -f "${EMBEDDING_PID_FILE}"
    print -- "정책 검색 엔진을 껐습니다."
    return
  fi

  /bin/rm -f "${EMBEDDING_PID_FILE}"
  if embedding_is_ready; then
    print -- "정책 검색 엔진은 이 앱이 시작한 프로세스가 아니어서 종료하지 않았습니다."
  else
    print -- "정책 검색 엔진: 이미 정지됨"
  fi
}

health_summary() {
  local docker_bin="$1"
  local services
  services="$(compose_command "${docker_bin}" ps --services --filter status=running 2>/dev/null || true)"
  local service_count=0
  if [[ -n "${services}" ]]; then
    service_count="$(print -r -- "${services}" | /usr/bin/awk 'NF { count += 1 } END { print count + 0 }')"
  fi

  local api_status="응답 없음"
  local web_status="응답 없음"
  local embedding_status="응답 없음"
  local public_status="응답 없음"
  if /usr/bin/curl -fsS --max-time 3 "${API_READY_URL}" >/dev/null 2>&1; then
    api_status="정상"
  fi
  if /usr/bin/curl -fsS --max-time 3 "${WEB_READY_URL}" >/dev/null 2>&1; then
    web_status="정상"
  fi
  if embedding_is_ready; then
    embedding_status="정상"
  fi
  if public_route_is_ready; then
    public_status="정상"
  fi

  print -- "Docker Desktop: 실행 중"
  print -- "실행 중인 CSight 서비스: ${service_count}개"
  print -- "API 상태: ${api_status}"
  print -- "상담원 화면: ${web_status}"
  print -- "정책 검색 엔진: ${embedding_status}"
  print -- "공개 시연 주소: ${public_status}"
  if [[ -f "${PROJECT_ROOT}/.csight-internal-feedback" ]]; then
    print -- "실모델 피드백: GX10 Q5 + E3 / SHADOW / 사람 최종 확인 / 모의 실행"
  else
    print -- "GX10 Q5 내부 검증 엔진 (Core 설정·운영 전환 없음)"
  fi
  gx10_action status || print -- "GX10 엔진: 응답 없음 또는 기동 조건 미충족 (Core 상태와 별개)"
  if [[ -n "${services}" ]]; then
    print -- ""
    print -- "실행 서비스"
    print -r -- "${services}"
  fi
}

start_quick() {
  local docker_bin="$1"
  start_embedding_if_needed
  if [[ -f "${PROJECT_ROOT}/.csight-internal-feedback" ]]; then
    /bin/zsh "${PROJECT_ROOT}/scripts/csight_internal_feedback.sh" prepare
  fi
  compose_command "${docker_bin}" up --detach --wait --remove-orphans
  ensure_public_tunnel
  if [[ ! -f "${PROJECT_ROOT}/.csight-internal-feedback" ]]; then
    gx10_action start || fail "Core 서버는 켜졌지만 GX10 내부 엔진은 준비되지 않았습니다. 다른 GPU 작업은 종료하지 않았습니다."
  fi
  print -- "CSight 전체 PoC 서버를 켰습니다."
  print -- ""
  health_summary "${docker_bin}"
}

start_rebuilt() {
  local docker_bin="$1"
  start_embedding_if_needed
  if [[ -f "${PROJECT_ROOT}/.csight-internal-feedback" ]]; then
    /bin/zsh "${PROJECT_ROOT}/scripts/csight_internal_feedback.sh" prepare
  fi
  compose_command "${docker_bin}" build
  compose_command "${docker_bin}" up --detach postgres rabbitmq minio
  compose_command "${docker_bin}" run --rm migrator
  compose_command "${docker_bin}" up --detach --wait --remove-orphans
  ensure_public_tunnel
  if [[ ! -f "${PROJECT_ROOT}/.csight-internal-feedback" ]]; then
    gx10_action start || fail "Core 서버는 켜졌지만 GX10 내부 엔진은 준비되지 않았습니다. 다른 GPU 작업은 종료하지 않았습니다."
  fi
  print -- "최신 코드와 DB 마이그레이션을 반영해 CSight 전체 PoC 서버를 켰습니다."
  print -- ""
  health_summary "${docker_bin}"
}

stop_preserving_data() {
  local docker_bin="$1"
  gx10_action stop || fail "GX10 전용 엔진 정지를 확인하지 못했습니다. 나머지 서버는 유지합니다."
  stop_public_tunnel
  if docker_is_ready "${docker_bin}"; then
    compose_command "${docker_bin}" stop
    print -- "Docker Core 서비스를 껐습니다."
  else
    print -- "Docker Desktop이 꺼져 있어 Core 서비스는 이미 정지된 상태입니다."
  fi
  stop_managed_embedding
  if [[ -f "${PROJECT_ROOT}/.csight-internal-feedback" ]]; then
    /bin/zsh "${PROJECT_ROOT}/scripts/csight_internal_feedback.sh" stop
  fi
  print -- "CSight 전체 PoC 서버를 껐습니다."
  print -- "DB와 업로드 파일이 들어 있는 Docker 볼륨은 그대로 보존했습니다."
}

show_status() {
  local docker_bin="$1"
  if ! docker_is_ready "${docker_bin}"; then
    print -- "Docker Desktop: 꺼짐"
    if embedding_is_ready; then
      print -- "정책 검색 엔진: 정상"
    else
      print -- "정책 검색 엔진: 응답 없음"
    fi
    print -- "CSight Core 서버: 정지됨"
    gx10_action status || print -- "GX10 엔진: 응답 없음 또는 정지됨"
    if public_route_is_ready; then
      print -- "공개 시연 주소: 정상"
    else
      print -- "공개 시연 주소: 응답 없음"
    fi
    return
  fi
  health_summary "${docker_bin}"
}

main() {
  require_project
  local docker_bin
  docker_bin="$(find_docker)"

  case "${1:-status}" in
    start)
      ensure_docker "${docker_bin}"
      start_quick "${docker_bin}"
      ;;
    rebuild)
      ensure_docker "${docker_bin}"
      start_rebuilt "${docker_bin}"
      ;;
    stop)
      stop_preserving_data "${docker_bin}"
      ;;
    status)
      show_status "${docker_bin}"
      ;;
    open)
      /usr/bin/open "${CONSOLE_URL}"
      print -- "상담원 화면을 열었습니다."
      ;;
    *)
      fail "사용법: ${0:t} {start|rebuild|stop|status|open}"
      ;;
  esac
}

main "$@"
