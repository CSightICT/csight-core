"""Fail-closed API and model-Worker composition for pinned v2 routes."""

from pathlib import Path
from typing import Literal, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import SecretStr

from app.adapters.security.model_release_signatures import ModelReleaseKeyConfigurationError
from app.application.analysis import StartTextAnalysis
from app.application.model_routing import (
    ResolveActiveModelRoutePlan,
    ResolvePinnedModelRoutePlan,
)
from app.bootstrap.model_routing import (
    build_active_model_route_resolver,
    build_pinned_model_route_guard,
    validate_model_route_worker_startup,
)
from app.bootstrap.settings import Settings
from app.bootstrap.sprint2 import build_execute_text_extraction, build_sprint2_services

pytestmark = pytest.mark.unit


def _public_key(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "model-release-public.pem"
    path.write_bytes(
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    path.chmod(0o600)
    return path


def _settings(tmp_path: Path, *, role: Literal["api", "worker"]) -> Settings:
    digest = "sha256:" + "a" * 64
    values: dict[str, object] = {
        "database_url": SecretStr(f"postgresql+psycopg://{role}:secret@invalid:5432/csight"),
        "database_runtime_role": role,
        "database_rls_required": True,
        "llm_provider": "vllm",
        "llm_base_url": "http://llm.invalid:18000/v1",
        "llm_model_id": "qualified-model",
        "llm_model_version": "1.0.0",
        "llm_model_revision": "b" * 40,
        "model_release_enforcement": True,
        "model_release_signing_public_key_file": _public_key(tmp_path),
        "model_release_signing_key_id": "release-key-1",
        "llm_artifact_content_digest": digest,
        "llm_runtime_image_digest": digest,
        "llm_dependency_lock_digest": digest,
        "llm_sbom_digest": digest,
        "model_route_enforcement": True,
    }
    if role == "worker":
        values["model_route_deployment_id"] = "onprem-4090-primary"
    return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


def test_disabled_route_enforcement_preserves_legacy_composition() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert build_active_model_route_resolver(settings) is None
    assert build_pinned_model_route_guard(settings) is None
    validate_model_route_worker_startup(settings)


def test_api_and_model_worker_receive_their_distinct_route_guards(tmp_path: Path) -> None:
    api_settings = _settings(tmp_path / "api", role="api")
    worker_settings = _settings(tmp_path / "worker", role="worker")

    active = build_active_model_route_resolver(api_settings)
    pinned = build_pinned_model_route_guard(worker_settings)
    api_services = build_sprint2_services(api_settings)
    api_start = cast(StartTextAnalysis, api_services.start_text_analysis)
    worker = build_execute_text_extraction(worker_settings)
    validate_model_route_worker_startup(worker_settings)

    assert isinstance(active, ResolveActiveModelRoutePlan)
    assert isinstance(pinned, ResolvePinnedModelRoutePlan)
    assert isinstance(
        api_start._model_route_resolver,  # pyright: ignore[reportPrivateUsage]
        ResolveActiveModelRoutePlan,
    )
    assert isinstance(
        worker._model_route_guard,  # pyright: ignore[reportPrivateUsage]
        ResolvePinnedModelRoutePlan,
    )
    deployment = worker._model_route_guard._deployment_identity  # pyright: ignore[reportPrivateUsage]
    assert deployment.deployment_id == "onprem-4090-primary"
    assert deployment.runtime_identity.served_model_name == "qualified-model"


def test_enforced_composition_rejects_an_unreadable_verification_key(tmp_path: Path) -> None:
    settings = _settings(tmp_path, role="worker")
    public_key = settings.model_release_signing_public_key_file
    assert public_key is not None
    public_key.unlink()

    with pytest.raises(ModelReleaseKeyConfigurationError, match="public key file is unavailable"):
        validate_model_route_worker_startup(settings)
