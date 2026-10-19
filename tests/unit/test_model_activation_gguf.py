"""GGUF release provenance, runtime identity, and fail-closed mode contracts."""

import base64
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr, ValidationError

from app.application.model_activation import (
    ActivateSignedModelRelease,
    RequireActiveModelRelease,
)
from app.application.model_routing import ActivateModelRoutePlan
from app.bootstrap.model_activation import (
    ModelActivationConfigurationError,
    build_runtime_llm_identity,
)
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs import PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
from app.domains.product_defect_cs.prompts import (
    GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1,
    POLICY_QUERY_BUILDER_PROMPT_V1_1,
)
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.model_activation import (
    ActiveLLMRelease,
    LLMReleaseManifestV1_1,
    ModelActivationEvent,
    ModelArtifactFormat,
    ModelReleaseExecutionGateReason,
    ModelReleaseModeNotAllowedError,
    ModelReleaseStatus,
    ModelReleaseTask,
    ModelRuntimeEngine,
    RegisteredLLMRelease,
    RuntimeLLMIdentityV1_1,
    SignedLLMReleaseManifest,
)
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 31, 4, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


def gguf_manifest_fixture(
    status: ModelReleaseStatus = ModelReleaseStatus.SHADOW_CANDIDATE,
    task: ModelReleaseTask = ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
) -> LLMReleaseManifestV1_1:
    return LLMReleaseManifestV1_1(
        candidate_id="qwen38-27b-csight-q4-k-m-llama-cpp",
        package_name="csight-qwen38-27b-gguf",
        package_version="2026.08.31.1",
        task=task,
        artifact="CSightICT/Qwen3.8-27B-CSight-GGUF",
        artifact_revision="1" * 40,
        artifact_content_digest=DIGEST,
        artifact_weight_bytes=17_000_000_000,
        upstream_model_artifact="Qwen/Qwen3.8-27B",
        upstream_model_revision="2" * 40,
        base_artifact="ggml-org/Qwen3.8-27B-GGUF",
        base_revision="3" * 40,
        base_artifact_content_digest="sha256:" + "b" * 64,
        gguf_filename="Qwen3.8-27B-CSight-Q4_K_M.gguf",
        quantization_type="Q4_K_M",
        quantization_recipe_digest="sha256:" + "c" * 64,
        calibration_dataset_digest="sha256:" + "d" * 64,
        calibration_manifest_digest="sha256:" + "e" * 64,
        importance_matrix_digest="sha256:" + "f" * 64,
        tokenizer_digest="sha256:" + "0" * 64,
        chat_template_digest="sha256:" + "1" * 64,
        quantizer_binary_digest="sha256:" + "2" * 64,
        runtime_image="csight/llama-cpp-qwen38",
        runtime_image_digest="sha256:" + "3" * 64,
        llama_cpp_revision="4" * 40,
        runtime_binary_digest="sha256:" + "5" * 64,
        runtime_build_manifest_digest="sha256:" + "6" * 64,
        sbom_digest="sha256:" + "7" * 64,
        served_model_name="csight-qwen3.8-27b-q4-k-m",
        model_version="Qwen3.8-27B-CSight-Q4_K_M",
        max_context_tokens=4096,
        max_num_sequences=1,
        batch_size=512,
        ubatch_size=128,
        prompt_name="product_defect_text_extraction",
        prompt_version="2.0.0",
        prompt_content_hash="8" * 64,
        input_schema_version="2.0",
        output_schema_version="2.0",
        qualification_dataset_digest="sha256:" + "9" * 64,
        qualification_result_digest=(
            "sha256:" + "a" * 64 if status is ModelReleaseStatus.RELEASE_ELIGIBLE else None
        ),
        candidate_matrix_digest="sha256:" + "b" * 64,
        candidate_assessment_digest="sha256:" + "c" * 64,
        release_status=status,
        qualified_at=NOW if status is ModelReleaseStatus.RELEASE_ELIGIBLE else None,
    )


def _signed(
    status: ModelReleaseStatus = ModelReleaseStatus.SHADOW_CANDIDATE,
    task: ModelReleaseTask = ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
) -> SignedLLMReleaseManifest:
    return SignedLLMReleaseManifest(
        manifest=gguf_manifest_fixture(status, task),
        signing_key_id="release-key-1",
        signature_base64=base64.b64encode(b"s" * 64).decode(),
    )


def _principal() -> Principal:
    return Principal(
        user_id="admin-1",
        tenant_id="tenant-1",
        email="admin@example.test",
        display_name="Admin",
        roles=frozenset({Role.ADMIN}),
    )


