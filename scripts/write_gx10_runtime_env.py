from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--gguf-root", required=True, type=Path)
    parser.add_argument("--gguf-filename", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--bind-address", required=True)
    parser.add_argument("--context-per-slot", type=int, choices=(4096, 16384, 32768), default=4096)
    parser.add_argument("--parallel", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--benchmark-requests", type=int, choices=range(2, 17), default=5)
    parser.add_argument("--benchmark-warmup", type=int, choices=range(1, 4), default=1)
    args = parser.parse_args()

    if (
        not args.path.is_absolute()
        or args.path.exists()
        or args.path.is_symlink()
        or not args.path.parent.is_dir()
        or args.path.parent.is_symlink()
        or not args.gguf_root.is_absolute()
        or not args.gguf_root.is_dir()
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_id)
        or not re.fullmatch(r"[a-z0-9][a-z0-9./_-]*:[a-zA-Z0-9._-]+", args.image)
        or not re.fullmatch(r"[A-Za-z0-9._-]+", args.gguf_filename)
        or not re.fullmatch(r"[A-Za-z0-9._-]+", args.model_id)
        or not re.fullmatch(r"[0-9.]+", args.bind_address)
    ):
        return 2
    if args.path.parent.stat().st_uid != os.getuid() or args.path.parent.stat().st_mode & 0o077:
        return 2

    values = {
        "LLAMA_CPP_IMAGE": args.image,
        "LLAMA_CPP_IMAGE_ID": args.image_id,
        "LLAMA_CPP_RUN_UID": str(os.getuid()),
        "LLAMA_CPP_RUN_GID": str(os.getgid()),
        "LLAMA_CPP_GGUF_ROOT": str(args.gguf_root),
        "LLAMA_CPP_GGUF_FILENAME": args.gguf_filename,
        "LLAMA_CPP_CONTEXT_SIZE": str(args.context_per_slot * args.parallel),
        "LLAMA_CPP_CONTEXT_PER_SLOT": str(args.context_per_slot),
        "LLAMA_CPP_PARALLEL": str(args.parallel),
        "LLAMA_CPP_BATCH_SIZE": "512",
        "LLAMA_CPP_UBATCH_SIZE": "128",
        "LLAMA_CPP_GPU_LAYERS": "all",
        "LLAMA_CPP_REASONING": "off",
        "LLAMA_CPP_FLASH_ATTN": "on",
        "LLAMA_CPP_KV_CACHE_TYPE_K": "q8_0",
        "LLAMA_CPP_KV_CACHE_TYPE_V": "q8_0",
        "LLAMA_CPP_PORT": "18002",
        "GX10_BENCHMARK_REQUESTS": str(args.benchmark_requests),
        "GX10_BENCHMARK_WARMUP": str(args.benchmark_warmup),
        "LLM_BIND_ADDRESS": args.bind_address,
        "LLM_MODEL_ID": args.model_id,
        "LLM_API_KEY": secrets.token_hex(32),
    }
    descriptor = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as runtime_env:
        for key, value in values.items():
            runtime_env.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
