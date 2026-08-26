# Qwen3-Reranker-0.6B model manifest

- Artifact: `Qwen/Qwen3-Reranker-0.6B`
- Resolved revision: `e61197ed45024b0ed8a2d74b80b4d909f1255473`
- Architecture: `Qwen3ForCausalLM`, 28 layers, hidden size 1024
- Artifact dtype: BF16
- Config maximum positions: 40,960; model card context: 32K
- Qualification pair limit: 2,048
- Runtime: Python 3.12.13, PyTorch 2.13.0, Transformers 5.15.1, Apple MPS
- Official compatibility floor: Transformers 4.51.0; artifact config producer: 4.51.3
- Padding: left
- Special scoring tokens: tokenizer IDs for `no` and `yes`
- Input: official fixed system/user prefix, `<Instruct>/<Query>/<Document>`, fixed assistant suffix
- Truncation policy: reject above the versioned limit; qualification truncation count 0
- Batch size: 8; concurrency limit: 1
- Score: exponentiated two-label log-softmax for `yes`, range `[0,1]`

The score is only relative pairwise relevance. It is not calibrated probability, policy applicability,
approval likelihood, legal suitability or decision confidence.

Primary references:

- https://huggingface.co/Qwen/Qwen3-Reranker-0.6B
- https://github.com/QwenLM/Qwen3-Embedding

Qualification on Mac16,10 / 32 GiB / macOS 26.5.2: download 27.69s, cached load 3.60s,
MPS driver allocation peak observed 5,623,398,400 bytes, pair token min/p50/p95/max
172/178/187/189, truncation 0. CPU fallback was not required.
