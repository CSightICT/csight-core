"""Validate persisted policy corpus, embeddings, and active index invariants."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    PolicyClauseEmbeddingModel,
    PolicyClauseModel,
    PolicyDocumentModel,
    PolicyIndexVersionModel,
    PolicyIngestionRunModel,
    TenantModel,
)
from app.adapters.persistence.policy_repositories import to_policy_clause_record
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings
from app.platform.policy_retrieval import PolicyIndexStatus, PolicyIngestionStatus
from scripts.build_policy_embeddings import (
    REFERENCE_CORPUS_HASH,
    REFERENCE_CORPUS_NAME,
    REFERENCE_CORPUS_VERSION,
    CorpusIndexMetadata,
    embedding_snapshot,
    index_snapshot,
    validate_persisted_embedding_integrity,
    validate_protected_index_state,
)

REFERENCE_TENANTS = ("csight-demo-brand", "csight-demo-retail")
EXPECTED_DOCUMENTS_PER_TENANT = 12
EXPECTED_CLAUSES_PER_TENANT = 84


def _reference_index_is_invalid(row: PolicyIndexVersionModel) -> bool:
    try:
        validate_protected_index_state(
            index_snapshot(row),
            metadata=CorpusIndexMetadata(
                name=REFERENCE_CORPUS_NAME,
                version=REFERENCE_CORPUS_VERSION,
                source_hash=REFERENCE_CORPUS_HASH,
            ),
            expected_clause_count=EXPECTED_CLAUSES_PER_TENANT,
        )
    except ValueError:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        reference_tenants = tuple(
            session.scalars(
                select(TenantModel)
                .where(TenantModel.slug.in_(REFERENCE_TENANTS))
                .order_by(TenantModel.slug)
            )
        )
        tenant_ids = tuple(tenant.id for tenant in reference_tenants)
        tenant_count = len(reference_tenants)
        document_count = session.scalar(
            select(func.count(PolicyDocumentModel.id)).where(
                PolicyDocumentModel.tenant_id.in_(tenant_ids)
            )
        )
        clause_rows = tuple(
            session.scalars(
                select(PolicyClauseModel).where(PolicyClauseModel.tenant_id.in_(tenant_ids))
            )
        )
        clause_count = len(clause_rows)
        embedding_count = session.scalar(
            select(func.count(PolicyClauseEmbeddingModel.id)).where(
                PolicyClauseEmbeddingModel.tenant_id.in_(tenant_ids)
            )
        )
        active_indexes = session.scalar(
            select(func.count(PolicyIndexVersionModel.id)).where(
                PolicyIndexVersionModel.tenant_id.in_(tenant_ids),
                PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
            )
        )
        successful_runs = session.scalar(
            select(func.count(func.distinct(PolicyIngestionRunModel.id)))
            .join(
                PolicyDocumentModel,
                PolicyDocumentModel.ingestion_run_id == PolicyIngestionRunModel.id,
            )
            .where(
                PolicyDocumentModel.tenant_id.in_(tenant_ids),
                PolicyIngestionRunModel.status == PolicyIngestionStatus.SUCCEEDED.value,
            )
        )
        documents_without_successful_run = session.scalar(
            select(func.count(PolicyDocumentModel.id))
            .join(
                PolicyIngestionRunModel,
                PolicyIngestionRunModel.id == PolicyDocumentModel.ingestion_run_id,
            )
            .where(
                PolicyDocumentModel.tenant_id.in_(tenant_ids),
                PolicyIngestionRunModel.status != PolicyIngestionStatus.SUCCEEDED.value,
            )
        )
        dimension_mismatch = session.scalar(
            select(func.count(PolicyClauseEmbeddingModel.id)).where(
                PolicyClauseEmbeddingModel.tenant_id.in_(tenant_ids),
                PolicyClauseEmbeddingModel.embedding_dimension != 1024,
            )
        )
        embedding_rows = tuple(
            session.scalars(
                select(PolicyClauseEmbeddingModel).where(
                    PolicyClauseEmbeddingModel.tenant_id.in_(tenant_ids)
                )
            )
        )
        vector_mismatch = sum(
            len(row.embedding) != 1024
            or any(not math.isfinite(float(value)) for value in row.embedding)
            for row in embedding_rows
        )
        try:
            validate_persisted_embedding_integrity(
                tuple(to_policy_clause_record(row) for row in clause_rows),
                tuple(embedding_snapshot(row) for row in embedding_rows),
                require_complete=True,
            )
        except ValueError:
            embedding_integrity_mismatch = 1
        else:
            embedding_integrity_mismatch = 0
        index_rows = tuple(
            session.scalars(
                select(PolicyIndexVersionModel).where(
                    PolicyIndexVersionModel.tenant_id.in_(tenant_ids)
                )
            )
        )
        invalid_index_state = sum(_reference_index_is_invalid(row) for row in index_rows)
        documents_by_tenant = {
            tenant.slug: (
                session.scalar(
                    select(func.count(PolicyDocumentModel.id)).where(
                        PolicyDocumentModel.tenant_id == tenant.id
                    )
                )
                or 0
            )
            for tenant in reference_tenants
        }
        clauses_by_tenant = {
            tenant.slug: (
                session.scalar(
                    select(func.count(PolicyClauseModel.id)).where(
                        PolicyClauseModel.tenant_id == tenant.id
                    )
                )
                or 0
            )
            for tenant in reference_tenants
        }
        embeddings_by_tenant = {
            tenant.slug: (
                session.scalar(
                    select(func.count(PolicyClauseEmbeddingModel.id)).where(
                        PolicyClauseEmbeddingModel.tenant_id == tenant.id
                    )
                )
                or 0
            )
            for tenant in reference_tenants
        }
        active_indexes_by_tenant = {
            tenant.slug: (
                session.scalar(
                    select(func.count(PolicyIndexVersionModel.id)).where(
                        PolicyIndexVersionModel.tenant_id == tenant.id,
                        PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
                    )
                )
                or 0
            )
            for tenant in reference_tenants
        }
        parent = aliased(PolicyClauseModel)
        parent_missing = session.scalar(
            select(func.count(PolicyClauseModel.id))
            .select_from(PolicyClauseModel)
            .where(
                PolicyClauseModel.tenant_id.in_(tenant_ids),
                PolicyClauseModel.parent_clause_id.is_not(None),
                ~select(parent.id)
                .where(
                    parent.tenant_id == PolicyClauseModel.tenant_id,
                    parent.clause_id == PolicyClauseModel.parent_clause_id,
                )
                .exists(),
            )
        )
    checks: dict[str, object] = {
        "tenant_count": tenant_count,
        "document_count": document_count,
        "clause_count": clause_count,
        "embedding_count": embedding_count,
        "active_index_count": active_indexes,
        "successful_ingestion_run_count": successful_runs,
        "documents_without_successful_ingestion_run": documents_without_successful_run,
        "embedding_dimension_mismatch": dimension_mismatch,
        "embedding_vector_mismatch": vector_mismatch,
        "embedding_integrity_mismatch": embedding_integrity_mismatch,
        "invalid_index_state_count": invalid_index_state,
        "missing_parent_count": parent_missing,
        "documents_by_reference_tenant": documents_by_tenant,
        "clauses_by_reference_tenant": clauses_by_tenant,
        "embeddings_by_reference_tenant": embeddings_by_tenant,
        "active_indexes_by_reference_tenant": active_indexes_by_tenant,
    }
    expected = {
        "tenant_count": 2,
        "document_count": 24,
        "clause_count": 168,
        "embedding_count": 168,
        "active_index_count": 2,
        "documents_without_successful_ingestion_run": 0,
        "embedding_dimension_mismatch": 0,
        "embedding_vector_mismatch": 0,
        "embedding_integrity_mismatch": 0,
        "invalid_index_state_count": 0,
        "missing_parent_count": 0,
    }
    failures = {key: value for key, value in expected.items() if checks[key] != value}
    expected_documents_by_tenant = dict.fromkeys(REFERENCE_TENANTS, EXPECTED_DOCUMENTS_PER_TENANT)
    expected_clauses_by_tenant = dict.fromkeys(REFERENCE_TENANTS, EXPECTED_CLAUSES_PER_TENANT)
    expected_indexes_by_tenant = dict.fromkeys(REFERENCE_TENANTS, 1)
    tenant_scoped_counts_match = (
        documents_by_tenant == expected_documents_by_tenant
        and clauses_by_tenant == expected_clauses_by_tenant
        and embeddings_by_tenant == expected_clauses_by_tenant
        and active_indexes_by_tenant == expected_indexes_by_tenant
    )
    checks["status"] = (
        "PASS" if not failures and successful_runs and tenant_scoped_counts_match else "FAIL"
    )
    print(json.dumps(checks, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if checks["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
