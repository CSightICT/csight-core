"""Validate persisted policy corpus, embeddings, and active index invariants."""

from __future__ import annotations

import argparse
import json
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
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings
from app.platform.policy_retrieval import PolicyIndexStatus, PolicyIngestionStatus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        tenant_count = session.scalar(
            select(func.count(TenantModel.id)).where(
                TenantModel.slug.in_(("csight-demo-brand", "csight-demo-retail"))
            )
        )
        document_count = session.scalar(select(func.count(PolicyDocumentModel.id)))
        clause_count = session.scalar(select(func.count(PolicyClauseModel.id)))
        embedding_count = session.scalar(select(func.count(PolicyClauseEmbeddingModel.id)))
        active_indexes = session.scalar(
            select(func.count(PolicyIndexVersionModel.id)).where(
                PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value
            )
        )
        successful_runs = session.scalar(
            select(func.count(PolicyIngestionRunModel.id)).where(
                PolicyIngestionRunModel.status == PolicyIngestionStatus.SUCCEEDED.value
            )
        )
        dimension_mismatch = session.scalar(
            select(func.count(PolicyClauseEmbeddingModel.id)).where(
                PolicyClauseEmbeddingModel.embedding_dimension != 1024
            )
        )
        parent = aliased(PolicyClauseModel)
        parent_missing = session.scalar(
            select(func.count(PolicyClauseModel.id))
            .select_from(PolicyClauseModel)
            .where(
                PolicyClauseModel.parent_clause_id.is_not(None),
                ~select(parent.id)
                .where(
                    parent.tenant_id == PolicyClauseModel.tenant_id,
                    parent.clause_id == PolicyClauseModel.parent_clause_id,
                )
                .exists(),
            )
        )
    checks = {
        "tenant_count": tenant_count,
        "document_count": document_count,
        "clause_count": clause_count,
        "embedding_count": embedding_count,
        "active_index_count": active_indexes,
        "successful_ingestion_run_count": successful_runs,
        "embedding_dimension_mismatch": dimension_mismatch,
        "missing_parent_count": parent_missing,
    }
    expected = {
        "tenant_count": 2,
        "document_count": 24,
        "clause_count": 168,
        "embedding_count": 168,
        "active_index_count": 2,
        "embedding_dimension_mismatch": 0,
        "missing_parent_count": 0,
    }
    failures = {key: value for key, value in expected.items() if checks[key] != value}
    checks["status"] = "PASS" if not failures and successful_runs else "FAIL"
    print(json.dumps(checks, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if checks["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
