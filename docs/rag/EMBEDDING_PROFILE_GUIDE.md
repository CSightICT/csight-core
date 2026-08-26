# Embedding Profile Guide

현재 immutable profile은 `qwen3_embedding_0.6b:1.0.0`이다.

- artifact/revision: `Qwen/Qwen3-Embedding-0.6B` /
  `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`
- dimension/pooling/normalization: 1024 / last-token / L2 true
- query instruction: `Given a web search query, retrieve relevant passages that answer the query`
- passage: `policy_clause_passage:1.0.0`
- max query/document tokens: 8192/8192; over-limit 입력은 조용히 truncate하지 않는다.

Passage template은 title, section path, policy/clause type, text만 포함한다. Tenant와 DB row ID를
포함하지 않는다. instruction/template/model 의미가 바뀌면 새 profile version과 embedding/index를
append한다.

```bash
make start-embedding
make health-embedding
make test-external-embedding
make build-policy-embeddings
make list-policy-indexes
make stop-embedding
```

서비스는 loopback/private network 전용이며 access log, raw input log, Core DB 접근이 없다.
