#!/usr/bin/env bash
set -euo pipefail

if [[ "${ALLOW_GX10_MUTATION:-}" != "YES" || "${ALLOW_LLAMA_CPP_BUILD:-}" != "YES" ]]; then
  echo "GX10 image build requires both approved mutation gates" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
dockerfile_dir="${GX10_LLAMA_CPP_DOCKERFILE_DIR:-${script_dir}/llama.cpp-gx10}"
source_dir="${1:-}"
image_tag="${2:-}"
devel_image="${LLAMA_CPP_CUDA_DEVEL_IMAGE:-}"
runtime_image="${LLAMA_CPP_CUDA_RUNTIME_IMAGE:-}"
revision="${LLAMA_CPP_REVISION:-}"
build_number="${LLAMA_CPP_BUILD_NUMBER:-}"

if [[ -z "${source_dir}" || ! -d "${source_dir}/.git" || -L "${source_dir}" ]]; then
  echo "first argument must be a regular GX10-local llama.cpp git checkout" >&2
  exit 2
fi
if [[ "${dockerfile_dir}" != /* || ! -d "${dockerfile_dir}" \
  || ! -f "${dockerfile_dir}/Dockerfile" || -L "${dockerfile_dir}" \
  || -L "${dockerfile_dir}/Dockerfile" ]]; then
  echo "GX10 Dockerfile directory must be an absolute regular reviewed directory" >&2
  exit 2
fi
if [[ ! "${devel_image}" =~ @sha256:[0-9a-f]{64}$ \
  || ! "${runtime_image}" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "CUDA build and runtime images must be digest pinned" >&2
  exit 2
fi
if [[ ! "${revision}" =~ ^[0-9a-f]{40}$ \
  || "$(git -C "${source_dir}" rev-parse HEAD)" != "${revision}" ]]; then
  echo "GX10 llama.cpp checkout does not match LLAMA_CPP_REVISION" >&2
  exit 2
fi
if [[ ! "${build_number}" =~ ^[0-9]+$ || -n "$(git -C "${source_dir}" status --porcelain)" ]]; then
  echo "llama.cpp build number must be numeric and checkout must be clean" >&2
  exit 2
fi
if [[ ! "${image_tag}" =~ ^[a-z0-9][a-z0-9./_-]*:[a-zA-Z0-9._-]+$ ]]; then
  echo "second argument must be an explicit local image tag" >&2
  exit 2
fi
if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "GX10 image build is restricted to an aarch64 host" >&2
  exit 2
fi

docker buildx build --load --pull=false --platform=linux/arm64 \
  --build-context "llama_cpp_source=${source_dir}" \
  --build-arg "CUDA_DEVEL_IMAGE=${devel_image}" \
  --build-arg "CUDA_RUNTIME_IMAGE=${runtime_image}" \
  --build-arg "LLAMA_CPP_REVISION=${revision}" \
  --build-arg "LLAMA_CPP_BUILD_NUMBER=${build_number}" \
  --tag "${image_tag}" \
  --file "${dockerfile_dir}/Dockerfile" \
  "${dockerfile_dir}"

echo "GX10_LLAMA_CPP_IMAGE_BUILT_UNQUALIFIED image=${image_tag}"
