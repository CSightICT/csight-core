"""Ports for policy corpus persistence, embedding, and retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.platform.policy_reference import PolicyClause, PolicyDocument
from app.platform.policy_retrieval import (
    DenseProfile,
    EmbeddingVector,
    HybridFusionProfile,
    LexicalProfile,
    PolicyClauseRecord,
    PolicyEmbeddingProfile,
    PolicyIndexVersion,
    PolicyIngestionRun,
    PolicyRetrievalProfile,
    PolicySearchHit,
    PolicySearchQuery,
)


class PolicyDocumentRepository(Protocol):
    def ingest_documents(self, *, run_id: str, documents: Sequence[PolicyDocument]) -> int: ...


class PolicyClauseRepository(Protocol):
    def ingest_clauses(self, *, run_id: str, clauses: Sequence[PolicyClause]) -> int: ...

    def candidates(self, query: PolicySearchQuery) -> tuple[PolicyClauseRecord, ...]: ...


class PolicyClauseSearchRepository(Protocol):
    def candidates(self, query: PolicySearchQuery) -> tuple[PolicyClauseRecord, ...]: ...


class PolicyIngestionRunRepository(Protocol):
    def find_succeeded(
        self, *, corpus_source_hash: str, manifest_hash: str, builder_version: str
    ) -> PolicyIngestionRun | None: ...


class PolicyEmbeddingProfileRepository(Protocol):
    def get_active_profile(self, tenant_id: str) -> PolicyRetrievalProfile: ...

    def add(self, profile: PolicyEmbeddingProfile) -> None: ...


class ActivePolicyRetrievalProfileRepository(Protocol):
    def get_active_profile(self, tenant_id: str) -> PolicyRetrievalProfile: ...


class PolicyEmbeddingRepository(Protocol):
    def missing_clauses(
        self, *, tenant_id: str, embedding_profile_id: str
    ) -> tuple[PolicyClauseRecord, ...]: ...

    def add(
        self,
        *,
        clause_row_id: str,
        tenant_id: str,
        embedding_profile_id: str,
        vector: EmbeddingVector,
        document_text_hash: str,
    ) -> None: ...


class PolicyIndexVersionRepository(Protocol):
    def activate(self, version: PolicyIndexVersion) -> None: ...


class LexicalRetriever(Protocol):
    def retrieve(
        self,
        *,
        query: PolicySearchQuery,
        candidates: Sequence[PolicyClauseRecord],
        profile: LexicalProfile,
    ) -> tuple[PolicySearchHit, ...]: ...


class EmbeddingProvider(Protocol):
    def embed_query(self, value: str, profile: DenseProfile) -> EmbeddingVector: ...

    def embed_documents(
        self, values: Sequence[str], profile: DenseProfile
    ) -> tuple[EmbeddingVector, ...]: ...


class DenseRetriever(Protocol):
    def retrieve(
        self,
        *,
        query: PolicySearchQuery,
        query_vector: EmbeddingVector,
        embedding_profile_id: str,
    ) -> tuple[PolicySearchHit, ...]: ...

    def retrieve_least_similar(
        self,
        *,
        query: PolicySearchQuery,
        query_vector: EmbeddingVector,
        embedding_profile_id: str,
    ) -> tuple[PolicySearchHit, ...]: ...

    def retrieve_closest_to_score(
        self,
        *,
        query: PolicySearchQuery,
        query_vector: EmbeddingVector,
        embedding_profile_id: str,
        reference_score: float,
        limit: int,
    ) -> tuple[PolicySearchHit, ...]: ...


class HybridRetriever(Protocol):
    def fuse(
        self,
        *,
        lexical_hits: Sequence[PolicySearchHit],
        dense_hits: Sequence[PolicySearchHit],
        profile: HybridFusionProfile,
        top_k: int,
    ) -> tuple[PolicySearchHit, ...]: ...


__all__ = [
    "ActivePolicyRetrievalProfileRepository",
    "DenseRetriever",
    "EmbeddingProvider",
    "HybridRetriever",
    "LexicalRetriever",
    "PolicyClauseRepository",
    "PolicyClauseSearchRepository",
    "PolicyDocumentRepository",
    "PolicyEmbeddingProfileRepository",
    "PolicyEmbeddingRepository",
    "PolicyIndexVersionRepository",
    "PolicyIngestionRunRepository",
]
