"""Policy retrieval use case composed exclusively from ports."""

from __future__ import annotations

from time import perf_counter

from app.platform.policy_retrieval import (
    PolicyRetrievalResult,
    PolicySearchQuery,
    RetrievalMode,
)
from app.platform.tenant import Permission, Principal
from app.ports.policy_retrieval import (
    ActivePolicyRetrievalProfileRepository,
    DenseRetriever,
    EmbeddingProvider,
    HybridRetriever,
    LexicalRetriever,
    PolicyClauseSearchRepository,
)


class SearchPolicyClauses:
    """Return ranked reference clauses without policy interpretation or decisions."""

    def __init__(
        self,
        *,
        clauses: PolicyClauseSearchRepository,
        profiles: ActivePolicyRetrievalProfileRepository,
        lexical: LexicalRetriever,
        embeddings: EmbeddingProvider,
        dense: DenseRetriever,
        hybrid: HybridRetriever,
    ) -> None:
        self._clauses = clauses
        self._profiles = profiles
        self._lexical = lexical
        self._embeddings = embeddings
        self._dense = dense
        self._hybrid = hybrid

    def execute(self, *, principal: Principal, query: PolicySearchQuery) -> PolicyRetrievalResult:
        principal.require(Permission.POLICY_READ)
        if query.tenant_id != principal.tenant_id:
            raise ValueError("query tenant must be the authenticated principal tenant")
        started = perf_counter()
        profile = self._profiles.get_active_profile(principal.tenant_id)
        lexical_hits = ()
        dense_hits = ()
        if query.mode in {RetrievalMode.LEXICAL, RetrievalMode.HYBRID}:
            candidates = self._clauses.candidates(query)
            lexical_hits = self._lexical.retrieve(
                query=query,
                candidates=candidates,
                profile=profile.lexical,
            )
        if query.mode in {RetrievalMode.DENSE, RetrievalMode.HYBRID}:
            query_vector = self._embeddings.embed_query(query.query, profile.dense)
            dense_hits = self._dense.retrieve(
                query=query,
                query_vector=query_vector,
                embedding_profile_id=profile.embedding_profile_id,
            )
        if query.mode is RetrievalMode.LEXICAL:
            hits = lexical_hits
        elif query.mode is RetrievalMode.DENSE:
            hits = dense_hits
        else:
            hits = self._hybrid.fuse(
                lexical_hits=lexical_hits,
                dense_hits=dense_hits,
                profile=profile.fusion,
                top_k=query.top_k,
            )
        return PolicyRetrievalResult(
            query_hash=query.query_hash,
            mode=query.mode,
            as_of_date=query.as_of_date,
            retrieval_profile=profile,
            hits=hits,
            latency_ms=(perf_counter() - started) * 1000.0,
        )


__all__ = ["SearchPolicyClauses"]
