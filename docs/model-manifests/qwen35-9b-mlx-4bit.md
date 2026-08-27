# Qwen3.5-9B MLX 4-bit local PoC manifest

| Field | Value |
|---|---|
| Artifact | `mlx-community/Qwen3.5-9B-MLX-4bit` |
| Immutable revision | `938d8919941c6e7efd3c7150eff7fe9d12afa631` |
| Family / quantization | Qwen3.5-9B / MLX 4-bit, group size 64 |
| Runtime | MLX 0.32.2 + mlx-vlm 0.6.17 |
| Device | Apple M4, 32 GB unified memory |
| Context / max output | 4096 / 512 tokens |
| Concurrency | 1 |
| Thinking | disabled |
| Structured output | OpenAI JSON Schema via MLX-VLM llguidance |
| Qualification scope | `LOCAL_POC` |
| Production target | Qwen3.8-27B AWQ INT4, RTX 4090, vLLM |

Downloaded size was about 5.6 GiB (HF dry-run 6.0 GB) in 132.03 seconds. The server must use the immutable snapshot path rather than selecting the first item from `/v1/models`, because mlx-vlm lists all cached Hub models.