class _Verifier:
    def verify(self, value: SignedLLMReleaseManifest) -> bool:
        del value
        return True


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Ids:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.value = 0

    def new_id(self) -> str:
        self.value += 1
        return f"{self.prefix}-{self.value}"


class _ActivationRepository:
    def __init__(self, release: RegisteredLLMRelease) -> None:
        self.release = release
        self.active: ActiveLLMRelease | None = None
        self.by_id: dict[str, ActiveLLMRelease] = {}
        self.activation_events: list[ModelActivationEvent] = []
        self.active_reads = 0

    def get_release(self, **_: object) -> RegisteredLLMRelease:
        return self.release

    def get_active(self, **_: object) -> ActiveLLMRelease | None:
        self.active_reads += 1
        return self.active

    def get_by_activation_id(self, *, activation_id: str, **_: object) -> ActiveLLMRelease | None:
        return self.by_id.get(activation_id)

    def activate(
        self,
        *,
        event: ModelActivationEvent,
        expected_current_activation_id: str | None,
    ) -> tuple[ModelActivationEvent, bool]:
        del expected_current_activation_id
        self.activation_events.append(event)
        self.active = ActiveLLMRelease(release=self.release, activation=event)
        self.by_id[event.id] = self.active
        return event, False


class _RouteRepository:
    def __init__(self) -> None:
        self.events: list[object] = []

    def get_by_idempotency_key(self, **_: object) -> None:
        return None

    def get_active(self, **_: object) -> None:
        return None

    def activate(self, *, route_plan: object, **_: object) -> tuple[object, bool]:
        self.events.append(route_plan)
        return route_plan, False


def _registered(
    status: ModelReleaseStatus = ModelReleaseStatus.SHADOW_CANDIDATE,
    task: ModelReleaseTask = ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
) -> RegisteredLLMRelease:
    return RegisteredLLMRelease(
        id="release-1",
        tenant_id="tenant-1",
        signed_manifest=_signed(status, task),
        registered_by="admin-1",
        registered_at=NOW,
    )


def gguf_runtime_identity_fixture(
    manifest: LLMReleaseManifestV1_1,
) -> RuntimeLLMIdentityV1_1:
    return RuntimeLLMIdentityV1_1.model_validate(
        {field: getattr(manifest, field) for field in RuntimeLLMIdentityV1_1.model_fields}
    )


def test_gguf_manifest_is_not_a_vllm_manifest_and_carries_complete_provenance() -> None:
    manifest = gguf_manifest_fixture()

    assert manifest.artifact_format is ModelArtifactFormat.GGUF
    assert manifest.runtime_engine is ModelRuntimeEngine.LLAMA_CPP
    assert "gpu_memory_utilization" not in LLMReleaseManifestV1_1.model_fields
    assert "dependency_lock_digest" not in LLMReleaseManifestV1_1.model_fields
    assert manifest.upstream_model_artifact == "Qwen/Qwen3.8-27B"
    assert manifest.base_artifact == "ggml-org/Qwen3.8-27B-GGUF"
    assert manifest.tokenizer_digest.startswith("sha256:")
    assert manifest.chat_template_digest.startswith("sha256:")
    assert manifest.quantizer_binary_digest.startswith("sha256:")


def test_extraction_gguf_cannot_claim_release_eligible_without_provider_neutral_evaluator() -> None:
    with pytest.raises(ValidationError, match="provider-neutral extraction evaluator"):
        gguf_manifest_fixture(ModelReleaseStatus.RELEASE_ELIGIBLE)


def test_extraction_gguf_primary_activation_reports_gate_and_creates_zero_events() -> None:
    repository = _ActivationRepository(_registered())
    service = ActivateSignedModelRelease(
        repository=repository,  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
        clock=_Clock(),
        id_generator=_Ids("activation"),
    )

    with pytest.raises(ModelReleaseModeNotAllowedError) as captured:
        service.execute(
            principal=_principal(),
            release_id="release-1",
            execution_mode=AnalysisExecutionMode.PRIMARY,
            expected_current_activation_id=None,
            reason="Must remain Shadow",
            idempotency_key="activation-key-1",
        )

    assert captured.value.details == {
        "gate_reason": (
            ModelReleaseExecutionGateReason.GGUF_EXTRACTION_PROVIDER_NEUTRAL_EVALUATOR_REQUIRED
        ).value
    }
    assert "provider-neutral extraction evaluator" in captured.value.message
    assert repository.active_reads == 0
    assert repository.activation_events == []


