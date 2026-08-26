"""Sprint 4B policy retrieval composition root."""

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.policy_repositories import (
    SQLAlchemyDenseRetriever,
    SQLAlchemyPolicyClauseRepository,
    SQLAlchemyPolicyProfileRepository,
)
from app.adapters.persistence.reranker_profiles import SQLAlchemyPolicyExecutionProfileRepository
from app.adapters.persistence.session import create_session_factory
from app.adapters.reranking import RemoteQwenRerankerAdapter
from app.adapters.retrieval import (
    ExactBM25Retriever,
    HTTPEmbeddingProvider,
    ReciprocalRankFusionRetriever,
)
from app.application.policy_retrieval import SearchPolicyClauses
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint4BServiceContainer


def sprint4b_is_configured(settings: Settings) -> bool:
    return bool(settings.database_url_value and settings.embedding_base_url is not None)


def build_sprint4b_services(settings: Settings) -> Sprint4BServiceContainer:
    if settings.embedding_base_url is None:
        raise ValueError("EMBEDDING_BASE_URL is required for Sprint 4B composition")
    factory = create_session_factory(get_engine(settings))
    reranker = (
        RemoteQwenRerankerAdapter(
            base_url=str(settings.reranker_base_url).rstrip("/"),
            timeout_seconds=settings.reranker_timeout_seconds,
        )
        if settings.reranker_base_url is not None
        else None
    )
    return Sprint4BServiceContainer(
        search_policy_clauses=SearchPolicyClauses(
            clauses=SQLAlchemyPolicyClauseRepository(factory),
            profiles=SQLAlchemyPolicyProfileRepository(factory),
            lexical=ExactBM25Retriever(),
            embeddings=HTTPEmbeddingProvider(
                base_url=str(settings.embedding_base_url).rstrip("/"),
                timeout_seconds=settings.embedding_timeout_seconds,
            ),
            dense=SQLAlchemyDenseRetriever(factory),
            hybrid=ReciprocalRankFusionRetriever(),
            execution_profiles=SQLAlchemyPolicyExecutionProfileRepository(factory),
            reranker=reranker,
        )
    )


__all__ = ["build_sprint4b_services", "sprint4b_is_configured"]
