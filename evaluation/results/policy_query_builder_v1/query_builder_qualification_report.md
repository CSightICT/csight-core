# Query Builder Qualification Report

Decision: `BLOCKED_EXTERNAL_LLM`.

RAW was frozen provisionally after Dev because its MRR@10 and nDCG@10 exceeded deterministic while
Recall@10 tied.
The sealed Test was then run once for RAW and deterministic. Real LLM qualification is Skipped because
no approved Qwen3.8 endpoint was configured; Mock success is contract evidence only.

The online baseline therefore remains direct Case text through frozen HYBRID, but the full three-way
qualification cannot close without real LLM results. Deterministic and LLM
strategies exist as explicit asynchronous profiles, never implicit fallback. The reranker remains off.
