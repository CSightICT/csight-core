"""Explicitly activate a complete policy index version and retire its predecessor."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import PolicyIndexVersionModel, TenantModel
from app.adapters.persistence.session import create_session_factory, session_scope
from app.bootstrap.settings import Settings
from app.platform.policy_retrieval import PolicyIndexStatus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--tenant", required=True, help="Tenant slug")
    parser.add_argument("--index-name", default="csight_policy_reference")
    parser.add_argument("--index-version", required=True)
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    factory = create_session_factory(get_engine(settings))
    with session_scope(factory) as session:
        tenant_id = session.scalar(
            select(TenantModel.id).where(TenantModel.slug == arguments.tenant)
        )
        if tenant_id is None:
            raise ValueError("tenant does not exist")
        row = session.scalar(
            select(PolicyIndexVersionModel).where(
                PolicyIndexVersionModel.tenant_id == tenant_id,
                PolicyIndexVersionModel.index_name == arguments.index_name,
                PolicyIndexVersionModel.index_version == arguments.index_version,
            )
        )
        if row is None:
            raise ValueError("policy index version does not exist")
        if row.indexed_clause_count != row.expected_clause_count:
            raise ValueError("incomplete policy index cannot be activated")
        now = datetime.now(UTC)
        session.execute(
            update(PolicyIndexVersionModel)
            .where(
                PolicyIndexVersionModel.tenant_id == tenant_id,
                PolicyIndexVersionModel.index_name == arguments.index_name,
                PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
                PolicyIndexVersionModel.id != row.id,
            )
            .values(status=PolicyIndexStatus.RETIRED.value, retired_at=now)
        )
        row.status = PolicyIndexStatus.ACTIVE.value
        row.activated_at = now
    print(
        "POLICY_INDEX_ACTIVATED "
        f"tenant={arguments.tenant} index={arguments.index_name}:{arguments.index_version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
