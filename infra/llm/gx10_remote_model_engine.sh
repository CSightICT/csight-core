#!/usr/bin/env bash
set -euo pipefail
umask 077

phase="${1:-}"
gx10_root="${GX10_ROOT:-/home/aidi_lab/csight-gx10}"
run_id="${GX10_RUN_ID:-}"
candidate_id="qwen38-27b-csight-q5-k-s-llama-cpp"
project_name="csight-gx10-qwen38-dev"
service_name="qwen38-llama-cpp"
control_root="${gx10_root}/control"
runtime_env="${GX10_RUNTIME_ENV:-${gx10_root}/runtime/gx10-q5.env}"
compose_file="${GX10_COMPOSE_FILE:-${control_root}/infra/llm/compose.llama-cpp-gx10.yml}"
benchmark_script="${GX10_BENCHMARK_SCRIPT:-${control_root}/scripts/benchmark_gx10_llama_cpp.py}"
expected_model="${gx10_root}/models/sha256/d709a46e48db256ac0bb3eee7fb2cdcfd087820eb4701b1af5dda84db41a2219/Qwen3.8-27B-CSight-Q5_K_S.gguf"
expected_model_bytes=18679614080
expected_model_sha="d709a46e48db256ac0bb3eee7fb2cdcfd087820eb4701b1af5dda84db41a2219"

usage() {
  echo "usage: gx10_remote_model_engine.sh {status|prepare|serve|canary|evaluate|report|stop}" >&2
  exit 2
}

emit_summary() {
  local status="$1" error_code="${2:-}" ttft="${3:-}" latency="${4:-}" decode="${5:-}" digest="${6:-}" peak="${7:-}"
  PHASE="${phase}" STATUS="${status}" ERROR_CODE="${error_code}" TTFT="${ttft}" \
    LATENCY="${latency}" DECODE="${decode}" REPORT_DIGEST="${digest}" PEAK="${peak}" \
    python3 - <<'PY'
import json
import os

def number(name: str):
    value = os.environ.get(name, "")
    return None if not value else float(value)

def integer(name: str):
    value = os.environ.get(name, "")
    return None if not value else int(value)

error = os.environ.get("ERROR_CODE", "")
print(json.dumps({
    "schema": "csight_gx10_run_summary/1.0.0",
    "host": "gx10-ade1",
    "phase": os.environ["PHASE"],
    "candidate_id": "qwen38-27b-csight-q5-k-s-llama-cpp",
    "status": os.environ["STATUS"],
    "ttft_ms_p95": number("TTFT"),
    "latency_ms_p95": number("LATENCY"),
    "decode_tokens_per_second": number("DECODE"),
    "peak_unified_memory_bytes": integer("PEAK"),
    "errors": [] if not error else [error],
    "report_digest": os.environ.get("REPORT_DIGEST") or None,
}, separators=(",", ":"), sort_keys=True))
PY
}

require_mutation_gate() {
  if [[ "${ALLOW_GX10_MUTATION:-}" != "YES" ]]; then
    emit_summary "BLOCKED" "GX10_MUTATION_GATE_REQUIRED"
    exit 2
  fi
}

require_run_id() {
  if [[ ! "${run_id}" =~ ^[0-9]{8}T[0-9]{6}[A-Z0-9_-]{0,32}$ ]]; then
    emit_summary "BLOCKED" "INVALID_OR_MISSING_RUN_ID"
    exit 2
  fi
}

file_mode() {
  local path="$1"
  stat -c '%u:%a' "${path}" 2>/dev/null || stat -f '%u:%Lp' "${path}" 2>/dev/null
}

env_value() {
  local key="$1"
  awk -F= -v wanted="${key}" '$1 == wanted {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 1}' \
    "${runtime_env}"
}

