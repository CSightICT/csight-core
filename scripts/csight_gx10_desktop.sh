#!/bin/zsh
# Execute reviewed source over key-only SSH; never copy the application .env.
emulate -L zsh
set -eu
readonly runner="${0:A:h}/csight_gx10_desktop_remote.py"
readonly target="aidi_lab@aidi-lab-asus-gx10-ade1.tailf0a69e.ts.net"
# Verify the key already trusted for this GX10 IP; DNS alone is not identity.
readonly host_key_alias="100.119.134.88"
case "${1:-status}" in
  start|status|stop) ;;
  *) print -u2 -- '지원하지 않는 GX10 작업입니다.'; exit 2 ;;
esac
/usr/bin/ssh -o BatchMode=yes -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no -o StrictHostKeyChecking=yes \
  -o "HostKeyAlias=${host_key_alias}" \
  -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 \
  "${target}" "python3 - '${1:-status}'" < "${runner}"
