from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_llama_cpp_dockerfile_binds_source_identity_and_disables_web_ui() -> None:
    dockerfile = (ROOT / "infra/llm/llama.cpp/Dockerfile").read_text(encoding="utf-8")

    assert '-DLLAMA_BUILD_COMMIT="${LLAMA_CPP_REVISION}"' in dockerfile
    assert '-DLLAMA_BUILD_NUMBER="${LLAMA_CPP_BUILD_NUMBER}"' in dockerfile
    assert "-DLLAMA_BUILD_IS_DEV=OFF" in dockerfile
    assert "-DLLAMA_BUILD_UI=OFF" in dockerfile
    assert "-DLLAMA_USE_PREBUILT_UI=OFF" in dockerfile


def test_llama_cpp_dockerfile_puts_dynamic_backends_beside_the_binaries() -> None:
    dockerfile = (ROOT / "infra/llm/llama.cpp/Dockerfile").read_text(encoding="utf-8")

    assert "build/bin/*.so* /app/" in dockerfile
    assert "ENV LD_LIBRARY_PATH=/app" in dockerfile
    assert "test -e /app/libggml-cuda.so" in dockerfile
    assert "-name 'libggml-cpu*.so*'" in dockerfile
    assert "build/bin/*.so* /usr/local/lib/" not in dockerfile


def test_llama_cpp_build_launcher_requires_numeric_build_and_amd64() -> None:
    launcher = (ROOT / "infra/llm/build_llama_cpp_image.sh").read_text(encoding="utf-8")

    assert 'build_number="${LLAMA_CPP_BUILD_NUMBER:-}"' in launcher
    assert '[[ ! "${build_number}" =~ ^[0-9]+$ ]]' in launcher
    assert '--build-arg "LLAMA_CPP_BUILD_NUMBER=${build_number}"' in launcher
    assert "--platform=linux/amd64" in launcher
