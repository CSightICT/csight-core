"""Opt-in PostgreSQL tests for policy ingestion, filtering, vectors, and indexes."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from alembic import command as alembic_command
from app.adapters.persistence.engine import clear_engine_cache, get_engine
from app.adapters.persistence.models import (
    PolicyClauseEmbeddingModel,
    PolicyClauseModel,
    PolicyEmbeddingProfileModel,
    PolicyIndexVersionModel,
    TenantModel,
)
from app.adapters.persistence.policy_ingestion import (
    ingest_policy_documents,
    ingest_validated_policy_corpus,
)
from app.adapters.persistence.policy_repositories import (
    SQLAlchemyDenseRetriever,
    SQLAlchemyPolicyClauseRepository,
    SQLAlchemyPolicyIndexVersionRepository,
)
from app.adapters.persistence.session import create_session_factory, session_scope
from app.bootstrap.settings import Settings
from app.platform.policy_reference import PolicyDocument
from app.platform.policy_retrieval import (
    EmbeddingVector,
    PolicyDocumentVersionContentMismatchError,
    PolicyIndexStatus,
    PolicyIndexVersion,
    PolicySearchQuery,
    RetrievalMode,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def policy_engine() -> Generator[Engine, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test policy persistence")
    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        pytest.fail("DATABASE_URL is required for policy integration tests")
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    alembic_command.upgrade(config, "head")
    engine = get_engine(settings)
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        ingest_validated_policy_corpus(
            session=session,
            corpus_root=root / "data" / "policy_corpus",
            allow_synthetic_tenant_creation=True,
        )
    try:
        yield engine
    finally:
        clear_engine_cache()


def test_ingestion_is_idempotent_and_persists_expected_graph(policy_engine: Engine) -> None:
    factory = create_session_factory(policy_engine)
    with session_scope(factory) as session:
        result = ingest_validated_policy_corpus(
            session=session,
            corpus_root=Path(__file__).resolve().parents[2] / "data" / "policy_corpus",
            allow_synthetic_tenant_creation=True,
        )
        assert result.reused is True
        assert result.document_count == 24
        assert result.clause_count == 168
        assert session.scalar(select(func.count(PolicyClauseModel.id))) == 168
        assert (
            session.scalar(
                select(func.count(PolicyClauseModel.id)).where(
                    PolicyClauseModel.parent_clause_id.is_not(None)
                )
            )
            == 48
        )


def test_immutable_document_version_content_mismatch_is_blocked(policy_engine: Engine) -> None:
    root = Path(__file__).resolve().parents[2]
    first = PolicyDocument.model_validate_json(
        (root / "data/policy_corpus/normalized/policy_documents_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    changed = first.model_copy(update={"source_hash": "f" * 64})
    with Session(policy_engine) as session:
        tenant_id = session.scalar(
            select(TenantModel.id).where(TenantModel.slug == first.tenant_id)
        )
        run_id = session.scalar(select(PolicyClauseModel.ingestion_run_id).limit(1))
        assert tenant_id is not None and run_id is not None
        with pytest.raises(PolicyDocumentVersionContentMismatchError):
            ingest_policy_documents(
                session,
                run_id=run_id,
                documents=(changed,),
                tenant_ids={first.tenant_id: tenant_id},
            )
        session.rollback()


def test_candidates_are_tenant_status_and_effective_date_filtered(policy_engine: Engine) -> None:
    factory = create_session_factory(policy_engine)
    with factory() as session:
        tenants = {
            slug: str(identifier)
            for identifier, slug in session.execute(
                select(TenantModel.id, TenantModel.slug).where(
                    TenantModel.slug.in_(("csight-demo-brand", "csight-demo-retail"))
                )
            )
        }
    repository = SQLAlchemyPolicyClauseRepository(factory)
    query = PolicySearchQuery(
        tenant_id=tenants["csight-demo-brand"],
        query="교환 조건",
        as_of_date=date(2026, 2, 1),
        mode=RetrievalMode.LEXICAL,
    )
    candidates = repository.candidates(query)
    assert candidates
    assert {item.tenant_id for item in candidates} == {tenants["csight-demo-brand"]}
    assert all(item.document_status.value == "ACTIVE" for item in candidates)
    assert all(item.effective_from <= query.as_of_date for item in candidates)


def test_embedding_profile_coexists_and_exact_cosine_semantics(policy_engine: Engine) -> None:
    factory = create_session_factory(policy_engine)
    profile_id = uuid4()
    with session_scope(factory) as session:
        clause = session.scalar(
            select(PolicyClauseModel)
            .where(PolicyClauseModel.document_status == "ACTIVE")
            .order_by(PolicyClauseModel.id)
            .limit(1)
        )
        assert clause is not None
        session.add(
            PolicyEmbeddingProfileModel(
                id=profile_id,
                profile_name=f"integration-{profile_id}",
                profile_version="1.0.0",
                provider_name="fixture",
                model_artifact="fixture",
                model_revision="fixture",
                embedding_dimension=2,
                pooling_strategy="fixture",
                normalize_embeddings=True,
                query_instruction="fixture",
                query_instruction_hash="a" * 64,
                document_template_name="fixture",
                document_template_version="1.0.0",
                document_template_hash="b" * 64,
                max_query_tokens=8,
                max_document_tokens=8,
            )
        )
        session.flush()
        session.add(
            PolicyClauseEmbeddingModel(
                id=uuid4(),
                tenant_id=clause.tenant_id,
                policy_clause_row_id=clause.id,
                embedding_profile_id=profile_id,
                embedding=[1.0, 0.0],
                embedding_dimension=2,
                document_text_hash="c" * 64,
            )
        )
        tenant_id = str(clause.tenant_id)
        expected_clause = clause.clause_id
    retriever = SQLAlchemyDenseRetriever(factory)
    hits = retriever.retrieve(
        query=PolicySearchQuery(
            tenant_id=tenant_id,
            query="fixture query",
            as_of_date=date(2026, 2, 1),
            mode=RetrievalMode.DENSE,
        ),
        query_vector=EmbeddingVector(
            values=(1.0, 0.0), model="fixture", model_revision="fixture", normalized=True
        ),
        embedding_profile_id=str(profile_id),
    )
    assert hits[0].clause.clause_id == expected_clause
    assert hits[0].dense_score == pytest.approx(1.0)
    with policy_engine.begin() as connection:
        connection.execute(
            delete(PolicyClauseEmbeddingModel).where(
                PolicyClauseEmbeddingModel.embedding_profile_id == profile_id
            )
        )
        connection.execute(
            delete(PolicyEmbeddingProfileModel).where(PolicyEmbeddingProfileModel.id == profile_id)
        )


def test_index_activation_retires_existing_active_version(policy_engine: Engine) -> None:
    factory = create_session_factory(policy_engine)
    profile_id = uuid4()
    index_name = f"integration-{uuid4()}"
    first_id, second_id = uuid4(), uuid4()
    with session_scope(factory) as session:
        tenant_id = session.scalar(select(TenantModel.id).limit(1))
        assert tenant_id is not None
        session.add(
            PolicyEmbeddingProfileModel(
                id=profile_id,
                profile_name=f"integration-index-{profile_id}",
                profile_version="1.0.0",
                provider_name="fixture",
                model_artifact="fixture",
                model_revision="fixture",
                embedding_dimension=2,
                pooling_strategy="fixture",
                normalize_embeddings=True,
                query_instruction="fixture",
                query_instruction_hash="d" * 64,
                document_template_name="fixture",
                document_template_version="1.0.0",
                document_template_hash="e" * 64,
                max_query_tokens=8,
                max_document_tokens=8,
            )
        )
        for identifier, version, status in (
            (first_id, "1.0.0", PolicyIndexStatus.ACTIVE.value),
            (second_id, "2.0.0", PolicyIndexStatus.BUILDING.value),
        ):
            session.add(
                PolicyIndexVersionModel(
                    id=identifier,
                    tenant_id=tenant_id,
                    index_name=index_name,
                    index_version=version,
                    corpus_name="fixture",
                    corpus_version="1.0.0",
                    corpus_source_hash="f" * 64,
                    lexical_profile_name="fixture",
                    lexical_profile_version="1.0.0",
                    lexical_k1=1.2,
                    lexical_b=0.75,
                    embedding_profile_id=profile_id,
                    fusion_profile_name="fixture",
                    fusion_profile_version="1.0.0",
                    fusion_rrf_k=20,
                    fusion_lexical_weight=1.0,
                    fusion_dense_weight=1.0,
                    status=status,
                    expected_clause_count=1,
                    indexed_clause_count=1,
                    activated_at=datetime.now(UTC) if status == "ACTIVE" else None,
                )
            )
    with session_scope(factory) as session:
        SQLAlchemyPolicyIndexVersionRepository(session).activate(
            PolicyIndexVersion(
                id=str(second_id),
                tenant_id=str(tenant_id),
                index_name=index_name,
                index_version="2.0.0",
                status=PolicyIndexStatus.ACTIVE,
                embedding_profile_id=str(profile_id),
                expected_clause_count=1,
                indexed_clause_count=1,
                activated_at=datetime.now(UTC),
            )
        )
    with Session(policy_engine) as session:
        assert session.get(PolicyIndexVersionModel, first_id).status == "RETIRED"  # type: ignore[union-attr]
        assert session.get(PolicyIndexVersionModel, second_id).status == "ACTIVE"  # type: ignore[union-attr]
    with policy_engine.begin() as connection:
        connection.execute(
            delete(PolicyIndexVersionModel).where(PolicyIndexVersionModel.index_name == index_name)
        )
        connection.execute(
            delete(PolicyEmbeddingProfileModel).where(PolicyEmbeddingProfileModel.id == profile_id)
        )
