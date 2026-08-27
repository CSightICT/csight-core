# RAW vs Deterministic vs Local MLX Query Builder

Sealed Test comparison on the same frozen HYBRID retriever:

| Metric | RAW | Deterministic | Local MLX |
|---|---:|---:|---:|
| Recall@1 | 0.6000 | 0.6250 | 0.7250 |
| Recall@3 | 0.9250 | 0.7500 | 0.7500 |
| Recall@5 | 0.9250 | 0.8500 | 0.7500 |
| Recall@10 | 0.9750 | 1.0000 | 0.9000 |
| MRR@10 | 0.7392 | 0.7245 | 0.7531 |
| nDCG@10 | 0.7414 | 0.6576 | 0.7227 |
| Exact coverage@10 | 0.8500 | 0.8250 | 0.7500 |

Decision: `RAW_REMAINS_SELECTED`. Local MLX did not improve retrieval consistently.
