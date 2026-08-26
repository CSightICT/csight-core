"""SQLAlchemy adapter for ACTIVE policy reranker execution profiles."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    PolicyIndexVersionModel,
    PolicyRerankerProfileModel,
    PolicyRetrievalExecutionProfileModel,
)
from app.platform.reranking import (
    PolicyRerankerProfile,
    PolicyRetrievalExecutionProfile,
    RerankerProfileUnavailableError,
)


class SQLAlchemyPolicyExecutionProfileRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_active_execution_profile(
        self, *, tenant_id: str, base_index_version: str
    ) -> PolicyRetrievalExecutionProfile:
        with self._session_factory() as session:
            row = session.execute(
                select(
                    PolicyRetrievalExecutionProfileModel,
                    PolicyRerankerProfileModel,
                    PolicyIndexVersionModel,
                )
                .join(
                    PolicyRerankerProfileModel,
                    PolicyRerankerProfileModel.id
                    == PolicyRetrievalExecutionProfileModel.reranker_profile_id,
                )
                .join(
                    PolicyIndexVersionModel,
                    PolicyIndexVersionModel.id
                    == PolicyRetrievalExecutionProfileModel.base_index_version_id,
                )
                .where(
                    PolicyIndexVersionModel.tenant_id == UUID(tenant_id),
                    PolicyIndexVersionModel.index_version == base_index_version,
                    PolicyIndexVersionModel.status == "ACTIVE",
                    PolicyRetrievalExecutionProfileModel.status == "ACTIVE",
                )
                .limit(1)
            ).one_or_none()
        if row is None:
            raise RerankerProfileUnavailableError()
        execution, reranker, index = row
        profile = PolicyRerankerProfile(
            profile_name=reranker.profile_name,
            profile_version=reranker.profile_version,
            provider_name=reranker.provider_name,
            model_artifact=reranker.model_artifact,
            model_revision=reranker.model_revision,
            instruction=reranker.instruction,
            instruction_hash=reranker.instruction_hash,
            query_template_name=reranker.query_template_name,
            query_template_version=reranker.query_template_version,
            query_template_hash=reranker.query_template_hash,
            document_template_name=reranker.document_template_name,
            document_template_version=reranker.document_template_version,
            document_template_hash=reranker.document_template_hash,
            max_query_tokens=reranker.max_query_tokens,
            max_document_tokens=reranker.max_document_tokens,
            max_pair_tokens=reranker.max_pair_tokens,
            candidate_k=reranker.candidate_k,
            final_k=reranker.final_k,
            batch_size=reranker.batch_size,
            device=reranker.device,
            score_semantics=reranker.score_semantics,
        )
        return PolicyRetrievalExecutionProfile(
            profile_name=execution.profile_name,
            profile_version=execution.profile_version,
            base_index_version=index.index_version,
            candidate_mode=execution.candidate_mode,
            candidate_k=execution.candidate_k,
            final_k=execution.final_k,
            status=execution.status,
            profile_hash=execution.profile_hash,
            reranker=profile,
        )


__all__ = ["SQLAlchemyPolicyExecutionProfileRepository"]
