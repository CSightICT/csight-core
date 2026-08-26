# Latency Report

Latency values in the metrics JSON are local Apple-silicon Qwen3-Embedding plus PostgreSQL execution
measurements. They are not Qwen3.8 Query Builder latency. RAW and deterministic include all per-query
HYBRID calls and multi-query fusion. External Qwen memory/VRAM and LLM latency are unavailable.
