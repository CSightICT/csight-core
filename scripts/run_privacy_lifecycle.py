"""Run tenant-scoped privacy lifecycle work; every command defaults to dry-run."""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.identity import SQLAlchemyIdentityRepositoryFactoryAdapter
from app.adapters.persistence.session import create_session_factory
from app.adapters.persistence.tenant_context import tenant_context
from app.bootstrap.privacy_lifecycle import build_privacy_lifecycle_services
from app.bootstrap.settings import Settings
from app.platform.tenant import Principal, Role


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the planned mutations; omission is always a read-only dry-run.",
    )
    parser.add_argument(
        "--confirm-tenant-id",
        help="Required with --execute and must exactly match --tenant-id.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("purge-sensitive")
    reconcile = subparsers.add_parser("reconcile-evidence")
    reconcile.add_argument("--stale-after-minutes", type=int, default=60)
    reconcile.add_argument(
        "--delete-orphan-objects",
        action="store_true",
        help="Permit object deletion in addition to --execute and tenant confirmation.",
    )
    arguments = parser.parse_args()
    if arguments.execute and arguments.confirm_tenant_id != arguments.tenant_id:
        raise SystemExit("--execute requires matching --confirm-tenant-id")
    if not 1 <= arguments.limit <= 5000:
        raise SystemExit("--limit must be between 1 and 5000")

    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    identities = SQLAlchemyIdentityRepositoryFactoryAdapter(
        create_session_factory(get_engine(settings))
    )
    account = identities.get_by_tenant_and_subject(
        tenant_id=arguments.tenant_id,
        subject=arguments.operator_id,
    )
    if account is None or not account.can_authenticate or Role.ADMIN not in account.roles:
        raise SystemExit("an active tenant ADMIN account is required")
    principal = Principal(
        user_id=account.user_id,
        tenant_id=account.tenant_id,
        email=account.email,
        display_name=account.display_name,
        roles=account.roles,
    )

    stale_after = timedelta(minutes=getattr(arguments, "stale_after_minutes", 60))
    if stale_after <= timedelta(0):
        raise SystemExit("--stale-after-minutes must be positive")
    services = build_privacy_lifecycle_services(
        settings,
        evidence_stale_after=stale_after,
    )
    with tenant_context(principal.tenant_id):
        if arguments.operation == "purge-sensitive":
            report = services.purge_sensitive_payloads.execute(
                principal=principal,
                execute=arguments.execute,
                limit=arguments.limit,
            )
        else:
            report = services.reconcile_evidence.execute(
                principal=principal,
                execute=arguments.execute,
                delete_orphan_objects=arguments.delete_orphan_objects,
                limit=arguments.limit,
            )
    print(report.model_dump_json(indent=2))
    return 2 if arguments.execute and (report.blocked_count or report.truncated) else 0


if __name__ == "__main__":
    raise SystemExit(main())
