#!/bin/zsh
# Opt-in local profile; SSH login is key-only. Never log the remote service API key.
emulate -L zsh
set -eu
readonly feedback_root="${0:A:h:h}"
readonly feedback_target="aidi_lab@100.119.134.88"
readonly feedback_socket="${feedback_root}/.csight-feedback-ssh.sock"
typeset -a feedback_ssh
feedback_ssh=(/usr/bin/ssh -o BatchMode=yes -o PasswordAuthentication=no
  -o KbdInteractiveAuthentication=no -o StrictHostKeyChecking=yes
  -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)

case "${1:-}" in
  prepare)
    /bin/zsh "${feedback_root}/scripts/csight_gx10_desktop.sh" start
    if ! "${feedback_ssh[@]}" -S "${feedback_socket}" -O check "${feedback_target}" >/dev/null 2>&1; then
      "${feedback_ssh[@]}" -M -S "${feedback_socket}" -fNT -o ExitOnForwardFailure=yes \
        -L 127.0.0.1:18004:127.0.0.1:18003 "${feedback_target}"
    fi
    if ! /usr/bin/curl -fsS --max-time 3 http://127.0.0.1:8093/health >/dev/null 2>&1; then
      if /usr/bin/screen -ls 2>/dev/null | /usr/bin/grep -q '[.]csight-vision-e3-internal[[:space:]]'; then
        print -- 'E3 모델 로딩을 기다립니다.'
      else
        checkpoint="${VISION_E3_CHECKPOINT_PATH:-/Users/ckdlsxor/Downloads/drive-download-20260827T154132Z-1-001/E3_best_epoch10.pt}"
        [[ -f "${checkpoint}" ]] || { print -u2 -- 'E3 checkpoint를 찾을 수 없습니다.'; exit 1; }
        /usr/bin/screen -dmS csight-vision-e3-internal /usr/bin/env \
          "VISION_E3_CHECKPOINT_PATH=${checkpoint}" /bin/bash \
          "${feedback_root}/infra/vision_e3/serve_vision_e3.sh"
      fi
    fi
    for attempt in {1..90}; do
      if /usr/bin/curl -fsS --max-time 3 http://127.0.0.1:8093/health >/dev/null 2>&1; then
        print -- '실모델 피드백 연결 준비 완료 (SHADOW · 사람 최종 확인 · 모의 실행)'
        exit 0
      fi
      sleep 1
    done
    print -u2 -- 'E3 기동을 확인하지 못했습니다.'; exit 1
    ;;
  stop)
    if "${feedback_ssh[@]}" -S "${feedback_socket}" -O check "${feedback_target}" >/dev/null 2>&1; then
      "${feedback_ssh[@]}" -S "${feedback_socket}" -O exit "${feedback_target}"
    fi
    if /usr/bin/screen -ls 2>/dev/null | /usr/bin/grep -q '[.]csight-vision-e3-internal[[:space:]]'; then
      /usr/bin/screen -S csight-vision-e3-internal -X quit
    fi
    ;;
  compose)
    shift
    docker_bin="$1"
    shift
    # The API key is transferred over verified SSH into the child process environment only.
    # No login password, local secret file, command argument, or report contains its value.
    export CSIGHT_FEEDBACK_LLM_API_KEY="$("${feedback_ssh[@]}" "${feedback_target}" \
      'python3 -c '\''import os, pathlib, stat
p=pathlib.Path("/home/aidi_lab/csight-gx10/runtime/gx10-q5-bench-4k-c1-v2.env")
s=p.lstat()
assert stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o600
values=dict(line.split("=",1) for line in p.read_text().splitlines() if "=" in line and not line.startswith("#"))
key=values["LLM_API_KEY"].strip().strip("\"\x27")
assert key and "\n" not in key
print(key, end="")'\''')"
    [[ -n "${CSIGHT_FEEDBACK_LLM_API_KEY}" ]] || exit 1
    exec "${docker_bin}" compose --env-file "${feedback_root}/.env" \
      -f "${feedback_root}/infra/compose.core.yml" \
      -f "${feedback_root}/infra/compose.internal-feedback.yml" "$@"
    ;;
  *) print -u2 -- 'Usage: csight_internal_feedback.sh prepare|stop|compose'; exit 2 ;;
esac
