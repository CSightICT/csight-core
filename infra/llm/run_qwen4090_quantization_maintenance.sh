#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly EXPECTED_RUNNER_RELATIVE_PATH="scripts/run_qwen38_quantization_plan.py"
readonly DOCKER_IMAGE_ID_PATTERN='^sha256:[0-9a-f]{64}$'

fail() {
  echo "$1" >&2
  exit 2
}

[[ "$#" -eq 0 ]] || fail "quantization maintenance accepts no arguments"
[[ "${ALLOW_QWEN38_QUANTIZATION:-}" == "YES" ]] \
  || fail "set ALLOW_QWEN38_QUANTIZATION=YES for explicit execution"

pythonpath_root="${CSIGHT_QWEN38_QUANTIZATION_PYTHONPATH_ROOT:-}"
dependency_root="${CSIGHT_QWEN38_QUANTIZATION_DEPENDENCY_ROOT:-}"
runner="${CSIGHT_QWEN38_QUANTIZATION_RUNNER:-}"
plan="${CSIGHT_QWEN38_QUANTIZATION_PLAN:-}"
evidence_output="${CSIGHT_QWEN38_QUANTIZATION_EVIDENCE_OUTPUT:-}"
docker_image_id="${CSIGHT_QWEN38_QUANTIZATION_DOCKER_IMAGE_ID:-}"

for command in realpath stat dirname basename id python3; do
  command -v "${command}" >/dev/null 2>&1 \
    || fail "required command is unavailable: ${command}"
done

owner_uid="$(id -u)"

stat_uid_mode() {
  local path="$1" metadata
  if metadata="$(stat -c '%u:%a' "${path}" 2>/dev/null)"; then
    printf '%s\n' "${metadata}"
    return 0
  fi
  stat -f '%u:%Lp' "${path}" 2>/dev/null
}

require_owner_controlled_directory() {
  local label="$1" path="$2" canonical metadata uid mode
  [[ "${path}" == /* && -d "${path}" && ! -L "${path}" ]] \
    || fail "${label} must be an absolute, real directory"
  canonical="$(realpath "${path}")" \
    || fail "${label} cannot be resolved"
  [[ "${canonical}" == "${path}" ]] \
    || fail "${label} must be canonical"
  metadata="$(stat_uid_mode "${path}")" \
    || fail "${label} metadata cannot be read"
  IFS=: read -r uid mode <<<"${metadata}"
  [[ "${uid}" == "${owner_uid}" && "${mode}" =~ ^[0-7]{3,4}$ ]] \
    || fail "${label} must be owned by the executing user"
  (( (8#${mode} & 8#022) == 0 )) \
    || fail "${label} must not be group- or world-writable"
  [[ -r "${path}" && -x "${path}" ]] \
    || fail "${label} must be readable and searchable by its owner"
}

require_owner_controlled_regular_file() {
  local label="$1" path="$2" canonical parent metadata uid mode
  [[ "${path}" == /* && -f "${path}" && ! -L "${path}" ]] \
    || fail "${label} must be an absolute, regular non-symlink file"
  canonical="$(realpath "${path}")" \
    || fail "${label} cannot be resolved"
  [[ "${canonical}" == "${path}" ]] \
    || fail "${label} must be canonical"
  metadata="$(stat_uid_mode "${path}")" \
    || fail "${label} metadata cannot be read"
  IFS=: read -r uid mode <<<"${metadata}"
  [[ "${uid}" == "${owner_uid}" && "${mode}" =~ ^[0-7]{3,4}$ ]] \
    || fail "${label} must be owned by the executing user"
  (( (8#${mode} & 8#022) == 0 )) \
    || fail "${label} must not be group- or world-writable"
  [[ -r "${path}" ]] || fail "${label} must be readable by its owner"
  parent="$(dirname "${path}")"
  require_owner_controlled_directory "${label} parent" "${parent}"
}

require_owner_only_evidence_target() {
  local path="$1" parent name canonical_parent metadata uid mode
  [[ "${path}" == /* ]] \
    || fail "quantization evidence target must be absolute"
  [[ ! -e "${path}" && ! -L "${path}" ]] \
    || fail "refusing to overwrite quantization evidence"
  parent="$(dirname "${path}")"
  name="$(basename "${path}")"
  [[ "${name}" != "." && "${name}" != ".." ]] \
    || fail "quantization evidence target is invalid"
  [[ -d "${parent}" && ! -L "${parent}" ]] \
    || fail "quantization evidence parent must be a real directory"
  canonical_parent="$(realpath "${parent}")" \
    || fail "quantization evidence parent cannot be resolved"
  [[ "${parent}" == "${canonical_parent}" \
    && "${path}" == "${canonical_parent}/${name}" ]] \
    || fail "quantization evidence target must be canonical"
  metadata="$(stat_uid_mode "${parent}")" \
    || fail "quantization evidence parent metadata cannot be read"
  IFS=: read -r uid mode <<<"${metadata}"
  [[ "${uid}" == "${owner_uid}" && "${mode}" == "700" ]] \
    || fail "quantization evidence parent must be owner-only mode 700"
}

require_owner_controlled_directory \
  "CSIGHT_QWEN38_QUANTIZATION_PYTHONPATH_ROOT" "${pythonpath_root}"
require_owner_controlled_directory \
  "CSIGHT_QWEN38_QUANTIZATION_DEPENDENCY_ROOT" "${dependency_root}"
require_owner_controlled_regular_file \
  "pydantic runtime" "${dependency_root}/pydantic/__init__.py"
require_owner_controlled_regular_file \
  "pydantic-core runtime" "${dependency_root}/pydantic_core/__init__.py"
require_owner_controlled_regular_file \
  "CSIGHT_QWEN38_QUANTIZATION_RUNNER" "${runner}"
[[ "${runner}" == "${pythonpath_root}/${EXPECTED_RUNNER_RELATIVE_PATH}" ]] \
  || fail "quantization runner must be the deployed run_qwen38_quantization_plan.py"
require_owner_controlled_regular_file \
  "CSIGHT_QWEN38_QUANTIZATION_PLAN" "${plan}"
require_owner_only_evidence_target "${evidence_output}"
[[ "${docker_image_id}" =~ ${DOCKER_IMAGE_ID_PATTERN} ]] \
  || fail "quantization Docker image must be an exact sha256 image ID"

readonly -a command=(
  python3
  "${runner}"
  --plan
  "${plan}"
  --execute
  --evidence-output
  "${evidence_output}"
  --docker-image-id
  "${docker_image_id}"
)

unset PYTHONHOME PYTHONINSPECT PYTHONSTARTUP PYTHONWARNINGS
PYTHONPATH="${pythonpath_root}:${dependency_root}" \
PYTHONNOUSERSITE=1 \
PYTHONDONTWRITEBYTECODE=1 \
  "${command[@]}"
