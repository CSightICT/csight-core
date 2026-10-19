#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "${ALLOW_GX10_MUTATION:-}" != "YES" ]]; then
  echo "Q5 transfer requires ALLOW_GX10_MUTATION=YES after explicit approval" >&2
  exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source_path=/home/data/csight-qwen38-quant-v1/dev-pair-runs/c85eec9b41cc-8d1de26320c4-20260901/gguf/Qwen3.8-27B-CSight-Q5_K_S.gguf
filename=Qwen3.8-27B-CSight-Q5_K_S.gguf
allowed_root=/home/aidi_lab/csight-gx10
incoming=${allowed_root}/.incoming/q5-d709a46e-20260902T004500
partial=${incoming}/${filename}.partial
final_parent=${allowed_root}/models/sha256/d709a46e48db256ac0bb3eee7fb2cdcfd087820eb4701b1af5dda84db41a2219
final=${final_parent}/${filename}
expected_bytes=18679614080
expected_sha=d709a46e48db256ac0bb3eee7fb2cdcfd087820eb4701b1af5dda84db41a2219
ssh_options=(-o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no)
transfer_token="$(openssl rand -hex 32)"
gx10_addr="$(tailscale status --json | jq -r \
  '.Peer | to_entries[] | select(.value.HostName == "gx10-ade1" or .value.DNSName == "gx10-ade1") | .value.TailscaleIPs[0]' \
  | head -n 1)"
khrin_addr="$(ssh "${ssh_options[@]}" Khrin 'tailscale ip -4 | head -n 1')"
test -n "${gx10_addr}" && test -n "${khrin_addr}"

transfer_tmp="$(mktemp -d)"
server_pid=""
stop_server_on_exit() {
  local status="$?"
  trap - EXIT INT TERM
  if [[ -n "${server_pid}" ]]; then
    kill "${server_pid}" >/dev/null 2>&1 || true
  fi
  if (( status != 0 )); then
    echo "Q5_TRANSFER_FAILED_PARTIAL_PRESERVED local_log=${transfer_tmp}" >&2
  fi
  exit "${status}"
}
trap stop_server_on_exit EXIT INT TERM

ssh "${ssh_options[@]}" aidi_lab@gx10-ade1 \
  "python3 - prepare --allowed-root '${allowed_root}' --incoming '${incoming}' --partial '${partial}' --final '${final}' --expected-bytes '${expected_bytes}' --expected-sha256 '${expected_sha}'" \
  <"${repo_root}/scripts/finalize_content_addressed_artifact.py"

ssh "${ssh_options[@]}" Khrin \
  "python3 - --source '${source_path}' --bind-host '${khrin_addr}' --allowed-client '${gx10_addr}' --token '${transfer_token}' --expected-bytes '${expected_bytes}' --expected-sha256 '${expected_sha}'" \
  <"${repo_root}/scripts/serve_one_shot_tailnet_artifact.py" \
  >"${transfer_tmp}/server.log" 2>"${transfer_tmp}/server.err" &
server_pid="$!"

ready=0
for _ in $(seq 1 180); do
  if grep -q '"status":"READY"' "${transfer_tmp}/server.log" 2>/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "${server_pid}" 2>/dev/null; then
    break
  fi
  sleep 1
done
if (( ready != 1 )); then
  echo "Q5_TRANSFER_SERVER_FAILED_BEFORE_READY" >&2
  exit 4
fi
port="$(jq -r 'select(.status == "READY") | .port' "${transfer_tmp}/server.log" | tail -n 1)"
test "${port}" -ge 1024 && test "${port}" -le 65535
echo "Q5_TRANSFER_SERVER_READY"

transfer_url="http://${khrin_addr}:${port}/${transfer_token}/${filename}"
ssh "${ssh_options[@]}" aidi_lab@gx10-ade1 \
  "bash -s -- '${partial}' '${transfer_url}'" \
  <"${repo_root}/scripts/receive_one_shot_artifact.sh"

wait "${server_pid}"
server_pid=""
grep -q '"status":"PASS"' "${transfer_tmp}/server.log"
echo "Q5_TRANSFER_STREAM_PASS"

ssh "${ssh_options[@]}" aidi_lab@gx10-ade1 \
  "python3 - finalize --allowed-root '${allowed_root}' --incoming '${incoming}' --partial '${partial}' --final '${final}' --expected-bytes '${expected_bytes}' --expected-sha256 '${expected_sha}'" \
  <"${repo_root}/scripts/finalize_content_addressed_artifact.py"

trap - EXIT INT TERM
echo "Q5_TRANSFER_FINAL_PASS"
