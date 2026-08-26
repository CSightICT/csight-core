"""Explicitly seed local/test users for the two synthetic policy tenants."""

import argparse
from pathlib import Path

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.session import create_session_factory, session_scope
from app.adapters.security import Argon2PasswordHasher
from app.bootstrap.seed import (
    DevelopmentSeedPlan,
    DevelopmentSeedUser,
    development_seed_passwords,
    seed_development_identities,
)
from app.bootstrap.settings import Settings
from app.platform.tenant import Role


def _plan(slug: str, label: str) -> DevelopmentSeedPlan:
    return DevelopmentSeedPlan(
        tenant_slug=slug,
        tenant_name=f"CSight Synthetic Policy {label}",
        users=(
            DevelopmentSeedUser(
                email=f"admin@{slug}.demo", display_name=f"{label} Admin", role=Role.ADMIN
            ),
            DevelopmentSeedUser(
                email=f"reviewer@{slug}.demo",
                display_name=f"{label} Reviewer",
                role=Role.REVIEWER,
            ),
            DevelopmentSeedUser(
                email=f"viewer@{slug}.demo",
                display_name=f"{label} Quality Viewer",
                role=Role.QUALITY_VIEWER,
            ),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    passwords = development_seed_passwords(settings)
    factory = create_session_factory(get_engine(settings))
    with session_scope(factory) as session:
        for plan in (
            _plan("csight-demo-brand", "Brand"),
            _plan("csight-demo-retail", "Retail"),
        ):
            seed_development_identities(
                session=session,
                password_hasher=Argon2PasswordHasher(),
                passwords=passwords,
                plan=plan,
            )
    print("POLICY_DEMO_IDENTITIES_SEEDED tenants=2 users=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
