# Qwen3-Embedding-0.6B Qualification Manifest

- 판정: `QWEN3_EMBEDDING_QUALIFIED`
- 측정일: 2026-08-26, Asia/Seoul
- Artifact: `Qwen/Qwen3-Embedding-0.6B`
- Resolved revision: `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`
- Dimension: 1024
- Pooling: last-token
- Normalization: L2 true
- Maximum model sequence length: 32,768; CSight profile limit: 8,192
- Runtime: Python 3.12.13, PyTorch 2.13.0, sentence-transformers 6.0.0
- Host: Mac mini Apple M4 10-core, unified memory 32 GB, macOS 26.5.2 arm64
- Device: MPS (`is_built=true`, `is_available=true`), CPU fallback 불필요

## 실제 측정

| 항목 | 값 |
|---|---:|
| 최초 model download | 약 38 s |
| cache-hit cold runtime load | 4.669 s |
| 168 clause embedding, batch 16 | 8.882 s |
| Token min / p50 / p95 / max | 89 / 95 / 100 / 102 |
| Truncation | 0 |
| Query embedding p50 / p95 | 39.634 / 47.374 ms |
| MPS allocated | 1,191,553,536 bytes |
| Process peak memory footprint | 1,772,980,072 bytes |

168 vectors 모두 finite, dimension 1024이며 unit norm tolerance 0.5%를 통과했다. 서비스는
loopback에서 concurrency를 lock으로 직렬화한다. Concurrency 2 비교와 장시간 부하는 이번
qualification 범위가 아니다.

Model/card/config 확인 근거는 공식 Qwen Hugging Face model repository와 Qwen embedding example이다.
실행 환경의 상세 JSON은 `evaluation/results/policy_retrieval_v1/embedding_qualification.json`에 있다.
