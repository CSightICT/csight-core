#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$#" -lt 1 ]]; then
  echo "usage: $0 PYTHON_SCRIPT [ARG ...]" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../.." && pwd)"
python_image_id="${CSIGHT_LOCAL_DEV_PYTHON_IMAGE_ID:-}"
docker_bin="$(command -v docker)"
docker_socket="/var/run/docker.sock"

if [[ ! "${python_image_id}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "CSIGHT_LOCAL_DEV_PYTHON_IMAGE_ID must be an exact local image ID" >&2
  exit 2
fi
if [[ -z "${docker_bin}" || "${docker_bin}" != /* || ! -x "${docker_bin}" ]]; then
  echo "an absolute Docker CLI is required" >&2
  exit 2
fi
if [[ ! -S "${docker_socket}" ]]; then
  echo "the Docker socket is unavailable" >&2
  exit 2
fi
if [[ "$("${docker_bin}" image inspect "${python_image_id}" --format '{{.Id}}' 2>/dev/null)" != "${python_image_id}" ]]; then
  echo "the exact local Python image is unavailable" >&2
  exit 2
fi
if [[ "${repo_root}" != /home/user/* || ! -d "${repo_root}" || -L "${repo_root}" ]]; then
  echo "the deployed repository must be a real directory below /home/user" >&2
  exit 2
fi

caller_uid="$(id -u)"
caller_gid="$(id -g)"
socket_gid="$(stat -c '%g' "${docker_socket}")"

exec "${docker_bin}" run --rm --pull=never \
  --network host \
  --gpus all \
  --read-only \
  --pids-limit 256 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --user "${caller_uid}:${caller_gid}" \
  --group-add "${socket_gid}" \
  --env HOME=/nonexistent \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env PYTHONNOUSERSITE=1 \
  --env "PYTHONPATH=${repo_root}" \
  --volume "${docker_socket}:${docker_socket}" \
  --volume "${docker_bin}:/usr/bin/docker:ro" \
  --volume /home/user:/home/user:ro \
  --volume /home/data:/home/data:ro \
  --volume /tmp:/tmp:ro \
  --workdir "${repo_root}" \
  --entrypoint /app/.venv/bin/python \
  "${python_image_id}" \
  "$@"
