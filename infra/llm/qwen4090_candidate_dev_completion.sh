#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  echo "usage: $0 prepare|wait|complete CANDIDATE_ID STATE_DIR [TIMEOUT|STATUS EVIDENCE_DIGEST]" >&2
  exit 2
}

[[ "$#" -ge 3 ]] || usage
mode="$1"
candidate_id="$2"
state_dir="$3"

case "${candidate_id}" in
  qwen38-27b-csight-q4-k-m-llama-cpp|qwen38-27b-csight-q5-k-s-llama-cpp) ;;
  *) echo "candidate is not allowlisted for DEV_LOCAL completion" >&2; exit 2 ;;
esac

if [[ "${state_dir}" != /* || -L "${state_dir}" ]]; then
  echo "completion state directory must be an absolute non-symlink path" >&2
  exit 2
fi

file_identity() {
  local path="$1" metadata
  if metadata="$(stat -c '%u:%a' "${path}" 2>/dev/null)"; then
    printf '%s\n' "${metadata}"
    return 0
  fi
  stat -f '%u:%Lp' "${path}" 2>/dev/null
}

private_directory() {
  [[ -d "$1" && ! -L "$1" && "$(file_identity "$1")" == "$(id -u):700" ]]
}

private_regular_file() {
  [[ -f "$1" && ! -L "$1" && "$(file_identity "$1")" == "$(id -u):600" ]]
}

request_file="${state_dir}/request.tsv"
completion_file="${state_dir}/completion.tsv"

validate_request() {
  private_directory "${state_dir}" || return 1
  private_regular_file "${request_file}" || return 1
  local schema="" observed_candidate="" key value count=0
  while IFS='=' read -r key value; do
    [[ -n "${key}" && -n "${value}" ]] || return 1
    case "${key}" in
      schema_version) [[ -z "${schema}" ]] || return 1; schema="${value}" ;;
      candidate_id) [[ -z "${observed_candidate}" ]] || return 1; observed_candidate="${value}" ;;
      *) return 1 ;;
    esac
    count="$(( count + 1 ))"
  done <"${request_file}"
  [[ "${count}" -eq 2 \
    && "${schema}" == "qwen4090_candidate_dev_completion_request/1.0.0" \
    && "${observed_candidate}" == "${candidate_id}" ]]
}

validate_completion() {
  private_regular_file "${completion_file}" || return 1
  local schema="" observed_candidate="" status="" digest="" key value count=0
  while IFS='=' read -r key value; do
    [[ -n "${key}" && -n "${value}" ]] || return 1
    case "${key}" in
      schema_version) [[ -z "${schema}" ]] || return 1; schema="${value}" ;;
      candidate_id) [[ -z "${observed_candidate}" ]] || return 1; observed_candidate="${value}" ;;
      status) [[ -z "${status}" ]] || return 1; status="${value}" ;;
      evidence_digest) [[ -z "${digest}" ]] || return 1; digest="${value}" ;;
      *) return 1 ;;
    esac
    count="$(( count + 1 ))"
  done <"${completion_file}"
  [[ "${count}" -eq 4 \
    && "${schema}" == "qwen4090_candidate_dev_completion/1.0.0" \
    && "${observed_candidate}" == "${candidate_id}" \
    && "${status}" =~ ^(COMPLETE|FAILED)$ \
    && "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]] || return 1
  completion_status="${status}"
  completion_digest="${digest}"
}

case "${mode}" in
  prepare)
    [[ "$#" -eq 3 ]] || usage
    parent_dir="$(dirname -- "${state_dir}")"
    private_directory "${parent_dir}" || {
      echo "completion state parent must be caller-owned mode 700" >&2
      exit 2
    }
    [[ ! -e "${state_dir}" ]] || {
      echo "completion state already exists" >&2
      exit 2
    }
    mkdir -m 700 "${state_dir}"
    {
      printf 'schema_version=qwen4090_candidate_dev_completion_request/1.0.0\n'
      printf 'candidate_id=%s\n' "${candidate_id}"
    } >"${request_file}"
    chmod 600 "${request_file}"
    echo "QWEN4090_CANDIDATE_DEV_COMPLETION_PREPARED candidate=${candidate_id}"
    ;;
  wait)
    [[ "$#" -eq 4 ]] || usage
    timeout_seconds="$4"
    [[ "${timeout_seconds}" =~ ^[0-9]+$ \
      && "${timeout_seconds}" -ge 60 \
      && "${timeout_seconds}" -le 43200 ]] || {
      echo "completion timeout must be 60..43200 seconds" >&2
      exit 2
    }
    validate_request || {
      echo "completion request is invalid" >&2
      exit 2
    }
    deadline="$(( $(date +%s) + timeout_seconds ))"
    while [[ "$(date +%s)" -lt "${deadline}" ]]; do
      if [[ -e "${completion_file}" ]]; then
        validate_completion || {
          echo "completion evidence is invalid" >&2
          exit 2
        }
        echo "QWEN4090_CANDIDATE_DEV_COMPLETION_RECEIVED candidate=${candidate_id} status=${completion_status} evidence_digest=${completion_digest}"
        [[ "${completion_status}" == "COMPLETE" ]] && exit 0
        exit 1
      fi
      sleep 2
    done
    echo "candidate Dev completion timed out" >&2
    exit 124
    ;;
  complete)
    [[ "$#" -eq 5 ]] || usage
    status="$4"
    evidence_digest="$5"
    [[ "${status}" =~ ^(COMPLETE|FAILED)$ \
      && "${evidence_digest}" =~ ^sha256:[0-9a-f]{64}$ ]] || {
      echo "completion status or evidence digest is invalid" >&2
      exit 2
    }
    validate_request || {
      echo "completion request is invalid" >&2
      exit 2
    }
    [[ ! -e "${completion_file}" ]] || {
      echo "completion evidence already exists" >&2
      exit 2
    }
    temporary_file="$(mktemp "${state_dir}/completion.XXXXXX")"
    cleanup_temporary() {
      rm -f -- "${temporary_file}"
    }
    trap cleanup_temporary EXIT HUP INT TERM
    {
      printf 'schema_version=qwen4090_candidate_dev_completion/1.0.0\n'
      printf 'candidate_id=%s\n' "${candidate_id}"
      printf 'status=%s\n' "${status}"
      printf 'evidence_digest=%s\n' "${evidence_digest}"
    } >"${temporary_file}"
    chmod 600 "${temporary_file}"
    ln "${temporary_file}" "${completion_file}"
    rm -f -- "${temporary_file}"
    trap - EXIT HUP INT TERM
    echo "QWEN4090_CANDIDATE_DEV_COMPLETION_WRITTEN candidate=${candidate_id} status=${status}"
    ;;
  *) usage ;;
esac