require_runtime_contract() {
  local image image_id run_uid run_gid
  if [[ ! -f "${runtime_env}" || -L "${runtime_env}" \
    || "$(file_mode "${runtime_env}")" != "$(id -u):600" ]]; then
    emit_summary "BLOCKED" "PRIVATE_RUNTIME_ENV_REQUIRED"
    exit 2
  fi
  if [[ ! -f "${compose_file}" || -L "${compose_file}" || ! -f "${expected_model}" ]]; then
    emit_summary "BLOCKED" "GX10_RUNTIME_INPUT_MISSING"
    exit 2
  fi
  if [[ "$(stat -c '%s' "${expected_model}")" != "${expected_model_bytes}" ]]; then
    emit_summary "BLOCKED" "GX10_MODEL_SIZE_MISMATCH"
    exit 2
  fi
  if [[ "$(sha256sum "${expected_model}" | awk '{print $1}')" != "${expected_model_sha}" ]]; then
    emit_summary "BLOCKED" "GX10_MODEL_SHA256_MISMATCH"
    exit 2
  fi
  image="$(env_value LLAMA_CPP_IMAGE)"
  image_id="$(env_value LLAMA_CPP_IMAGE_ID)"
  run_uid="$(env_value LLAMA_CPP_RUN_UID)"
  run_gid="$(env_value LLAMA_CPP_RUN_GID)"
  if [[ ! "${image_id}" =~ ^sha256:[0-9a-f]{64}$ \
    || "$(docker image inspect "${image}" --format '{{.Id}}' 2>/dev/null)" != "${image_id}" ]]; then
    emit_summary "BLOCKED" "GX10_IMAGE_ID_MISMATCH"
    exit 2
  fi
  if [[ "${run_uid}" != "$(id -u)" || "${run_gid}" != "$(id -g)" ]]; then
    emit_summary "BLOCKED" "GX10_RUNTIME_OWNER_MISMATCH"
    exit 2
  fi
}

case "${phase}" in
  status)
    docker_active=false
    model_present=false
    service_running=false
    [[ "$(systemctl is-active docker 2>/dev/null || true)" == "active" ]] && docker_active=true
    [[ -f "${expected_model}" && ! -L "${expected_model}" ]] && model_present=true
    if command -v docker >/dev/null 2>&1 \
      && docker ps --filter "label=com.docker.compose.project=${project_name}" --format '{{.Names}}' \
        | grep -Fxq "${project_name}-${service_name}-1"; then
      service_running=true
    fi
    DOCKER_ACTIVE="${docker_active}" MODEL_PRESENT="${model_present}" SERVICE_RUNNING="${service_running}" \
      python3 - <<'PY'
