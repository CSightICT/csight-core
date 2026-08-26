# Policy Retrieval Architecture

```text
JWT Principal tenant
  → application use case
  → active retrieval profile
  → SQL metadata-filtered clause candidates
      ├─ Exact BM25
      └─ Qwen query embedding → pgvector exact cosine
  → versioned weighted RRF
  → clause-only HTTP response
```

필수 tenant/status/effective interval과 optional allowlist filter는 scoring 전에 적용한다. Lexical은
host model 장애와 무관하다. Dense/Hybrid는 embedding provider 장애 시 자동 mock fallback 없이
`503 EMBEDDING_PROVIDER_UNAVAILABLE`을 반환하고 Core readiness는 유지한다.

Application은 port에만 의존하며 BM25, SQLAlchemy, HTTP provider를 생성하지 않는다. Router에는
scoring이 없다. Search hit는 관련 정책 참조이며 적용·승인·거절 결정이 아니다. API는 vector,
internal row/profile id, raw SQL을 노출하지 않는다.
