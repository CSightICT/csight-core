"""Policy retrieval use case composed exclusively from ports."""

from __future__ import annotations

from time import perf_counter

from app.platform.policy_retrieval import (
    PolicyRetrievalResult,
    PolicySearchQuery,
    RetrievalMode,
)
from app.platform.reranking import (
    PolicyRerankRequest,
    RerankCandidate,
    RerankerProfileUnavailableError,
    serialize_rerank_document,
    validate_rerank_result,
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
from app.ports.reranking import (
    ActivePolicyRetrievalExecutionProfileRepository,
    PolicyReranker,
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
        execution_profiles: ActivePolicyRetrievalExecutionProfileRepository | None = None,
        reranker: PolicyReranker | None = None,
    ) -> None:
        self._clauses = clauses
        self._profiles = profiles
        self._lexical = lexical
        self._embeddings = embeddings
        self._dense = dense
        self._hybrid = hybrid
        self._execution_profiles = execution_profiles
        self._reranker = reranker

    def execute(self, *, principal: Principal, query: PolicySearchQuery) -> PolicyRetrievalResult:
        principal.require(Permission.POLICY_READ)
        if query.tenant_id != principal.tenant_id:
            raise ValueError("query tenant must be the authenticated principal tenant")
        started = perf_counter()
        profile = self._profiles.get_active_profile(principal.tenant_id)
        execution = None
        retrieval_query = query
        if query.mode is RetrievalMode.HYBRID_RERANKED:
            if self._execution_profiles is None or self._reranker is None:
                raise RerankerProfileUnavailableError()
            execution = self._execution_profiles.get_active_execution_profile(
                tenant_id=principal.tenant_id,
                base_index_version=profile.index_version,
            )
            retrieval_query = query.model_copy(
                update={"mode": RetrievalMode.HYBRID, "top_k": execution.candidate_k}
            )
        lexical_hits = ()
        dense_hits = ()
        if query.mode in {
            RetrievalMode.LEXICAL,
            RetrievalMode.HYBRID,
            RetrievalMode.HYBRID_RERANKED,
        }:
            candidates = self._clauses.candidates(retrieval_query)
            lexical_hits = self._lexical.retrieve(
                query=retrieval_query,
                candidates=candidates,
                profile=profile.lexical,
            )
        if query.mode in {
            RetrievalMode.DENSE,
            RetrievalMode.HYBRID,
            RetrievalMode.HYBRID_RERANKED,
        }:
            query_vector = self._embeddings.embed_query(query.query, profile.dense)
            dense_hits = self._dense.retrieve(
                query=retrieval_query,
                query_vector=query_vector,
                embedding_profile_id=profile.embedding_profile_id,
            )
        if query.mode is RetrievalMode.LEXICAL:
            hits = lexical_hits
        elif query.mode is RetrievalMode.DENSE:
            hits = dense_hits
        elif query.mode is RetrievalMode.HYBRID:
            hits = self._hybrid.fuse(
                lexical_hits=lexical_hits,
                dense_hits=dense_hits,
                profile=profile.fusion,
                top_k=query.top_k,
            )
        else:
            assert execution is not None and self._reranker is not None
            candidate_hits = self._hybrid.fuse(
                lexical_hits=lexical_hits,
                dense_hits=dense_hits,
                profile=profile.fusion,
                top_k=execution.candidate_k,
            )
            if not candidate_hits:
                hits = ()
            else:
                rerank_request = PolicyRerankRequest(
                    query=query.query,
                    candidates=tuple(
                        RerankCandidate(
                            candidate_id=hit.clause.clause_id,
                            text=serialize_rerank_document(hit.clause),
                            original_rank=rank,
                        )
                        for rank, hit in enumerate(candidate_hits, start=1)
                    ),
                    profile=execution.reranker,
                )
                rerank_result = self._reranker.rerank(rerank_request)
                scores = validate_rerank_result(request=rerank_request, result=rerank_result)
                by_id = {hit.clause.clause_id: hit for hit in candidate_hits}
                final_count = min(query.top_k, execution.final_k)
                hits = tuple(
                    by_id[value.candidate_id].model_copy(
                        update={
                            "candidate_rank": value.original_rank,
                            "rerank_rank": value.rerank_rank,
                            "rerank_score": value.rerank_score,
                            "reranker_profile": execution.reranker.identifier,
                        }
                    )
                    for value in scores[:final_count]
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
