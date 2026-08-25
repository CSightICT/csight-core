"""Explicit, idempotent identity seed command for local and test environments."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import SecretStr
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    RoleModel,
    TenantModel,
    UserModel,
    UserRoleModel,
)
from app.adapters.persistence.session import create_session_factory, session_scope
from app.adapters.security import Argon2PasswordHasher
from app.bootstrap.settings import Settings
from app.platform.tenant import Role
from app.ports.security import PasswordHasher

_ALLOWED_ENVIRONMENTS = frozenset({"local", "test"})


class SeedConfigurationError(RuntimeError):
    """Raised before database access when explicit seed safeguards are not met."""


class SeedDataConflictError(RuntimeError):
    """Raised when natural-key seed rows cannot be resolved after an upsert."""


@dataclass(frozen=True, slots=True)
class DevelopmentSeedUser:
    email: str
    display_name: str
    role: Role


@dataclass(frozen=True, slots=True)
class DevelopmentSeedPlan:
    tenant_slug: str
    tenant_name: str
    users: tuple[DevelopmentSeedUser, ...]


@dataclass(frozen=True, slots=True)
class DevelopmentSeedPasswords:
    admin: SecretStr = field(repr=False)
    reviewer: SecretStr = field(repr=False)
    quality_viewer: SecretStr = field(repr=False)

    def for_role(self, role: Role) -> SecretStr:
        return {
            Role.ADMIN: self.admin,
            Role.REVIEWER: self.reviewer,
            Role.QUALITY_VIEWER: self.quality_viewer,
        }[role]


@dataclass(frozen=True, slots=True)
class DevelopmentSeedResult:
    tenant_id: UUID
    user_ids: tuple[UUID, ...]


DEFAULT_DEVELOPMENT_SEED_PLAN = DevelopmentSeedPlan(
    tenant_slug="csight-demo",
    tenant_name="CSight Demo",
    users=(
        DevelopmentSeedUser(
            email="admin@csight.demo",
            display_name="Demo Admin",
            role=Role.ADMIN,
        ),
        DevelopmentSeedUser(
            email="reviewer@csight.demo",
            display_name="Demo Reviewer",
            role=Role.REVIEWER,
        ),
        DevelopmentSeedUser(
            email="viewer@csight.demo",
            display_name="Demo Quality Viewer",
            role=Role.QUALITY_VIEWER,
        ),
    ),
)


def development_seed_passwords(settings: Settings) -> DevelopmentSeedPasswords:
    """Validate environment guards and return redacted seed password values."""

    environment = settings.environment.strip().lower()
    if environment not in _ALLOWED_ENVIRONMENTS:
        raise SeedConfigurationError("development seed is allowed only in local or test")
    if not settings.development_seed_enabled:
        raise SeedConfigurationError("DEVELOPMENT_SEED_ENABLED=true is required")
    if not settings.database_url_value:
        raise SeedConfigurationError("DATABASE_URL is required")

    password_fields = {
        "DEVELOPMENT_SEED_ADMIN_PASSWORD": settings.development_seed_admin_password,
        "DEVELOPMENT_SEED_REVIEWER_PASSWORD": settings.development_seed_reviewer_password,
        "DEVELOPMENT_SEED_QUALITY_VIEWER_PASSWORD": (
            settings.development_seed_quality_viewer_password
        ),
    }
    for name, password in password_fields.items():
        if password is None or len(password.get_secret_value()) < 12:
            raise SeedConfigurationError(f"{name} must contain at least 12 characters")

    admin = settings.development_seed_admin_password
    reviewer = settings.development_seed_reviewer_password
    quality_viewer = settings.development_seed_quality_viewer_password
    if admin is None or reviewer is None or quality_viewer is None:
        raise AssertionError("validated seed passwords unexpectedly missing")
    return DevelopmentSeedPasswords(
        admin=admin,
        reviewer=reviewer,
        quality_viewer=quality_viewer,
    )


def seed_development_identities(
    *,
    session: Session,
    password_hasher: PasswordHasher,
    passwords: DevelopmentSeedPasswords,
    plan: DevelopmentSeedPlan = DEFAULT_DEVELOPMENT_SEED_PLAN,
) -> DevelopmentSeedResult:
    """Upsert one synthetic tenant, all roles, and three role-specific users."""

    _validate_plan(plan)
    tenant_id = _ensure_tenant(session, plan)
    role_ids = {role: _ensure_role(session, role) for role in Role}
    user_ids: list[UUID] = []
    for user in plan.users:
        user_id = _ensure_user(
            session=session,
            tenant_id=tenant_id,
            tenant_slug=plan.tenant_slug,
            user=user,
            password_hasher=password_hasher,
            password=passwords.for_role(user.role),
        )
        _ensure_user_role(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=role_ids[user.role],
        )
        user_ids.append(user_id)
    session.flush()
    return DevelopmentSeedResult(tenant_id=tenant_id, user_ids=tuple(user_ids))


def run_development_seed(settings: Settings) -> DevelopmentSeedResult:
    """Run the guarded seed within one commit-or-rollback transaction."""

    passwords = development_seed_passwords(settings)
    factory = create_session_factory(get_engine(settings))
    with session_scope(factory) as session:
        return seed_development_identities(
            session=session,
            password_hasher=Argon2PasswordHasher(),
            passwords=passwords,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed local/test CSight identities")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
        result = run_development_seed(settings)
    except (PydanticValidationError, SeedConfigurationError) as error:
        del error
        print("Development seed refused: configuration safeguards were not met.", file=sys.stderr)
        return 2
    except (SQLAlchemyError, SeedDataConflictError):
        print("Development seed failed during its database transaction.", file=sys.stderr)
        return 1

    print(
        "Development seed completed "
        f"for tenant {DEFAULT_DEVELOPMENT_SEED_PLAN.tenant_slug} "
        f"({len(result.user_ids)} users, {len(Role)} roles)."
    )
    return 0


def _validate_plan(plan: DevelopmentSeedPlan) -> None:
    if not plan.tenant_slug or plan.tenant_slug != plan.tenant_slug.strip().lower():
        raise SeedConfigurationError("seed tenant slug must be non-empty lowercase text")
    if not plan.tenant_name.strip():
        raise SeedConfigurationError("seed tenant name must not be blank")
    expected_roles = frozenset(Role)
    actual_roles = frozenset(user.role for user in plan.users)
    if len(plan.users) != len(expected_roles) or actual_roles != expected_roles:
        raise SeedConfigurationError("seed plan must contain exactly one user for every role")
    emails = tuple(user.email.strip().lower() for user in plan.users)
    if any(
        not email or email != user.email for email, user in zip(emails, plan.users, strict=True)
    ):
        raise SeedConfigurationError("seed emails must be non-empty lowercase text")
    if len(emails) != len(set(emails)):
        raise SeedConfigurationError("seed emails must be unique")


def _stable_uuid(kind: str, natural_key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"urn:csight:development-seed:{kind}:{natural_key}")


def _ensure_tenant(session: Session, plan: DevelopmentSeedPlan) -> UUID:
    desired_id = _stable_uuid("tenant", plan.tenant_slug)
    statement = (
        postgresql_insert(TenantModel)
        .values(
            id=desired_id,
            slug=plan.tenant_slug,
            name=plan.tenant_name,
            is_active=True,
        )
        .on_conflict_do_nothing(index_elements=[TenantModel.slug])
    )
    session.execute(statement)
    tenant_id = session.scalar(select(TenantModel.id).where(TenantModel.slug == plan.tenant_slug))
    if tenant_id is None:
        raise SeedDataConflictError("seed tenant could not be resolved")
    return tenant_id


def _ensure_role(session: Session, role: Role) -> UUID:
    desired_id = _stable_uuid("role", role.value)
    statement = (
        postgresql_insert(RoleModel)
        .values(id=desired_id, name=role.value)
        .on_conflict_do_nothing(index_elements=[RoleModel.name])
    )
    session.execute(statement)
    role_id = session.scalar(select(RoleModel.id).where(RoleModel.name == role.value))
    if role_id is None:
        raise SeedDataConflictError("seed role could not be resolved")
    return role_id


def _ensure_user(
    *,
    session: Session,
    tenant_id: UUID,
    tenant_slug: str,
    user: DevelopmentSeedUser,
    password_hasher: PasswordHasher,
    password: SecretStr,
) -> UUID:
    user_id = session.scalar(
        select(UserModel.id).where(
            UserModel.tenant_id == tenant_id,
            UserModel.email == user.email,
        )
    )
    if user_id is not None:
        return user_id

    desired_id = _stable_uuid("user", f"{tenant_slug}:{user.email}")
    statement = (
        postgresql_insert(UserModel)
        .values(
            id=desired_id,
            tenant_id=tenant_id,
            email=user.email,
            password_hash=password_hasher.hash_password(password.get_secret_value()),
            display_name=user.display_name,
            is_active=True,
        )
        .on_conflict_do_nothing(index_elements=[UserModel.tenant_id, UserModel.email])
    )
    session.execute(statement)
    resolved_id = session.scalar(
        select(UserModel.id).where(
            UserModel.tenant_id == tenant_id,
            UserModel.email == user.email,
        )
    )
    if resolved_id is None:
        raise SeedDataConflictError("seed user could not be resolved")
    return resolved_id


def _ensure_user_role(
    *,
    session: Session,
    tenant_id: UUID,
    user_id: UUID,
    role_id: UUID,
) -> None:
    statement = (
        postgresql_insert(UserRoleModel)
        .values(tenant_id=tenant_id, user_id=user_id, role_id=role_id)
        .on_conflict_do_nothing(
            index_elements=[
                UserRoleModel.tenant_id,
                UserRoleModel.user_id,
                UserRoleModel.role_id,
            ]
        )
    )
    session.execute(statement)


if __name__ == "__main__":
    raise SystemExit(main())
