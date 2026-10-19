"""Static and merged-contract checks for the isolated pilot Compose overlay."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest

from scripts.preflight_pilot_runtime import validate_compose_config

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
PILOT_COMPOSE = ROOT / "infra/pilot/compose.pilot.yml"
RLS_COMPOSE = ROOT / "infra/compose.rls.yml"
EVIDENCE_COMPOSE = ROOT / "infra/evidence/compose.evidence-security.yml"


def _service(environment: dict[str, str], *, image: str | None = None) -> dict[str, object]:
    service: dict[str, object] = {"environment": environment}
    if image is not None:
        service["image"] = image
    return service


@pytest.mark.parametrize("llm_provider", ["vllm", "llama_cpp"])
def test_merged_pilot_contract_requires_every_security_boundary(llm_provider: str) -> None:
    common = {
        "ENVIRONMENT": "pilot",
        "OTEL_ENABLED": "true",
        "OTEL_EXPORTER": "otlp_http",
        "DATABASE_RLS_REQUIRED": "true",
    }
    api = {
        **common,
        "LLM_PROVIDER": llm_provider,
        "VISION_PROVIDER": "remote",
        "MODEL_RELEASE_ENFORCEMENT": "true",
        "MODEL_ROUTE_ENFORCEMENT": "true",
        "LLM_API_KEY": "",
        "VISION_API_KEY": "",
        "LEGACY_PASSWORD_AUTH_ENABLED": "false",
        "OIDC_ENABLED": "true",
        "OIDC_TLS_VERIFY": "true",
        "OIDC_ALLOW_INSECURE_HTTP": "false",
        "OIDC_COOKIE_SECURE": "true",
        "EVIDENCE_IMAGE_SANITIZATION_ENABLED": "true",
        "EVIDENCE_MALWARE_SCANNER": "clamav",
        "CLAMAV_HOST": "clamav",
        "OPERATIONS_FAILURE_RECOVERY_MUTATIONS_ENABLED": "false",
        "SIGNED_INTAKE_ENABLED": "true",
        "SIGNED_INTAKE_SOURCES": json.dumps(
            {
                "pilot-customer-key-v1": {
                    "source_id": "pilot-customer-intake",
                    "tenant_id": "11111111-1111-4111-8111-111111111111",
                    "actor_user_id": "22222222-2222-4222-8222-222222222222",
                    "provenance": "pilot.customer.integration",
                    "public_key_file": "/run/config/signed_intake_public_key.pem",
                }
            }
        ),
        "SIGNED_INTAKE_MAX_BODY_BYTES": "131072",
        "SIGNED_INTAKE_CLOCK_SKEW_SECONDS": "300",
    }
    model_worker = {
        **common,
        "LLM_PROVIDER": llm_provider,
        "VISION_PROVIDER": "remote",
        "MODEL_RELEASE_ENFORCEMENT": "true",
        "MODEL_ROUTE_ENFORCEMENT": "true",
        "MODEL_ROUTE_DEPLOYMENT_ID": "onprem-4090-primary",
        "LLM_API_KEY": "model-llm-secret",
        "VISION_API_KEY": "model-vision-secret",
    }
    non_provider = {
        **common,
        "LLM_PROVIDER": "mock",
        "VISION_PROVIDER": "mock",
        "MODEL_RELEASE_ENFORCEMENT": "false",
        "MODEL_ROUTE_ENFORCEMENT": "false",
        "LLM_API_KEY": "",
        "VISION_API_KEY": "",
    }
    retrieval_worker = {
        **non_provider,
    }
    services = {
        "api": _service(api, image="csight-core:pilot-release"),
        "worker-model": _service(model_worker),
        "worker-retrieval": _service(retrieval_worker),
        "worker-decision": _service({**non_provider}),
        "dispatcher": _service({**non_provider}),
        "privacy-lifecycle": _service(
            {
                **non_provider,
                "PRIVACY_LIFECYCLE_AUTOMATION_ENABLED": "true",
                "PRIVACY_LIFECYCLE_TENANT_ID": "11111111-1111-4111-8111-111111111111",
            }
        ),
        "web": {"image": "csight-web:pilot-release"},
        "clamav": {
            "image": "clamav/clamav:1.5.4@sha256:" + "a" * 64,
            "expose": ["3310"],
        },
    }
    api_service = cast(dict[str, object], services["api"])
    api_service["configs"] = [
        {
            "source": "model-release-public-key",
            "target": "/run/config/model_release_public_key.pem",
            "mode": 0o444,
        },
        {
            "source": "signed-intake-public-key",
            "target": "/run/config/signed_intake_public_key.pem",
            "mode": 0o444,
        },
    ]
    model_service = cast(dict[str, object], services["worker-model"])
    model_service["configs"] = [
        {
            "source": "model-release-public-key",
            "target": "/run/config/model_release_public_key.pem",
            "mode": 0o444,
        }
    ]

    validate_compose_config(
        {"name": "csight-pilot", "services": services}, image_tag="pilot-release"
    )

    model = cast(dict[str, object], services["worker-model"])
    model_environment = cast(dict[str, str], model["environment"])
    model_environment["LLM_PROVIDER"] = "llama_cpp" if llm_provider == "vllm" else "vllm"
    with pytest.raises(Exception, match="share one admitted signed LLM runtime"):
        validate_compose_config(
            {"name": "csight-pilot", "services": services}, image_tag="pilot-release"
        )
    model_environment["LLM_PROVIDER"] = llm_provider

    retrieval = cast(dict[str, object], services["worker-retrieval"])
    retrieval_environment = cast(dict[str, str], retrieval["environment"])
    retrieval_environment["LLM_API_KEY"] = "credential-leak"
    with pytest.raises(
        Exception, match="worker-retrieval must not receive model provider credentials"
    ):
        validate_compose_config(
            {"name": "csight-pilot", "services": services}, image_tag="pilot-release"
        )
    retrieval_environment["LLM_API_KEY"] = ""
    retrieval["configs"] = [
        {
            "source": "model-release-public-key",
            "target": "/run/config/model_release_public_key.pem",
            "mode": 0o444,
        }
    ]
    with pytest.raises(
        Exception, match="worker-retrieval must not mount the model release public key"
    ):
        validate_compose_config(
            {"name": "csight-pilot", "services": services}, image_tag="pilot-release"
        )
    retrieval.pop("configs")

    api["LEGACY_PASSWORD_AUTH_ENABLED"] = "true"
    with pytest.raises(Exception, match="LEGACY_PASSWORD_AUTH_ENABLED=false"):
        validate_compose_config(
            {"name": "csight-pilot", "services": services}, image_tag="pilot-release"
        )
    api["LEGACY_PASSWORD_AUTH_ENABLED"] = "false"
    dispatcher = cast(dict[str, object], services["dispatcher"])
    dispatcher_environment = cast(dict[str, str], dispatcher["environment"])
    dispatcher_environment["LLM_API_KEY"] = "credential-leak"
    with pytest.raises(Exception, match="dispatcher must not receive model provider credentials"):
        validate_compose_config(
            {"name": "csight-pilot", "services": services}, image_tag="pilot-release"
        )
    dispatcher_environment["LLM_API_KEY"] = ""
    dispatcher_environment["SIGNED_INTAKE_ENABLED"] = "true"
    with pytest.raises(Exception, match="dispatcher must not receive signed intake settings"):
        validate_compose_config(
            {"name": "csight-pilot", "services": services}, image_tag="pilot-release"
        )
    dispatcher_environment.pop("SIGNED_INTAKE_ENABLED")
    dispatcher_environment["MODEL_ROUTE_DEPLOYMENT_ID"] = ""
    with pytest.raises(Exception, match="must not receive a model route deployment identity"):
        validate_compose_config(
            {"name": "csight-pilot", "services": services}, image_tag="pilot-release"
        )


def test_pilot_overlay_is_additive_and_reuses_rls_and_evidence_overlays() -> None:
    source = PILOT_COMPOSE.read_text(encoding="utf-8")
    rls_source = RLS_COMPOSE.read_text(encoding="utf-8")
    evidence_source = EVIDENCE_COMPOSE.read_text(encoding="utf-8")

    assert "name: csight-pilot" in source
    assert 'LEGACY_PASSWORD_AUTH_ENABLED: "false"' in source
    assert 'OIDC_ENABLED: "true"' in source
    assert 'PRIVACY_LIFECYCLE_AUTOMATION_ENABLED: "true"' in source
    assert 'MODEL_RELEASE_ENFORCEMENT: "true"' in source
    assert source.count('MODEL_ROUTE_ENFORCEMENT: "true"') == 2
    assert source.count('MODEL_ROUTE_ENFORCEMENT: "false"') == 4
    assert source.count("      MODEL_ROUTE_DEPLOYMENT_ID:") == 1
    assert 'OPERATIONS_FAILURE_RECOVERY_MUTATIONS_ENABLED: "false"' in source
    assert source.count('SIGNED_INTAKE_ENABLED: "true"') == 1
    assert source.count("signed-intake-public-key") == 2
    assert source.count("/run/config/signed_intake_public_key.pem") == 1
    common_source = source.split("x-qualified-llm-identity:", maxsplit=1)[0]
    assert "LLM_API_KEY" not in common_source
    assert "VISION_API_KEY" not in common_source
    assert source.count('LLM_API_KEY: ""') == 5
    assert source.count('VISION_API_KEY: ""') == 5
    assert "csight_api_login" not in source
    assert "clamav/clamav" not in source
    assert "csight_api_login" in rls_source
    assert "clamav/clamav:1.5.4@sha256:" in evidence_source


def test_real_compose_merge_scopes_provider_credentials_to_model_worker_only() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is not installed")
    environment = os.environ.copy()
    digest = "sha256:" + "a" * 64
    environment.update(
        {
            "CSIGHT_IMAGE_TAG": "pilot-merge-test",
            "POSTGRES_PASSWORD": "fixture",
            "RABBITMQ_DEFAULT_PASS": "fixture",
            "MINIO_ACCESS_KEY": "fixture",
            "MINIO_SECRET_KEY": "fixture",
            "JWT_SECRET_KEY": "f" * 32,
            "API_DATABASE_PASSWORD_HOST_FILE": os.fspath(ROOT / ".env.example"),
            "WORKER_DATABASE_PASSWORD_HOST_FILE": os.fspath(ROOT / ".env.example"),
            "DISPATCHER_DATABASE_PASSWORD_HOST_FILE": os.fspath(ROOT / ".env.example"),
            "MODEL_RELEASE_SIGNING_PUBLIC_KEY_HOST_FILE": os.fspath(ROOT / ".env.example"),
            "SIGNED_INTAKE_PUBLIC_KEY_HOST_FILE": os.fspath(ROOT / ".env.example"),
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector.internal:4318",
            "SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION": "pilot-v1",
            "SENSITIVE_PAYLOAD_RETENTION_DAYS": "90",
            "LLM_PROVIDER": "vllm",
            "LLM_BASE_URL": "http://llm.internal",
            "LLM_API_KEY": "llm-scope-fixture",
            "LLM_MODEL_ID": "model",
            "LLM_MODEL_VERSION": "1",
            "LLM_MODEL_REVISION": "a" * 40,
            "LLM_TASK_RUNTIMES": (
                '{"PRODUCT_DEFECT_TEXT_EXTRACTION_V2":'
                '{"base_url":"http://llm.internal","model_id":"model",'
                '"model_version":"1","model_revision":"'
                + "a"
                * 40
                + '","deployment_id":"onprem-4090-primary"},'
                '"POLICY_QUERY_BUILDER_V1":'
                '{"base_url":"http://llm.internal","model_id":"model",'
                '"model_version":"1","model_revision":"'
                + "a"
                * 40
                + '","deployment_id":"onprem-4090-primary"},'
                '"GROUNDED_POLICY_EXPLANATION_V1":'
                '{"base_url":"http://llm.internal","model_id":"model",'
                '"model_version":"1","model_revision":"'
                + "a" * 40
                + '","deployment_id":"onprem-4090-primary"}}'
            ),
            "MODEL_RELEASE_SIGNING_KEY_ID": "key-v1",
            "MODEL_ROUTE_DEPLOYMENT_ID": "onprem-4090-primary",
            "LLM_ARTIFACT_CONTENT_DIGEST": digest,
            "LLM_RUNTIME_IMAGE_DIGEST": digest,
            "LLM_DEPENDENCY_LOCK_DIGEST": digest,
            "LLM_SBOM_DIGEST": digest,
            "VISION_PROVIDER": "remote",
            "VISION_BASE_URL": "http://vision.internal",
            "VISION_API_KEY": "vision-scope-fixture",
            "VISION_MODEL_ID": "vision",
            "VISION_MODEL_VERSION": "1",
            "VISION_MODEL_REVISION": "revision",
            "EMBEDDING_BASE_URL": "http://embedding.internal",
            "OIDC_ISSUER": "https://idp.internal",
            "OIDC_CLIENT_ID": "pilot",
            "OIDC_AUTHORIZATION_ENDPOINT": "https://idp.internal/auth",
            "OIDC_TOKEN_ENDPOINT": "https://idp.internal/token",
            "OIDC_JWKS_URI": "https://idp.internal/certs",
            "OIDC_REDIRECT_URI": "https://pilot.internal/auth/oidc/callback",
            "OIDC_GROUP_MAPPINGS": (
                '{"/reviewers":{"tenant_slug":"pilot","allowed_roles":["REVIEWER"]}}'
            ),
            "MINIO_PRESIGNED_ENDPOINT": "evidence.internal",
            "PRIVACY_LIFECYCLE_TENANT_ID": "11111111-1111-4111-8111-111111111111",
            "SIGNED_INTAKE_SOURCES": (
                '{"pilot-customer-key-v1":{"source_id":"pilot-customer-intake",'
                '"tenant_id":"11111111-1111-4111-8111-111111111111",'
                '"actor_user_id":"22222222-2222-4222-8222-222222222222",'
                '"provenance":"pilot.customer.integration",'
                '"public_key_file":"/run/config/signed_intake_public_key.pem"}}'
            ),
            "SIGNED_INTAKE_MAX_BODY_BYTES": "131072",
            "SIGNED_INTAKE_CLOCK_SKEW_SECONDS": "300",
        }
    )
    command = [docker, "compose", "--env-file", "/dev/null"]
    for compose_file in (
        ROOT / "infra/compose.core.yml",
        ROOT / "infra/compose.rls.yml",
        ROOT / "infra/evidence/compose.evidence-security.yml",
        PILOT_COMPOSE,
    ):
        command.extend(("--file", os.fspath(compose_file)))
    command.extend(("--profile", "pilot-maintenance", "config", "--format", "json"))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    config = json.loads(completed.stdout)
    validate_compose_config(config, image_tag="pilot-merge-test")
    services = config["services"]

    assert services["api"]["environment"]["LLM_API_KEY"] == ""
    assert services["api"]["environment"]["VISION_API_KEY"] == ""
    assert services["api"]["environment"]["MODEL_ROUTE_ENFORCEMENT"] == "true"
    assert "MODEL_ROUTE_DEPLOYMENT_ID" not in services["api"]["environment"]
    assert services["api"]["environment"]["SIGNED_INTAKE_ENABLED"] == "true"
    assert services["api"]["environment"]["SIGNED_INTAKE_MAX_BODY_BYTES"] == "131072"
    assert services["api"]["environment"]["SIGNED_INTAKE_CLOCK_SKEW_SECONDS"] == "300"
    assert [
        item
        for item in services["api"]["configs"]
        if item["target"] == "/run/config/signed_intake_public_key.pem"
    ]
    assert services["worker-model"]["environment"]["LLM_API_KEY"] == "llm-scope-fixture"
    assert services["worker-model"]["environment"]["VISION_API_KEY"] == ("vision-scope-fixture")
    assert services["worker-model"]["environment"]["MODEL_ROUTE_ENFORCEMENT"] == "true"
    assert (
        services["worker-model"]["environment"]["MODEL_ROUTE_DEPLOYMENT_ID"]
        == "onprem-4090-primary"
    )
    assert services["worker-retrieval"]["environment"]["LLM_API_KEY"] == ""
    assert services["worker-retrieval"]["environment"]["VISION_API_KEY"] == ""
    assert services["worker-retrieval"]["environment"]["LLM_PROVIDER"] == "mock"
    assert services["worker-retrieval"]["environment"]["MODEL_RELEASE_ENFORCEMENT"] == "false"
    for service_name in ("worker-decision", "dispatcher", "privacy-lifecycle"):
        assert services[service_name]["environment"]["LLM_API_KEY"] == ""
        assert services[service_name]["environment"]["VISION_API_KEY"] == ""
    for service_name in (
        "worker-retrieval",
        "worker-decision",
        "dispatcher",
        "privacy-lifecycle",
    ):
        assert services[service_name]["environment"]["MODEL_ROUTE_ENFORCEMENT"] == "false"
        assert "MODEL_ROUTE_DEPLOYMENT_ID" not in services[service_name]["environment"]
    for service_name in (
        "worker-model",
        "worker-retrieval",
        "worker-decision",
        "dispatcher",
        "privacy-lifecycle",
    ):
        assert not any(
            name.startswith("SIGNED_INTAKE_") for name in services[service_name]["environment"]
        )
        assert not any(
            item.get("target") == "/run/config/signed_intake_public_key.pem"
            for item in services[service_name].get("configs", [])
        )