import json
import os
print(json.dumps({
    "schema": "csight_gx10_status/1.0.0",
    "host": "gx10-ade1",
    "phase": "status",
    "status": "PASS",
    "docker_active": os.environ["DOCKER_ACTIVE"] == "true",
    "model_present": os.environ["MODEL_PRESENT"] == "true",
    "service_running": os.environ["SERVICE_RUNNING"] == "true",
    "changes": 0,
}, separators=(",", ":"), sort_keys=True))
PY
    ;;
  prepare)
    require_mutation_gate
    require_run_id
    if [[ -e "${gx10_root}" && ( ! -d "${gx10_root}" || -L "${gx10_root}" ) ]]; then
      emit_summary "BLOCKED" "GX10_ROOT_UNSAFE"
      exit 2
    fi
    install -d -m 0700 \
      "${gx10_root}" "${gx10_root}/.incoming" "${control_root}" \
      "${gx10_root}/models/sha256" "${gx10_root}/imatrix/sha256" \
      "${gx10_root}/runtime" "${gx10_root}/evidence"
    emit_summary "PASS"
    ;;
  serve)
    require_mutation_gate
    require_run_id
    require_runtime_contract
    if [[ -n "$(docker ps -aq --filter "label=com.docker.compose.project=${project_name}")" ]]; then
      emit_summary "BLOCKED" "STALE_OR_RUNNING_GX10_PROJECT"
      exit 2
    fi
    evidence_dir="${gx10_root}/evidence/${run_id}"
    [[ ! -e "${evidence_dir}" && ! -L "${evidence_dir}" ]] || {
      emit_summary "BLOCKED" "RUN_EVIDENCE_ALREADY_EXISTS"; exit 2;
    }
    install -d -m 0700 "${evidence_dir}"
    startup_log="${evidence_dir}/serve.log"
    container_log="${evidence_dir}/serve-container.log"
    cleanup_failed_start() {
      local status="$?"
      trap - EXIT INT TERM
      if (( status != 0 )); then
        docker compose --project-name "${project_name}" --env-file "${runtime_env}" \
          -f "${compose_file}" logs --no-color --timestamps --tail 200 "${service_name}" \
          >"${container_log}" 2>&1 || true
        chmod 0600 "${container_log}" 2>/dev/null || true
        docker compose --project-name "${project_name}" --env-file "${runtime_env}" \
          -f "${compose_file}" down --remove-orphans >/dev/null 2>&1 || true
      fi
      exit "${status}"
    }
    trap cleanup_failed_start EXIT INT TERM
    docker compose --project-name "${project_name}" --env-file "${runtime_env}" \
      -f "${compose_file}" config --quiet
    if ! docker compose --project-name "${project_name}" --env-file "${runtime_env}" \
      -f "${compose_file}" up --detach --wait "${service_name}" >"${startup_log}" 2>&1; then
      chmod 0600 "${startup_log}"
      emit_summary "FAIL" "GX10_SERVE_START_FAILED"
      exit 1
    fi
    chmod 0600 "${startup_log}"
    trap - EXIT INT TERM
    emit_summary "PASS"
    ;;
  canary|evaluate)
    require_mutation_gate
    require_run_id
    require_runtime_contract
    api_key="$(env_value LLM_API_KEY)"
    bind_address="$(env_value LLM_BIND_ADDRESS)"
    port="$(env_value LLAMA_CPP_PORT 2>/dev/null || printf '18002')"
    model_id="$(env_value LLM_MODEL_ID)"
    [[ -n "${api_key}" && -n "${bind_address}" && "${port}" =~ ^[0-9]{1,5}$ ]] || {
      emit_summary "BLOCKED" "INVALID_RUNTIME_ENDPOINT"; exit 2;
    }
    evidence_dir="${gx10_root}/evidence/${run_id}"
    [[ -d "${evidence_dir}" && ! -L "${evidence_dir}" ]] || {
      emit_summary "BLOCKED" "RUN_EVIDENCE_MISSING"; exit 2;
    }
    response_file="${evidence_dir}/${phase}.json"
    metrics_file="${evidence_dir}/${phase}.metrics"
    [[ ! -e "${response_file}" && ! -e "${metrics_file}" ]] || {
      emit_summary "BLOCKED" "PHASE_EVIDENCE_ALREADY_EXISTS"; exit 2;
    }
    if [[ "${phase}" == "canary" ]]; then
      prompt='Return exactly {"status":"ok"} as JSON.'
      curl --fail --silent --show-error --max-time 180 \
        -H "Authorization: Bearer ${api_key}" -H 'Content-Type: application/json' \
        -o "${response_file}" -w '%{time_starttransfer} %{time_total}\n' \
        --data "$(python3 -c 'import json,sys; print(json.dumps({"model":sys.argv[1],"messages":[{"role":"user","content":sys.argv[2]}],"temperature":0,"max_tokens":32}))' "${model_id}" "${prompt}")" \
        "http://${bind_address}:${port}/v1/chat/completions" >"${metrics_file}"
      chmod 0600 "${response_file}" "${metrics_file}"
      python3 - "${response_file}" "${model_id}" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload.get("model") == sys.argv[2]
