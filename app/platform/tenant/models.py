"""Tenant identity and role permissions without authentication technology."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.platform.errors import ForbiddenError


class Role(StrEnum):
    ADMIN = "ADMIN"
    REVIEWER = "REVIEWER"
    QUALITY_VIEWER = "QUALITY_VIEWER"


class Permission(StrEnum):
    CASE_CREATE = "CASE_CREATE"
    CASE_READ = "CASE_READ"
    EVIDENCE_UPLOAD = "EVIDENCE_UPLOAD"
    ANALYSIS_CREATE = "ANALYSIS_CREATE"
    ANALYSIS_READ = "ANALYSIS_READ"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.REVIEWER: frozenset(
        {
            Permission.CASE_CREATE,
            Permission.CASE_READ,
            Permission.EVIDENCE_UPLOAD,
            Permission.ANALYSIS_CREATE,
            Permission.ANALYSIS_READ,
        }
    ),
    Role.QUALITY_VIEWER: frozenset({Permission.CASE_READ, Permission.ANALYSIS_READ}),
}


class Principal(BaseModel):
    """An active authenticated user scoped to exactly one tenant."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    user_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    email: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    roles: frozenset[Role] = Field(min_length=1)

    def has_permission(self, permission: Permission) -> bool:
        return any(permission in ROLE_PERMISSIONS[role] for role in self.roles)

    def require(self, permission: Permission) -> None:
        if not self.has_permission(permission):
            raise ForbiddenError()


class UserAccount(BaseModel):
    """Authentication-facing user snapshot without persistence implementation types."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    user_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    tenant_slug: str = Field(min_length=1, max_length=63)
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=255)
    password_hash: str = Field(min_length=1, max_length=512, repr=False)
    roles: frozenset[Role] = Field(default_factory=frozenset)
    is_active: bool
    tenant_is_active: bool

    @property
    def can_authenticate(self) -> bool:
        return self.is_active and self.tenant_is_active and bool(self.roles)
