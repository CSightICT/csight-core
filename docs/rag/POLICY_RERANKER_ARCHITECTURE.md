# Policy Reranker Architecture

`HYBRID_RERANKED` reuses the frozen `policy_retrieval_v1` BM25, embedding and RRF profile.
Core first applies principal tenant, ACTIVE status, effective date and request allowlisted metadata
filters. It retrieves K=20 candidates, serializes title/section/policy type/clause type/body under
`policy_rerank_pair:1.0.0`, sends only candidate ID and passage text to the private host service,
validates the complete response against the request allowlist, then returns at most 10 hits.

The reranker has no tenant, JWT, case or database knowledge. Unknown, duplicate, missing, non-finite,
out-of-range or rank-invalid results fail closed. Provider failure produces
`503 RERANKER_PROVIDER_UNAVAILABLE`; there is no silent Hybrid fallback. LEXICAL, DENSE and HYBRID
remain independent and Core readiness does not probe the optional reranker.

The private service binds to loopback, disables access logs and uses a single model lock. It never
persists or logs raw query, passage, pair input or score lists. Allowed operational log dimensions
are correlation ID, tenant ID, query hash, candidate/final counts, profile and aggregate latency.

`rerank_score` is the official yes/no-label-normalized pairwise relevance score. It is not a
calibrated probability and has no policy applicability, approval, legal or decision meaning.
