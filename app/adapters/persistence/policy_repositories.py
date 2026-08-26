"""SQLAlchemy repositories for tenant-filtered policy retrieval."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, Select, and_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    PolicyClauseEmbeddingModel,
    PolicyClauseModel,
    PolicyEmbeddingProfileModel,
    PolicyIndexVersionModel,
)
from app.platform.policy_reference import ClauseType, DocumentStatus
from app.platform.policy_retrieval import (
    DenseProfile,
    EmbeddingVector,
    HybridFusionProfile,
    LexicalProfile,
    PolicyClauseRecord,
    PolicyIndexStatus,
    PolicyIndexUnavailableError,
    PolicyIndexVersion,
    PolicyRetrievalProfile,
    PolicySearchHit,
    PolicySearchQuery,
)


class SQLAlchemyPolicyClauseRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def candidates(self, query: PolicySearchQuery) -> tuple[PolicyClauseRecord, ...]:
        factory = self._session_factory
        statement = _filtered_clause_statement(query).order_by(
            PolicyClauseModel.document_id,
            PolicyClauseModel.document_version,
            PolicyClauseModel.clause_id,
        )
        with factory() as session:
            rows = tuple(session.scalars(statement))
        return tuple(to_policy_clause_record(row) for row in rows)


class SQLAlchemyDenseRetriever:
    """Exact pgvector cosine search after mandatory metadata filtering."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def retrieve(
        self,
        *,
        query: PolicySearchQuery,
        query_vector: EmbeddingVector,
        embedding_profile_id: str,
    ) -> tuple[PolicySearchHit, ...]:
        factory = self._session_factory
        with factory() as session:
            distance = PolicyClauseEmbeddingModel.embedding.cosine_distance(
                list(query_vector.values)
            )
            statement = (
                select(PolicyClauseModel, distance.label("distance"))
                .join(
                    PolicyClauseEmbeddingModel,
                    and_(
                        PolicyClauseEmbeddingModel.tenant_id == PolicyClauseModel.tenant_id,
                        PolicyClauseEmbeddingModel.policy_clause_row_id == PolicyClauseModel.id,
                    ),
                )
                .where(
                    PolicyClauseEmbeddingModel.embedding_profile_id == UUID(embedding_profile_id),
                    *_filtered_clause_predicates(query),
                )
                .order_by(distance, PolicyClauseModel.id)
                .limit(query.top_k)
            )
            rows = session.execute(statement).all()
        return tuple(
            PolicySearchHit(
                clause=to_policy_clause_record(clause),
                dense_rank=rank,
                dense_score=1.0 - float(distance_value),
            )
            for rank, (clause, distance_value) in enumerate(rows, start=1)
        )


class SQLAlchemyPolicyProfileRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_active_profile(self, tenant_id: str) -> PolicyRetrievalProfile:
        factory = self._session_factory
        with factory() as session:
            row = session.execute(
                select(PolicyIndexVersionModel, PolicyEmbeddingProfileModel)
                .join(
                    PolicyEmbeddingProfileModel,
                    PolicyEmbeddingProfileModel.id == PolicyIndexVersionModel.embedding_profile_id,
                )
                .where(
                    PolicyIndexVersionModel.tenant_id == UUID(tenant_id),
                    PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
                )
                .order_by(PolicyIndexVersionModel.activated_at.desc(), PolicyIndexVersionModel.id)
                .limit(1)
            ).one_or_none()
        if row is None:
            raise PolicyIndexUnavailableError()
        index, embedding = row
        return PolicyRetrievalProfile(
            lexical=LexicalProfile(
                name=index.lexical_profile_name,
                version=index.lexical_profile_version,
                k1=index.lexical_k1,
                b=index.lexical_b,
            ),
            dense=DenseProfile(
                name=embedding.profile_name,
                version=embedding.profile_version,
                provider_name=embedding.provider_name,
                model_artifact=embedding.model_artifact,
                model_revision=embedding.model_revision,
                embedding_dimension=embedding.embedding_dimension,
                pooling_strategy=embedding.pooling_strategy,
                normalize_embeddings=embedding.normalize_embeddings,
                query_instruction=embedding.query_instruction,
                max_query_tokens=embedding.max_query_tokens,
                max_document_tokens=embedding.max_document_tokens,
                document_template_name=embedding.document_template_name,
                document_template_version=embedding.document_template_version,
            ),
            fusion=HybridFusionProfile(
                name=index.fusion_profile_name,
                version=index.fusion_profile_version,
                rrf_k=index.fusion_rrf_k,
                lexical_weight=index.fusion_lexical_weight,
                dense_weight=index.fusion_dense_weight,
            ),
            embedding_profile_id=str(embedding.id),
            index_version=index.index_version,
        )


class SQLAlchemyPolicyEmbeddingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def missing_clauses(
        self, *, tenant_id: str, embedding_profile_id: str
    ) -> tuple[PolicyClauseRecord, ...]:
        statement = (
            select(PolicyClauseModel)
            .outerjoin(
                PolicyClauseEmbeddingModel,
                and_(
                    PolicyClauseEmbeddingModel.policy_clause_row_id == PolicyClauseModel.id,
                    PolicyClauseEmbeddingModel.embedding_profile_id == UUID(embedding_profile_id),
                ),
            )
            .where(
                PolicyClauseModel.tenant_id == UUID(tenant_id),
                PolicyClauseModel.document_status == DocumentStatus.ACTIVE.value,
                PolicyClauseEmbeddingModel.id.is_(None),
            )
            .order_by(PolicyClauseModel.document_id, PolicyClauseModel.clause_id)
        )
        return tuple(to_policy_clause_record(row) for row in self._session.scalars(statement))

    def add(
        self,
        *,
        clause_row_id: str,
        tenant_id: str,
        embedding_profile_id: str,
        vector: EmbeddingVector,
        document_text_hash: str,
    ) -> None:
        self._session.add(
            PolicyClauseEmbeddingModel(
                id=uuid4(),
                tenant_id=UUID(tenant_id),
                policy_clause_row_id=UUID(clause_row_id),
                embedding_profile_id=UUID(embedding_profile_id),
                embedding=list(vector.values),
                embedding_dimension=vector.dimension,
                document_text_hash=document_text_hash,
            )
        )


class SQLAlchemyPolicyIndexVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def activate(self, version: PolicyIndexVersion) -> None:
        self._session.execute(
            update(PolicyIndexVersionModel)
            .where(
                PolicyIndexVersionModel.tenant_id == UUID(version.tenant_id),
                PolicyIndexVersionModel.index_name == version.index_name,
                PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
                PolicyIndexVersionModel.id != UUID(version.id),
            )
            .values(status=PolicyIndexStatus.RETIRED.value, retired_at=version.activated_at)
        )
        row = self._session.get(PolicyIndexVersionModel, UUID(version.id))
        if row is None:
            raise ValueError("policy index version does not exist")
        row.status = PolicyIndexStatus.ACTIVE.value
        row.indexed_clause_count = version.indexed_clause_count
        row.activated_at = version.activated_at


def _filtered_clause_statement(query: PolicySearchQuery) -> Select[tuple[PolicyClauseModel]]:
    return select(PolicyClauseModel).where(*_filtered_clause_predicates(query))


def _filtered_clause_predicates(query: PolicySearchQuery) -> tuple[ColumnElement[bool], ...]:
    filters = query.filters
    predicates: list[ColumnElement[bool]] = [
        PolicyClauseModel.tenant_id == UUID(query.tenant_id),
        PolicyClauseModel.document_status == DocumentStatus.ACTIVE.value,
        PolicyClauseModel.effective_from <= query.as_of_date,
        (
            PolicyClauseModel.effective_to.is_(None)
            | (PolicyClauseModel.effective_to >= query.as_of_date)
        ),
    ]
    if filters.policy_types:
        predicates.append(PolicyClauseModel.policy_type.in_(filters.policy_types))
    if filters.product_categories:
        predicates.append(
            PolicyClauseModel.product_categories.overlap(list(filters.product_categories))
        )
    if filters.defect_types:
        predicates.append(PolicyClauseModel.defect_types.overlap(list(filters.defect_types)))
    if filters.clause_types:
        predicates.append(
            PolicyClauseModel.clause_type.in_(tuple(value.value for value in filters.clause_types))
        )
    if filters.actions:
        predicates.append(PolicyClauseModel.actions.overlap(list(filters.actions)))
    return tuple(predicates)


def to_policy_clause_record(row: PolicyClauseModel) -> PolicyClauseRecord:
    return PolicyClauseRecord(
        row_id=str(row.id),
        tenant_id=str(row.tenant_id),
        document_id=row.document_id,
        document_version=row.document_version,
        title=row.title,
        clause_id=row.clause_id,
        section_path=tuple(row.section_path),
        clause_type=ClauseType(row.clause_type),
        text=row.text,
        parent_clause_id=row.parent_clause_id,
        policy_type=row.policy_type,
        product_categories=tuple(row.product_categories),
        defect_types=tuple(row.defect_types),
        actions=tuple(row.actions),
        requires_human_review=row.requires_human_review,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        document_status=DocumentStatus(row.document_status),
        source_type=row.source_type,
        source_hash=row.source_hash,
    )


__all__ = [
    "SQLAlchemyDenseRetriever",
    "SQLAlchemyPolicyClauseRepository",
    "SQLAlchemyPolicyEmbeddingRepository",
    "SQLAlchemyPolicyIndexVersionRepository",
    "SQLAlchemyPolicyProfileRepository",
    "to_policy_clause_record",
]
