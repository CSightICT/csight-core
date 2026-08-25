"""Tenant identity and role-permission contracts."""

from app.platform.tenant.models import Permission, Principal, Role, UserAccount

__all__ = ["Permission", "Principal", "Role", "UserAccount"]
