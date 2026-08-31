"""PII-free planning and owner-only output contracts for pilot onboarding."""

from pathlib import Path
from uuid import uuid4

import pytest

from scripts.onboard_pilot_tenant import (
    PilotOnboardingManifest,
    build_environment_fragment,
    build_public_plan,
    write_owner_only,
)

pytestmark = pytest.mark.unit


def _manifest(tmp_path: Path) -> PilotOnboardingManifest:
    tenant_id = uuid4()
    roles = ("ADMIN", "REVIEWER", "REVIEWER", "REVIEWER", "REVIEWER")
    return PilotOnboardingManifest.model_validate(
        {
            "schema_version": "pilot_onboarding/1.0.0",
            "tenant_id": tenant_id,
            "tenant_slug": "pilot-customer",
            "tenant_name": "Private Customer",
            "accounts": [
                {
                    "id": uuid4(),
                    "email": f"operator-{index}@private.invalid",
                    "display_name": f"Private Operator {index}",
                    "roles": [role],
                }
                for index, role in enumerate(roles, start=1)
            ],
            "admin_idp_group": "/private/admins",
            "reviewer_idp_group": "/private/reviewers",
            "retention_policy_version": "customer-approved-v1",
            "retention_days": 90,
            "service_actor": {
                "id": uuid4(),
                "email": "intake@private.invalid",
                "display_name": "Private Intake",
                "source_id": "pilot-intake-v1",
                "provenance": "customer.integration",
                "public_key_file": tmp_path / "public.pem",
            },
            "policy_index_name": "customer-policy",
            "policy_index_version": "v1",
            "policy_rule_set_name": "customer-rules",
            "policy_rule_set_version": "v1",
            "alert_recipient_count": 2,
            "operating_hours": "weekdays",
            "support_contact_configured": True,
        }
    )


def test_plan_exposes_only_counts_and_digest(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    plan = build_public_plan(manifest, action="plan")
    serialized = str(plan)

    assert plan["named_account_count"] == 5
    assert plan["retention_is_explicit"] is True
    assert manifest.tenant_name not in serialized
    assert manifest.tenant_slug not in serialized
    assert all(account.email not in serialized for account in manifest.accounts)


def test_owner_only_fragment_is_idempotent_and_never_overwritten(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    output = tmp_path / "pilot-onboarding.env"
    content = build_environment_fragment(manifest)

    assert write_owner_only(output, content) is True
    assert write_owner_only(output, content) is False
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(RuntimeError, match="different content"):
        write_owner_only(output, content + "CHANGED=true\n")
