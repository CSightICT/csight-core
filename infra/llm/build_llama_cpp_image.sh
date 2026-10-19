#!/usr/bin/env bash
set -euo pipefail

if [[ "${ALLOW_LLAMA_CPP_BUILD:-}" != "YES" ]]; then
  echo "set ALLOW_LLAMA_CPP_BUILD=YES only for an approved reproducible build" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${1:-}"
image_tag="${2:-}"
devel_image="${LLAMA_CPP_CUDA_DEVEL_IMAGE:-}"
runtime_image="${LLAMA_CPP_CUDA_RUNTIME_IMAGE:-}"
revision="${LLAMA_CPP_REVISION:-}"
build_number="${LLAMA_CPP_BUILD_NUMBER:-}"

if [[ -z "${source_dir}" || ! -d "${source_dir}/.git" || -L "${source_dir}" ]]; then
  echo "first argument must be a regular local llama.cpp git checkout" >&2
  exit 2
fi
if [[ ! "${devel_image}" =~ @sha256:[0-9a-f]{64}$ || ! "${runtime_image}" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "CUDA build and runtime images must be digest pinned" >&2
  exit 2
fi
if [[ ! "${revision}" =~ ^[0-9a-f]{40}$ || "$(git -C "${source_dir}" rev-parse HEAD)" != "${revision}" ]]; then
  echo "local llama.cpp checkout does not match LLAMA_CPP_REVISION" >&2
  exit 2
fi
if [[ ! "${build_number}" =~ ^[0-9]+$ ]]; then
  echo "LLAMA_CPP_BUILD_NUMBER must be the pinned numeric llama.cpp build number" >&2
  exit 2
fi
if [[ -n "$(git -C "${source_dir}" status --porcelain)" ]]; then
  echo "local llama.cpp checkout must be clean" >&2
  exit 2
fi
if [[ ! "${image_tag}" =~ ^[a-z0-9][a-z0-9./_-]*:[a-zA-Z0-9._-]+$ ]]; then
  echo "second argument must be an explicit local image tag" >&2
  exit 2
fi

docker buildx build --load --pull=false --platform=linux/amd64 \
  --build-context "llama_cpp_source=${source_dir}" \
  --build-arg "CUDA_DEVEL_IMAGE=${devel_image}" \
  --build-arg "CUDA_RUNTIME_IMAGE=${runtime_image}" \
  --build-arg "LLAMA_CPP_REVISION=${revision}" \
  --build-arg "LLAMA_CPP_BUILD_NUMBER=${build_number}" \
  --tag "${image_tag}" \
  --file "${script_dir}/llama.cpp/Dockerfile" \
  "${script_dir}/llama.cpp"

echo "LLAMA_CPP_IMAGE_BUILT_UNQUALIFIED image=${image_tag}"