assert payload.get("choices") and payload["choices"][0]["message"]["content"]
PY
      read -r ttft_seconds total_seconds <"${metrics_file}"
      ttft_ms="$(python3 -c 'import sys; print(round(float(sys.argv[1])*1000,3))' "${ttft_seconds}")"
      latency_ms="$(python3 -c 'import sys; print(round(float(sys.argv[1])*1000,3))' "${total_seconds}")"
      emit_summary "PASS" "" "${ttft_ms}" "${latency_ms}"
    else
      context_per_slot="$(env_value LLAMA_CPP_CONTEXT_PER_SLOT)"
      configured_total_context="$(env_value LLAMA_CPP_CONTEXT_SIZE)"
      parallel="$(env_value LLAMA_CPP_PARALLEL)"
      benchmark_requests="$(env_value GX10_BENCHMARK_REQUESTS)"
      benchmark_warmup="$(env_value GX10_BENCHMARK_WARMUP)"
      if [[ ! -f "${benchmark_script}" || -L "${benchmark_script}" \
        || ! "${context_per_slot}" =~ ^(4096|16384|32768)$ \
        || ! "${parallel}" =~ ^(1|2|4)$ \
        || ! "${configured_total_context}" =~ ^[0-9]+$ \
        || ! "${benchmark_requests}" =~ ^([2-9]|1[0-6])$ \
        || ! "${benchmark_warmup}" =~ ^[1-3]$ ]]; then
        emit_summary "BLOCKED" "GX10_BENCHMARK_CONTRACT_INVALID"
        exit 2
      fi
      if (( context_per_slot * parallel != configured_total_context )); then
        emit_summary "BLOCKED" "GX10_BENCHMARK_CONTRACT_INVALID"
        exit 2
      fi
      if ! LLM_BASE_URL="http://${bind_address}:${port}" LLM_API_KEY="${api_key}" \
        LLM_MODEL_ID="${model_id}" python3 "${benchmark_script}" \
          --context-per-slot "${context_per_slot}" \
          --configured-total-context "${configured_total_context}" \
          --concurrency "${parallel}" --requests "${benchmark_requests}" \
          --warmup "${benchmark_warmup}" >"${response_file}" 2>"${metrics_file}"; then
        chmod 0600 "${response_file}" "${metrics_file}"
        emit_summary "FAIL" "GX10_BENCHMARK_FAILED"
        exit 1
      fi
      chmod 0600 "${response_file}" "${metrics_file}"
      if ! benchmark_values="$(
        python3 - "${response_file}" "${context_per_slot}" "${parallel}" "${benchmark_requests}" <<'PY'
import json
import sys

try:
    payload = json.load(open(sys.argv[1], encoding="utf-8"))
    valid = (
        payload["schema"] == "csight_gx10_benchmark/1.0.0"
        and payload["context_per_slot_tokens"] == int(sys.argv[2])
        and payload["concurrency"] == int(sys.argv[3])
        and payload["successful_requests"] == int(sys.argv[4])
        and payload["success_rate"] == 1.0
        and payload["schema_validation_failures"] == 0
    )
    values = (
        payload["ttft_ms_p95"],
        payload["latency_ms_p95"],
        payload["decode_tokens_per_second"],
        payload["peak_unified_memory_bytes"],
    )
except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
    raise SystemExit(1)
if not valid or any(value is None for value in values):
    raise SystemExit(1)
print(*values)
PY
      )"; then
        emit_summary "FAIL" "GX10_BENCHMARK_RESULT_INVALID"
        exit 1
      fi
      read -r ttft_ms latency_ms decode_tps peak_memory <<<"${benchmark_values}"
      emit_summary "PASS" "" "${ttft_ms}" "${latency_ms}" "${decode_tps}" "" "${peak_memory}"
    fi
    ;;
  report)
    require_run_id
    evidence_dir="${gx10_root}/evidence/${run_id}"
    [[ -d "${evidence_dir}" && ! -L "${evidence_dir}" ]] || {
      emit_summary "BLOCKED" "RUN_EVIDENCE_MISSING"; exit 2;
    }
    report_digest="sha256:$(find "${evidence_dir}" -maxdepth 1 -type f -print0 \
      | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')"
    emit_summary "PASS" "" "" "" "" "${report_digest}"
    ;;
  stop)
    require_mutation_gate
    require_run_id
    require_runtime_contract
    docker compose --project-name "${project_name}" --env-file "${runtime_env}" \
      -f "${compose_file}" down --remove-orphans >/dev/null
    emit_summary "PASS"
    ;;
  *) usage ;;
esac
