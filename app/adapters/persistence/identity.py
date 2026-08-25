"""SQLAlchemy implementation of the tenant-scoped identity repository."""

from uuid import UUID

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    RoleModel,
    TenantModel,
    UserModel,
    UserRoleModel,
)
from app.platform.tenant import Role, UserAccount


def _optional_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


class SQLAlchemyIdentityRepository:
    """Return current user snapshots while leaving auth policy to the application."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_for_login(self, *, tenant_slug: str, email: str) -> UserAccount | None:
        normalized_slug = tenant_slug.strip().lower()
        normalized_email = email.strip().lower()
        if not normalized_slug or not normalized_email:
            return None
        return self._find(
            TenantModel.slug == normalized_slug,
            UserModel.email == normalized_email,
        )

    def get_by_tenant_and_subject(
        self,
        *,
        tenant_id: str,
        subject: str,
    ) -> UserAccount | None:
        tenant_uuid = _optional_uuid(tenant_id)
        user_uuid = _optional_uuid(subject)
        if tenant_uuid is None or user_uuid is None:
            return None
        return self._find(
            TenantModel.id == tenant_uuid,
            UserModel.id == user_uuid,
        )

    def _find(self, *filters: ColumnElement[bool]) -> UserAccount | None:
        statement = (
            select(TenantModel, UserModel, RoleModel.name)
            .select_from(TenantModel)
            .join(UserModel, UserModel.tenant_id == TenantModel.id)
            .outerjoin(
                UserRoleModel,
                and_(
                    UserRoleModel.tenant_id == UserModel.tenant_id,
                    UserRoleModel.user_id == UserModel.id,
                ),
            )
            .outerjoin(RoleModel, RoleModel.id == UserRoleModel.role_id)
            .where(*filters)
            .order_by(RoleModel.name.asc())
        )
        rows = self._session.execute(statement).all()
        if not rows:
            return None

        tenant, user, _role_name = rows[0]
        roles = frozenset(Role(role_name) for _, _, role_name in rows if role_name is not None)
        return UserAccount(
            user_id=str(user.id),
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
            email=user.email,
            display_name=user.display_name,
            password_hash=user.password_hash,
            roles=roles,
            is_active=user.is_active,
            tenant_is_active=tenant.is_active,
        )


class SQLAlchemyIdentityRepositoryFactoryAdapter:
    """Thread-safe identity adapter opening a short read session for every lookup."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def find_for_login(self, *, tenant_slug: str, email: str) -> UserAccount | None:
        with self._session_factory() as session:
            return SQLAlchemyIdentityRepository(session).find_for_login(
                tenant_slug=tenant_slug,
                email=email,
            )

    def get_by_tenant_and_subject(
        self,
        *,
        tenant_id: str,
        subject: str,
    ) -> UserAccount | None:
        with self._session_factory() as session:
            return SQLAlchemyIdentityRepository(session).get_by_tenant_and_subject(
                tenant_id=tenant_id,
                subject=subject,
            )
