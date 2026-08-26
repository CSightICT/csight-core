"""List policy retrieval index versions without exposing embedding vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import PolicyIndexVersionModel, TenantModel
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        rows = session.execute(
            select(PolicyIndexVersionModel, TenantModel.slug)
            .join(TenantModel, TenantModel.id == PolicyIndexVersionModel.tenant_id)
            .order_by(TenantModel.slug, PolicyIndexVersionModel.created_at)
        ).all()
    payload = [
        {
            "tenant": slug,
            "index_name": row.index_name,
            "index_version": row.index_version,
            "status": row.status,
            "indexed_clause_count": row.indexed_clause_count,
            "expected_clause_count": row.expected_clause_count,
            "lexical_profile": f"{row.lexical_profile_name}:{row.lexical_profile_version}",
            "embedding_profile_id": str(row.embedding_profile_id),
            "fusion_profile": f"{row.fusion_profile_name}:{row.fusion_profile_version}",
        }
        for row, slug in rows
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