def test_legacy_release_eligible_extraction_gguf_cannot_bypass_primary_gate() -> None:
    release = _registered()
    manifest = release.signed_manifest.manifest
    assert isinstance(manifest, LLMReleaseManifestV1_1)
    unvalidated_legacy_manifest = manifest.model_copy(
        update={
            "release_status": ModelReleaseStatus.RELEASE_ELIGIBLE,
            "qualification_result_digest": DIGEST,
            "qualified_at": NOW,
        }
    )
    release = release.model_copy(
        update={
            "signed_manifest": release.signed_manifest.model_copy(
                update={"manifest": unvalidated_legacy_manifest}
            )
        }
    )
    repository = _ActivationRepository(release)
    service = ActivateSignedModelRelease(
        repository=repository,  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
        clock=_Clock(),
        id_generator=_Ids("activation"),
    )

    with pytest.raises(ModelReleaseModeNotAllowedError) as captured:
        service.execute(
            principal=_principal(),
            release_id=release.id,
            execution_mode=AnalysisExecutionMode.PRIMARY,
            expected_current_activation_id=None,
            reason="Legacy release must still fail closed",
            idempotency_key="activation-key-legacy-eligible",
        )

    assert captured.value.details["gate_reason"] == (
        ModelReleaseExecutionGateReason.GGUF_EXTRACTION_PROVIDER_NEUTRAL_EVALUATOR_REQUIRED.value
    )
    assert repository.active_reads == 0
    assert repository.activation_events == []


def test_release_eligible_non_extraction_gguf_can_activate_primary() -> None:
    release = _registered(
        ModelReleaseStatus.RELEASE_ELIGIBLE,
        ModelReleaseTask.POLICY_QUERY_BUILDER_V1,
    )
    repository = _ActivationRepository(release)
    service = ActivateSignedModelRelease(
        repository=repository,  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
        clock=_Clock(),
        id_generator=_Ids("activation"),
    )

    result = service.execute(
        principal=_principal(),
        release_id=release.id,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        expected_current_activation_id=None,
        reason="Qualified provider-neutral policy query evaluator",
        idempotency_key="activation-key-query-primary",
    )

    assert result.activation.task is ModelReleaseTask.POLICY_QUERY_BUILDER_V1
    assert repository.activation_events == [result.activation]


def test_shadow_activation_is_allowed_and_runtime_guard_compares_all_gguf_fields() -> None:
    release = _registered()
    repository = _ActivationRepository(release)
    service = ActivateSignedModelRelease(
        repository=repository,  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
        clock=_Clock(),
        id_generator=_Ids("activation"),
    )
    service.execute(
        principal=_principal(),
        release_id=release.id,
        execution_mode=AnalysisExecutionMode.SHADOW,
        expected_current_activation_id=None,
        reason="Run signed Shadow qualification",
        idempotency_key="activation-key-shadow",
    )
    manifest = release.signed_manifest.manifest
    assert isinstance(manifest, LLMReleaseManifestV1_1)
    identity = gguf_runtime_identity_fixture(manifest)
    guard = RequireActiveModelRelease(
        repository=repository,  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
        runtime_identity=identity,
    )
    assert (
        guard.execute(
            tenant_id="tenant-1",
            execution_mode=AnalysisExecutionMode.SHADOW,
        ).release
        == release
    )
    assert set(RuntimeLLMIdentityV1_1.model_fields) == {
        field
        for field in LLMReleaseManifestV1_1.model_fields
        if field
        not in {
            "schema_version",
            "candidate_id",
            "package_name",
            "package_version",
            "task",
            "qualification_dataset_digest",
            "qualification_result_digest",
            "candidate_matrix_digest",
            "candidate_assessment_digest",
            "release_status",
            "qualified_at",
        }
    }


