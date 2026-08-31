"""Static safety contract for the opt-in Keycloak qualification stack."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

COMPOSE_PATH = Path("infra/oidc/compose.oidc-qualification.yml")
REALM_PATH = Path("infra/oidc/keycloak/csight-qualification-realm.json")
RUNNER_PATH = Path("scripts/qualify_oidc_keycloak.sh")


def test_keycloak_qualification_stack_is_isolated_pinned_and_oidc_only() -> None:
    document = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = document["services"]

    assert document["name"] == "csight-oidc-qualification"
    assert services["keycloak"]["image"] == (
        "quay.io/keycloak/keycloak@"
        "sha256:9d1f1b2b7261ff53c66cb1092dfcdc34a5fb77e81f9e6a6e75b8b6a795de8067"
    )
    assert services["postgres"]["tmpfs"] == ["/var/lib/postgresql/data"]
    assert services["api"]["ports"] == ["127.0.0.1:18000:8000"]
    assert services["keycloak"]["ports"] == ["127.0.0.1:18080:8080"]
    assert "--hostname=http://localhost:18080" in services["keycloak"]["command"]
    api_environment = services["api"]["environment"]
    assert api_environment["LEGACY_PASSWORD_AUTH_ENABLED"] == "false"
    assert api_environment["OIDC_ENABLED"] == "true"
    assert api_environment["OIDC_ALLOW_INSECURE_HTTP"] == "true"
    assert api_environment["ENVIRONMENT"] == "test"


def test_keycloak_realm_uses_public_pkce_client_and_placeholder_password() -> None:
    source = REALM_PATH.read_text(encoding="utf-8")
    realm = json.loads(source)
    client = realm["clients"][0]

    assert client["publicClient"] is True
    assert client["standardFlowEnabled"] is True
    assert client["directAccessGrantsEnabled"] is False
    assert client["serviceAccountsEnabled"] is False
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert client["attributes"]["backchannel.logout.url"] == (
        "http://api:8000/auth/oidc/backchannel-logout"
    )
    assert client["attributes"]["backchannel.logout.session.required"] == "true"
    assert client["redirectUris"] == ["http://127.0.0.1:18000/auth/oidc/callback"]
    assert realm["users"][0]["credentials"][0]["value"] == ("${OIDC_QUALIFICATION_USER_PASSWORD}")
    assert "reviewer-password" not in source
    assert "admin-password" not in source


def test_qualification_runner_rebuilds_current_core_and_always_cleans_up() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert "compose build migrator" in source
    assert "compose run --rm migrator" in source
    assert "trap cleanup EXIT INT TERM" in source
    assert "compose down --volumes --remove-orphans" in source
    assert "local-data/oidc-qualification/latest" in source
    assert 'chmod 600 "$REPORT_PATH"' in source
    assert 'chmod 700 "$OUTPUT_DIR"' in source
