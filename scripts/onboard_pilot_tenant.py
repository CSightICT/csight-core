"""Plan, apply, and verify one limited-pilot tenant without printing PII or secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    PolicyIndexVersionModel,
    PolicyRuleSetActivationModel,
    PolicyRuleSetModel,
    RoleModel,
    TenantModel,
    UserModel,
    UserRoleModel,
)
from app.adapters.persistence.session import create_session_factory
from app.adapters.security.password_hashing import Argon2PasswordHasher
from app.bootstrap.settings import Settings
from app.platform.tenant import Role

_ROLE_NAMESPACE = UUID("c18fc005-1867-49c3-907b-fba83556cc89")


class _ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AccountInput(_ManifestModel):
    id: UUID
    email: str = Field(min_length=3, max_length=320, repr=False)
    display_name: str = Field(min_length=1, max_length=255, repr=False)
    roles: frozenset[Role] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class ServiceActorInput(_ManifestModel):
    id: UUID
    email: str = Field(min_length=3, max_length=320, repr=False)
    display_name: str = Field(min_length=1, max_length=255, repr=False)
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
    provenance: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,191}$")
    public_key_file: Path

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class PilotOnboardingManifest(_ManifestModel):
    schema_version: str = Field(pattern=r"^pilot_onboarding/1\.0\.0$")
    tenant_id: UUID
    tenant_slug: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    tenant_name: str = Field(min_length=1, max_length=255, repr=False)
    accounts: tuple[AccountInput, ...] = Field(min_length=5, max_length=20)
    admin_idp_group: str = Field(min_length=1, max_length=255, repr=False)
    reviewer_idp_group: str = Field(min_length=1, max_length=255, repr=False)
    retention_policy_version: str = Field(min_length=1, max_length=128)
    retention_days: int = Field(ge=1, le=3650)
    service_actor: ServiceActorInput
    policy_index_name: str = Field(min_length=1, max_length=128)
    policy_index_version: str = Field(min_length=1, max_length=64)
    policy_rule_set_name: str = Field(min_length=1, max_length=128)
    policy_rule_set_version: str = Field(min_length=1, max_length=64)
    alert_recipient_count: int = Field(ge=1, le=20)
    operating_hours: str = Field(min_length=1, max_length=255)
    support_contact_configured: bool

    @model_validator(mode="after")
    def validate_staffing_and_identity(self) -> PilotOnboardingManifest:
        identifiers = [account.id for account in self.accounts]
        emails = [account.email for account in self.accounts]
        if len(set(identifiers)) != len(identifiers) or len(set(emails)) != len(emails):
            raise ValueError("named accounts must have unique IDs and emails")
        if self.service_actor.id in identifiers or self.service_actor.email in emails:
            raise ValueError("the signed-intake actor must be distinct from named accounts")
        roles = {role for account in self.accounts for role in account.roles}
        if Role.ADMIN not in roles or Role.REVIEWER not in roles:
            raise ValueError("at least one administrator and reviewer are required")
        if not self.support_contact_configured:
            raise ValueError("support contact must be configured")
        return self

    @property
    def configuration_digest(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


def _load_manifest(path: Path) -> PilotOnboardingManifest:
    return PilotOnboardingManifest.model_validate_json(path.read_text(encoding="utf-8"))


def build_public_plan(manifest: PilotOnboardingManifest, *, action: str) -> dict[str, object]:
    role_counts = {
        role.value: sum(role in account.roles for account in manifest.accounts) for role in Role
    }
    return {
        "schema_version": "pilot_onboarding_result/1.0.0",
        "action": action,
        "configuration_digest": manifest.configuration_digest,
        "named_account_count": len(manifest.accounts),
        "role_counts": role_counts,
        "signed_intake_actor_has_no_roles": True,
        "retention_is_explicit": True,
        "oidc_group_count": 2,
        "alert_recipient_count": manifest.alert_recipient_count,
        "support_contact_configured": manifest.support_contact_configured,
    }


def build_environment_fragment(manifest: PilotOnboardingManifest) -> str:
    oidc = {
        manifest.admin_idp_group: {
            "tenant_slug": manifest.tenant_slug,
            "allowed_roles": [Role.ADMIN.value],
        },
        manifest.reviewer_idp_group: {
            "tenant_slug": manifest.tenant_slug,
            "allowed_roles": [Role.REVIEWER.value],
        },
    }
    signed = {
        manifest.service_actor.source_id: {
            "source_id": manifest.service_actor.source_id,
            "tenant_id": str(manifest.tenant_id),
            "actor_user_id": str(manifest.service_actor.id),
            "provenance": manifest.service_actor.provenance,
            "public_key_file": os.fspath(manifest.service_actor.public_key_file),
        }
    }
    return "\n".join(
        (
            f"OIDC_GROUP_MAPPINGS='{json.dumps(oidc, separators=(',', ':'))}'",
            f"SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION={manifest.retention_policy_version}",
            f"SENSITIVE_PAYLOAD_RETENTION_DAYS={manifest.retention_days}",
            "PRIVACY_LIFECYCLE_AUTOMATION_ENABLED=true",
            f"PRIVACY_LIFECYCLE_TENANT_ID={manifest.tenant_id}",
            "SIGNED_INTAKE_ENABLED=true",
            f"SIGNED_INTAKE_SOURCES='{json.dumps(signed, separators=(',', ':'))}'",
            "",
        )
    )


def write_owner_only(path: Path, content: str) -> bool:
    encoded = content.encode()
    if path.exists():
        if path.read_bytes() != encoded:
            raise RuntimeError("onboarding output already exists with different content")
        return False
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
    finally:
        os.close(descriptor)
    return True


def _upsert_user(
    session: Session,
    manifest: PilotOnboardingManifest,
    account: AccountInput,
) -> None:
    existing = session.get(UserModel, account.id)
    if existing is None:
        existing = UserModel(
            id=account.id,
            tenant_id=manifest.tenant_id,
            email=account.email,
            display_name=account.display_name,
            password_hash=Argon2PasswordHasher().hash_password(secrets.token_urlsafe(48)),
            is_active=True,
        )
        session.add(existing)
        session.flush()
    elif (
        existing.tenant_id != manifest.tenant_id
        or existing.email != account.email
        or existing.display_name != account.display_name
    ):
        raise RuntimeError("an existing account conflicts with the onboarding manifest")
    else:
        existing.is_active = True


def apply_manifest(manifest: PilotOnboardingManifest, *, output: Path, settings: Settings) -> bool:
    if settings.database_url_value is None:
        raise RuntimeError("DATABASE_URL is required for onboarding apply")
    factory = create_session_factory(get_engine(settings))
    with factory.begin() as session:
        tenant = session.get(TenantModel, manifest.tenant_id)
        if tenant is None:
            session.add(
                TenantModel(
                    id=manifest.tenant_id,
                    slug=manifest.tenant_slug,
                    name=manifest.tenant_name,
                    is_active=True,
                )
            )
            session.flush()
        elif tenant.slug != manifest.tenant_slug or tenant.name != manifest.tenant_name:
            raise RuntimeError("an existing tenant conflicts with the onboarding manifest")
        else:
            tenant.is_active = True

        roles_by_name: dict[Role, RoleModel] = {}
        for role in Role:
            role_row = session.scalar(select(RoleModel).where(RoleModel.name == role.value))
            if role_row is None:
                role_row = RoleModel(id=uuid5(_ROLE_NAMESPACE, role.value), name=role.value)
                session.add(role_row)
                session.flush()
            roles_by_name[role] = role_row

        for account in manifest.accounts:
            _upsert_user(session, manifest, account)
            for role in account.roles:
                role_row = roles_by_name[role]
                assignment = session.get(
                    UserRoleModel,
                    {
                        "tenant_id": manifest.tenant_id,
                        "user_id": account.id,
                        "role_id": role_row.id,
                    },
                )
                if assignment is None:
                    session.add(
                        UserRoleModel(
                            tenant_id=manifest.tenant_id,
                            user_id=account.id,
                            role_id=role_row.id,
                        )
                    )

        actor = AccountInput(
            id=manifest.service_actor.id,
            email=manifest.service_actor.email,
            display_name=manifest.service_actor.display_name,
            roles=frozenset({Role.REVIEWER}),
        )
        _upsert_user(session, manifest, actor)
        actor_roles = session.scalar(
            select(UserRoleModel).where(
                UserRoleModel.tenant_id == manifest.tenant_id,
                UserRoleModel.user_id == manifest.service_actor.id,
            )
        )
        if actor_roles is not None:
            raise RuntimeError("the signed-intake service actor must have no roles")
    return write_owner_only(output, build_environment_fragment(manifest))


def verify_manifest(
    manifest: PilotOnboardingManifest,
    *,
    output: Path,
    settings: Settings,
) -> dict[str, object]:
    if settings.database_url_value is None:
        raise RuntimeError("DATABASE_URL is required for onboarding verify")
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        tenant = session.get(TenantModel, manifest.tenant_id)
        active_users = session.scalars(
            select(UserModel).where(
                UserModel.tenant_id == manifest.tenant_id,
                UserModel.is_active.is_(True),
            )
        ).all()
        actor_role = session.scalar(
            select(UserRoleModel).where(
                UserRoleModel.tenant_id == manifest.tenant_id,
                UserRoleModel.user_id == manifest.service_actor.id,
            )
        )
        index = session.scalar(
            select(PolicyIndexVersionModel).where(
                PolicyIndexVersionModel.tenant_id == manifest.tenant_id,
                PolicyIndexVersionModel.index_name == manifest.policy_index_name,
                PolicyIndexVersionModel.index_version == manifest.policy_index_version,
                PolicyIndexVersionModel.status == "ACTIVE",
            )
        )
        active_rule = session.scalar(
            select(PolicyRuleSetActivationModel)
            .join(
                PolicyRuleSetModel,
                PolicyRuleSetModel.id == PolicyRuleSetActivationModel.rule_set_id,
            )
            .where(
                PolicyRuleSetActivationModel.tenant_id == manifest.tenant_id,
                PolicyRuleSetActivationModel.retired_at.is_(None),
                PolicyRuleSetModel.rule_set_name == manifest.policy_rule_set_name,
                PolicyRuleSetModel.rule_set_version == manifest.policy_rule_set_version,
            )
        )
    expected_fragment = build_environment_fragment(manifest).encode()
    gates = {
        "tenant_and_named_accounts": tenant is not None
        and tenant.is_active
        and len(active_users) >= len(manifest.accounts) + 1,
        "oidc_mapping": output.is_file() and output.read_bytes() == expected_fragment,
        "retention": output.is_file() and output.read_bytes() == expected_fragment,
        "signed_intake_no_role_actor": actor_role is None,
        "active_policy_runtime": index is not None and active_rule is not None,
        "operator_support": manifest.alert_recipient_count > 0
        and manifest.support_contact_configured,
    }
    return {
        **build_public_plan(manifest, action="verify"),
        "gates": {name: "PASS" if passed else "FAIL" for name, passed in gates.items()},
        "configuration_ready": all(gates.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "apply", "verify"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    manifest = _load_manifest(arguments.manifest)
    if arguments.action == "plan":
        result = build_public_plan(manifest, action="plan")
    else:
        if arguments.output is None:
            parser.error("--output is required for apply and verify")
        settings = Settings()
        if arguments.action == "apply":
            created = apply_manifest(manifest, output=arguments.output, settings=settings)
            result = {**build_public_plan(manifest, action="apply"), "output_created": created}
        else:
            result = verify_manifest(manifest, output=arguments.output, settings=settings)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("configuration_ready", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
