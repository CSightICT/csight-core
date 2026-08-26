"""Ports for versioned policy reranking."""

from typing import Protocol

from app.platform.reranking import (
    PolicyRerankRequest,
    PolicyRerankResult,
    PolicyRetrievalExecutionProfile,
)


class PolicyReranker(Protocol):
    def rerank(self, request: PolicyRerankRequest) -> PolicyRerankResult: ...


class ActivePolicyRetrievalExecutionProfileRepository(Protocol):
    def get_active_execution_profile(
        self, *, tenant_id: str, base_index_version: str
    ) -> PolicyRetrievalExecutionProfile: ...


__all__ = ["ActivePolicyRetrievalExecutionProfileRepository", "PolicyReranker"]
