# syntax=docker/dockerfile:1.7
ARG CUDA_DEVEL_IMAGE
ARG CUDA_RUNTIME_IMAGE

FROM ${CUDA_DEVEL_IMAGE} AS build
ARG LLAMA_CPP_REVISION
ARG LLAMA_CPP_BUILD_NUMBER
COPY --from=llama_cpp_source . /src/llama.cpp
WORKDIR /src/llama.cpp
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
      build-essential ca-certificates cmake \
    && rm -rf /var/lib/apt/lists/* \
    && test -n "${LLAMA_CPP_REVISION}" \
    && test -n "${LLAMA_CPP_BUILD_NUMBER}" \
    && cmake -S . -B build \
      -DGGML_CUDA=ON \
      -DGGML_NATIVE=OFF \
      -DGGML_BACKEND_DL=ON \
      -DGGML_CPU_ALL_VARIANTS=OFF \
      -DCMAKE_CUDA_ARCHITECTURES=121 \
      -DCMAKE_BUILD_TYPE=Release \
      -DLLAMA_BUILD_IS_DEV=OFF \
      -DLLAMA_BUILD_COMMIT="${LLAMA_CPP_REVISION}" \
      -DLLAMA_BUILD_NUMBER="${LLAMA_CPP_BUILD_NUMBER}" \
      -DLLAMA_CURL=OFF \
      -DLLAMA_BUILD_TESTS=OFF \
      -DLLAMA_BUILD_EXAMPLES=ON \
      -DLLAMA_BUILD_UI=OFF \
      -DLLAMA_USE_PREBUILT_UI=OFF \
    && cmake --build build --config Release \
      --target llama-server llama-quantize llama-imatrix llama-tokenize -j2

FROM ${CUDA_RUNTIME_IMAGE} AS runtime
ARG LLAMA_CPP_REVISION
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 llama \
    && install -d --owner=10001 --group=10001 --mode=0755 /app
COPY --from=build /src/llama.cpp/build/bin/llama-server /app/llama-server
COPY --from=build /src/llama.cpp/build/bin/llama-quantize /app/llama-quantize
COPY --from=build /src/llama.cpp/build/bin/llama-imatrix /app/llama-imatrix
COPY --from=build /src/llama.cpp/build/bin/llama-tokenize /app/llama-tokenize
COPY --from=build /src/llama.cpp/build/bin/*.so* /app/
ENV LD_LIBRARY_PATH=/app
RUN ldconfig \
    && test -e /app/libggml-cuda.so \
    && find /app -maxdepth 1 -type f -name 'libggml-cpu*.so*' -print -quit | grep -q . \
    && for binary in llama-server llama-quantize llama-imatrix llama-tokenize; do \
      ldd "/app/${binary}" | tee "/tmp/${binary}.ldd"; \
      ! grep -F "not found" "/tmp/${binary}.ldd"; \
    done \
    && /app/llama-server --version \
    && /app/llama-imatrix --version \
    && /app/llama-tokenize --version \
    && /app/llama-quantize --help 2>&1 | grep -F "usage: /app/llama-quantize"
LABEL org.opencontainers.image.source="https://github.com/ggml-org/llama.cpp" \
      org.opencontainers.image.revision="${LLAMA_CPP_REVISION}" \
      org.csight.execution-scope="GX10_CANARY_DEV_ONLY" \
      org.csight.primary-allowed="false"
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/llama-server"]