def test_shadow_release_primary_route_activation_creates_zero_route_events() -> None:
    release = _registered()
    activation = ModelActivationEvent(
        id="activation-legacy-invalid",
        tenant_id="tenant-1",
        task=release.signed_manifest.manifest.task,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        model_release_id=release.id,
        activated_by="admin-1",
        reason="Pre-enforcement fixture",
        idempotency_key="legacy-invalid",
        request_hash="d" * 64,
        activated_at=NOW,
    )
    activations = _ActivationRepository(release)
    activations.active = ActiveLLMRelease(release=release, activation=activation)
    activations.by_id[activation.id] = activations.active
    routes = _RouteRepository()
    service = ActivateModelRoutePlan(
        route_repository=routes,  # type: ignore[arg-type]
        activation_repository=activations,  # type: ignore[arg-type]
        signature_verifier=_Verifier(),
        clock=_Clock(),
        id_generator=_Ids("route"),
    )

    with pytest.raises(ModelReleaseModeNotAllowedError):
        service.execute(
            principal=_principal(),
            task=ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
            execution_mode=AnalysisExecutionMode.PRIMARY,
            model_activation_id=activation.id,
            deployment_id="onprem-4090-primary",
            expected_current_route_plan_id=None,
            reason="Must remain Shadow",
            idempotency_key="route-key-1",
        )

    assert routes.events == []


def test_settings_builder_constructs_complete_gguf_runtime_identity() -> None:
    manifest = gguf_manifest_fixture()
    identity = gguf_runtime_identity_fixture(manifest).model_copy(
        update={
            "prompt_name": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.name,
            "prompt_version": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.version,
            "prompt_content_hash": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.content_hash,
            "input_schema_version": (PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.input_schema_version),
            "output_schema_version": (
                PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.output_schema_version
            ),
        }
    )
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr("postgresql+psycopg://worker@db/csight"),
        llm_provider="llama_cpp",
        llm_base_url="https://llm.example.test/v1",
        llm_model_id=identity.served_model_name,
        llm_model_version=identity.model_version,
        llm_model_revision=identity.artifact_revision,
        model_release_enforcement=True,
        model_release_signing_public_key_file="/private/release-key.pub",
        model_release_signing_key_id="release-key-1",
        llm_gguf_runtime_identity=identity,
    )

    assert build_runtime_llm_identity(settings) == identity
    mismatched = settings.model_copy(update={"llm_model_version": "wrong"})
    with pytest.raises(ModelActivationConfigurationError, match="model_version"):
        build_runtime_llm_identity(mismatched)


def test_task_keyed_gguf_identities_preserve_each_prompt_contract() -> None:
    base = gguf_runtime_identity_fixture(gguf_manifest_fixture())
    prompts = {
        ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2: (
            PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
        ),
        ModelReleaseTask.POLICY_QUERY_BUILDER_V1: POLICY_QUERY_BUILDER_PROMPT_V1_1,
        ModelReleaseTask.GROUNDED_POLICY_EXPLANATION_V1: (GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1),
    }
    identities = {
        task: base.model_copy(
            update={
                "prompt_name": prompt.name,
                "prompt_version": prompt.version,
                "prompt_content_hash": prompt.content_hash,
                "input_schema_version": prompt.input_schema_version,
                "output_schema_version": prompt.output_schema_version,
            }
        )
        for task, prompt in prompts.items()
    }
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr("postgresql+psycopg://worker@db/csight"),
        llm_provider="llama_cpp",
        llm_base_url="https://llm.example.test/v1",
        llm_model_id=base.served_model_name,
        llm_model_version=base.model_version,
        llm_model_revision=base.artifact_revision,
        model_release_enforcement=True,
        model_release_signing_public_key_file="/private/release-key.pub",
        model_release_signing_key_id="release-key-1",
        llm_gguf_runtime_identities=identities,
    )

    for task, prompt in prompts.items():
        assert build_runtime_llm_identity(settings, prompt, task) == identities[task]


def test_llama_cpp_route_enforcement_rejects_one_shared_prompt_identity() -> None:
    identity = gguf_runtime_identity_fixture(gguf_manifest_fixture()).model_copy(
        update={
            "prompt_name": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.name,
            "prompt_version": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.version,
            "prompt_content_hash": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.content_hash,
            "input_schema_version": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.input_schema_version,
            "output_schema_version": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.output_schema_version,
        }
    )
    with pytest.raises(ValueError, match="one GGUF runtime identity for each model task"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            database_url=SecretStr("postgresql+psycopg://worker@db/csight"),
            database_runtime_role="worker",
            database_rls_required=True,
            environment="pilot",
            llm_provider="llama_cpp",
            llm_base_url="https://llm.example.test/v1",
            llm_model_id=identity.served_model_name,
            llm_model_version=identity.model_version,
            llm_model_revision=identity.artifact_revision,
            model_release_enforcement=True,
            model_route_enforcement=True,
            model_route_deployment_id="onprem-4090-primary",
            model_release_signing_public_key_file="/private/release-key.pub",
            model_release_signing_key_id="release-key-1",
            llm_gguf_runtime_identity=identity,
        )
