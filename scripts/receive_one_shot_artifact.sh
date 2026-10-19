#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$#" -ne 2 ]]; then
  echo "usage: receive_one_shot_artifact.sh PARTIAL_PATH URL" >&2
  exit 2
fi

partial="$1"
url="$2"
if [[ ! "${partial}" =~ ^/home/aidi_lab/csight-gx10/\.incoming/q5-[a-zA-Z0-9_-]+/Qwen3\.8-27B-CSight-Q5_K_S\.gguf\.partial$ ]]; then
  echo "unsafe Q5 partial path" >&2
  exit 2
fi
if [[ ! "${url}" =~ ^http://[0-9.]+:[0-9]+/[0-9a-f]{64}/Qwen3\.8-27B-CSight-Q5_K_S\.gguf$ ]]; then
  echo "unsafe one-shot URL" >&2
  exit 2
fi
if [[ -e "${partial}" || -L "${partial}" ]]; then
  echo "Q5 partial path must be fresh" >&2
  exit 2
fi

curl --fail --silent --show-error --location --max-time 1800 --limit-rate 80M \
  --output "${partial}" \
  --write-out 'HTTP=%{http_code} BYTES=%{size_download} SECONDS=%{time_total} SPEED=%{speed_download}\n' \
  "${url}"
