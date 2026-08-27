"""Print the installed Local MLX runtime identity without loading Core services."""

from __future__ import annotations

import importlib.metadata
import json
import os


def main() -> int:
    manifest = {
        "model_family": "Qwen3.5-9B",
        "model_artifact": os.getenv(
            "LOCAL_LLM_MODEL_ARTIFACT", "mlx-community/Qwen3.5-9B-MLX-4bit"
        ),
        "model_revision": os.getenv(
            "LOCAL_LLM_MODEL_REVISION", "938d8919941c6e7efd3c7150eff7fe9d12afa631"
        ),
        "quantization": "MLX_4BIT",
        "runtime": "MLX",
        "runtime_version": importlib.metadata.version("mlx"),
        "server_runtime": f"mlx-vlm=={importlib.metadata.version('mlx-vlm')}",
        "qualification_scope": "LOCAL_POC",
        "served_model_name": "csight-qwen3.5-9b-local-poc",
    }
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
