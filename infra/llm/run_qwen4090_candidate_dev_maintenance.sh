#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$#" -ne 0 || "${ALLOW_VLM_MAINTENANCE:-}" != "YES" ]]; then
  echo "set ALLOW_VLM_MAINTENANCE=YES for the protected candidate Dev window" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
candidate_id="${CSIGHT_QWEN4090_DEV_CANDIDATE_ID:-}"
runtime_env="${CSIGHT_QWEN4090_DEV_RUNTIME_ENV:-}"
evidence_root="${CSIGHT_QWEN4090_DEV_EVIDENCE_ROOT:-}"
completion_state="${CSIGHT_QWEN4090_DEV_COMPLETION_STATE:-}"
completion_timeout="${CSIGHT_QWEN4090_DEV_COMPLETION_TIMEOUT_SECONDS:-21600}"
maintenance_script="${CSIGHT_QWEN4090_LOCAL_DEV_MAINTENANCE_SCRIPT:-${script_dir}/run_qwen4090_llama_cpp_local_dev_maintenance.sh}"
completion_script="${CSIGHT_QWEN4090_DEV_COMPLETION_SCRIPT:-${script_dir}/qwen4090_candidate_dev_completion.sh}"

case "${candidate_id}" in
  qwen38-27b-csight-q4-k-m-llama-cpp|qwen38-27b-csight-q5-k-s-llama-cpp) ;;
  *) echo "CSIGHT_QWEN4090_DEV_CANDIDATE_ID is not allowlisted" >&2; exit 2 ;;
esac

file_identity() {
  local path="$1" metadata
  if metadata="$(stat -c '%u:%a' "${path}" 2>/dev/null)"; then
    printf '%s\n' "${metadata}"
    return 0
  fi
  stat -f '%u:%Lp' "${path}" 2>/dev/null
}

private_directory() {
  [[ "$1" == /* && -d "$1" && ! -L "$1" \
    && "$(file_identity "$1")" == "$(id -u):700" ]]
}

private_regular_file() {
  [[ "$1" == /* && -f "$1" && ! -L "$1" \
    && "$(file_identity "$1")" == "$(id -u):600" ]]
}

for executable in "${maintenance_script}" "${completion_script}"; do
  if [[ "${executable}" != /* || ! -f "${executable}" || -L "${executable}" \
    || ! -x "${executable}" ]]; then
    echo "candidate Dev maintenance executables must be absolute real executable files" >&2
    exit 2
  fi
done
private_regular_file "${runtime_env}" || {
  echo "CSIGHT_QWEN4090_DEV_RUNTIME_ENV must be an owner-only mode 600 file" >&2
  exit 2
}
private_directory "${evidence_root}" || {
  echo "CSIGHT_QWEN4090_DEV_EVIDENCE_ROOT must be an owner-only mode 700 directory" >&2
  exit 2
}
private_directory "${completion_state}" || {
  echo "CSIGHT_QWEN4090_DEV_COMPLETION_STATE must be an owner-only mode 700 directory" >&2
  exit 2
}
if [[ ! "${completion_timeout}" =~ ^[0-9]+$ \
  || "${completion_timeout}" -lt 60 \
  || "${completion_timeout}" -gt 43200 ]]; then
  echo "CSIGHT_QWEN4090_DEV_COMPLETION_TIMEOUT_SECONDS must be 60..43200" >&2
  exit 2
fi

request_file="${completion_state}/request.tsv"
private_regular_file "${request_file}" || {
  echo "candidate Dev completion request is missing or unsafe" >&2
  exit 2
}
request_schema=""
request_candidate=""
request_extra=""
{
  IFS= read -r request_schema || true
  IFS= read -r request_candidate || true
  if IFS= read -r request_extra; then
    request_extra_present=1
  else
    request_extra_present=0
  fi
} <"${request_file}"
if [[ "${request_schema}" != "schema_version=qwen4090_candidate_dev_completion_request/1.0.0" \
  || "${request_candidate}" != "candidate_id=${candidate_id}" \
  || "${request_extra_present}" -ne 0 ]]; then
  echo "candidate Dev completion request differs from the selected candidate" >&2
  exit 2
fi
if [[ -e "${completion_state}/completion.tsv" ]]; then
  echo "candidate Dev completion state was already consumed" >&2
  exit 2
fi

exec "${maintenance_script}" \
  "${candidate_id}" \
  "${runtime_env}" \
  "${evidence_root}" \
  -- \
  "${completion_script}" wait \
  "${candidate_id}" \
  "${completion_state}" \
  "${completion_timeout}"
