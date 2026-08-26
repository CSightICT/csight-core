"""Build append-only Qwen clause embeddings and activate one index per tenant."""

from __future__ import annotations

import argparse
import hashlib
import statistics
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select, update

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    PolicyClauseEmbeddingModel,
    PolicyClauseModel,
    PolicyEmbeddingProfileModel,
    PolicyIndexVersionModel,
)
from app.adapters.persistence.policy_repositories import to_policy_clause_record
from app.adapters.persistence.session import create_session_factory, session_scope
from app.adapters.retrieval.embedding_http import HTTPEmbeddingProvider
from app.bootstrap.settings import Settings
from app.platform.policy_retrieval import (
    DenseProfile,
    EmbeddingVector,
    PolicyClauseRecord,
    PolicyIndexStatus,
    serialize_policy_clause,
)

MODEL_ARTIFACT = "Qwen/Qwen3-Embedding-0.6B"
MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QUERY_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"
TEMPLATE_CONTRACT = (
    "문서: {title}\n섹션: {section_path}\n정책 유형: {policy_type}\n"
    "조항 유형: {clause_type}\n본문: {text}"
)
PROFILE_ID = uuid5(NAMESPACE_URL, "urn:csight:policy-embedding-profile:qwen3-0.6b:1.0.0")
INDEX_NAME = "csight_policy_reference"
INDEX_VERSION = "1.0.0"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:8091")
    parser.add_argument("--batch-size", type=int, default=16)
    arguments = parser.parse_args()
    if not 1 <= arguments.batch_size <= 32:
        raise ValueError("batch size must be between 1 and 32")
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    factory = create_session_factory(get_engine(settings))
    profile = DenseProfile(
        model_artifact=MODEL_ARTIFACT,
        model_revision=MODEL_REVISION,
        embedding_dimension=1024,
        pooling_strategy="last-token",
        normalize_embeddings=True,
        query_instruction=QUERY_INSTRUCTION,
        max_query_tokens=8192,
        max_document_tokens=8192,
    )
    with factory() as session:
        clauses = tuple(
            to_policy_clause_record(row)
            for row in session.scalars(
                select(PolicyClauseModel).order_by(
                    PolicyClauseModel.tenant_id,
                    PolicyClauseModel.document_id,
                    PolicyClauseModel.document_version,
                    PolicyClauseModel.clause_id,
                )
            )
        )
        existing_ids = frozenset(
            session.scalars(
                select(PolicyClauseEmbeddingModel.policy_clause_row_id).where(
                    PolicyClauseEmbeddingModel.embedding_profile_id == PROFILE_ID
                )
            )
        )
    pending = tuple(
        clause for clause in clauses if clause.row_id not in {str(i) for i in existing_ids}
    )
    provider = HTTPEmbeddingProvider(base_url=arguments.embedding_base_url, timeout_seconds=180)
    embedded: list[tuple[PolicyClauseRecord, EmbeddingVector, str]] = []
    for offset in range(0, len(pending), arguments.batch_size):
        batch = pending[offset : offset + arguments.batch_size]
        texts = tuple(serialize_policy_clause(clause) for clause in batch)
        vectors = provider.embed_documents(texts, profile)
        embedded.extend(
            (clause, vector, _hash(text))
            for clause, vector, text in zip(batch, vectors, texts, strict=True)
        )
    now = datetime.now(UTC)
    with session_scope(factory) as session:
        stored_profile = session.get(PolicyEmbeddingProfileModel, PROFILE_ID)
        if stored_profile is None:
            session.add(
                PolicyEmbeddingProfileModel(
                    id=PROFILE_ID,
                    profile_name=profile.name,
                    profile_version=profile.version,
                    provider_name=profile.provider_name,
                    model_artifact=profile.model_artifact,
                    model_revision=profile.model_revision,
                    embedding_dimension=profile.embedding_dimension,
                    pooling_strategy=profile.pooling_strategy,
                    normalize_embeddings=profile.normalize_embeddings,
                    query_instruction=profile.query_instruction,
                    query_instruction_hash=_hash(profile.query_instruction),
                    document_template_name=profile.document_template_name,
                    document_template_version=profile.document_template_version,
                    document_template_hash=_hash(TEMPLATE_CONTRACT),
                    max_query_tokens=profile.max_query_tokens,
                    max_document_tokens=profile.max_document_tokens,
                )
            )
        elif (
            stored_profile.model_revision != MODEL_REVISION
            or stored_profile.embedding_dimension != 1024
        ):
            raise ValueError("immutable embedding profile content mismatch")
        session.flush()
        for clause, vector, text_hash in embedded:
            session.add(
                PolicyClauseEmbeddingModel(
                    id=uuid5(
                        NAMESPACE_URL, f"urn:csight:policy-embedding:{clause.row_id}:{PROFILE_ID}"
                    ),
                    tenant_id=UUID(clause.tenant_id),
                    policy_clause_row_id=UUID(clause.row_id),
                    embedding_profile_id=PROFILE_ID,
                    embedding=list(vector.values),
                    embedding_dimension=vector.dimension,
                    document_text_hash=text_hash,
                )
            )
        session.flush()
        tenant_counts = session.execute(
            select(PolicyClauseModel.tenant_id, func.count(PolicyClauseModel.id)).group_by(
                PolicyClauseModel.tenant_id
            )
        ).all()
        for tenant_id, count in tenant_counts:
            index_id = uuid5(
                NAMESPACE_URL,
                f"urn:csight:policy-index:{tenant_id}:{INDEX_NAME}:{INDEX_VERSION}",
            )
            index = session.get(PolicyIndexVersionModel, index_id)
            if index is None:
                index = PolicyIndexVersionModel(
                    id=index_id,
                    tenant_id=tenant_id,
                    index_name=INDEX_NAME,
                    index_version=INDEX_VERSION,
                    corpus_name="csight_synthetic_policy_reference",
                    corpus_version="1.0.0",
                    corpus_source_hash="8e60f4ce869ba83288ac094ba09465481a9d2e431cfe45a7ac4de4114092c237",
                    lexical_profile_name="ko_policy_lexical",
                    lexical_profile_version="1.0.0",
                    lexical_k1=1.2,
                    lexical_b=0.75,
                    embedding_profile_id=PROFILE_ID,
                    fusion_profile_name="policy_rrf",
                    fusion_profile_version="1.0.0",
                    fusion_rrf_k=20,
                    fusion_lexical_weight=1.5,
                    fusion_dense_weight=0.5,
                    status=PolicyIndexStatus.BUILDING.value,
                    expected_clause_count=count,
                    indexed_clause_count=0,
                    activated_at=None,
                    retired_at=None,
                )
                session.add(index)
                session.flush()
            embedded_count = session.scalar(
                select(func.count(PolicyClauseEmbeddingModel.id)).where(
                    PolicyClauseEmbeddingModel.tenant_id == tenant_id,
                    PolicyClauseEmbeddingModel.embedding_profile_id == PROFILE_ID,
                )
            )
            if embedded_count != count:
                raise ValueError("policy index embedding count mismatch")
            session.execute(
                update(PolicyIndexVersionModel)
                .where(
                    PolicyIndexVersionModel.tenant_id == tenant_id,
                    PolicyIndexVersionModel.index_name == INDEX_NAME,
                    PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
                    PolicyIndexVersionModel.id != index_id,
                )
                .values(status=PolicyIndexStatus.RETIRED.value, retired_at=now)
            )
            index.status = PolicyIndexStatus.ACTIVE.value
            index.indexed_clause_count = count
            index.activated_at = now
    token_counts = [vector.token_count or 0 for _, vector, _ in embedded]
    print(
        "POLICY_EMBEDDINGS_BUILT "
        f"total={len(clauses)} reused={len(clauses) - len(pending)} created={len(pending)} "
        f"dimension=1024 truncation_count={sum(vector.truncated for _, vector, _ in embedded)} "
        f"token_min={min(token_counts, default=0)} "
        f"token_p50={statistics.median(token_counts) if token_counts else 0} "
        f"token_max={max(token_counts, default=0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
