from __future__ import annotations

import json
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from app.platform.candidate_evaluation import CandidateEvaluationProfile
from scripts import run_qwen4090_candidate_dev as driver

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "a" * 64
CANDIDATE_ID = "qwen38-27b-csight-q4-k-m-llama-cpp"


def _candidate():
    return driver.evaluator.load_evaluation_candidate(driver.DEFAULT_MATRIX, CANDIDATE_ID)


def _task_summary(task: str) -> driver.CandidateDevTaskSummary:
    return driver.CandidateDevTaskSummary(
        task=task,  # type: ignore[arg-type]
        gate_passed=True,
        record_count=1,
        success_count=1,
        profile_digest=DIGEST,
        observation_evidence_digest=DIGEST,
        metrics_digest=DIGEST,
        gate_digest=DIGEST,
    )


def _execution_manifest(
    candidate_id: str,
    *,
    distribution_digest: str = DIGEST,
    python_version: str = "3.12.11",
) -> driver.CandidateDevExecutionManifest:
    candidate = driver.evaluator.load_evaluation_candidate(driver.DEFAULT_MATRIX, candidate_id)
    return driver.CandidateDevExecutionManifest(
        candidate_id=candidate.candidate_id,
        candidate_identity_digest=candidate.identity_digest,
        local_dev_identity_digest=DIGEST,
        local_dev_preflight_evidence_digest=DIGEST,
        candidate_matrix_digest=DIGEST,
        source_bundle_digest=DIGEST,
        dependency_lock_digest=DIGEST,
        installed_distribution_digest=distribution_digest,
        python_version=python_version,
        endpoint_identity_digest=DIGEST,
        started_at=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, 0, 1, tzinfo=UTC),
        tasks=tuple(_task_summary(task) for task in driver._TASKS),  # pyright: ignore[reportPrivateUsage,reportArgumentType]
        all_task_gates_passed=True,
    )


def _evaluation_values() -> dict[str, str]:
    candidate = _candidate()
    return {
        "ENVIRONMENT": "local",
        "LLM_PROVIDER": "llama_cpp",
        "LLM_BASE_URL": "http://100.116.246.125:18002/v1",
        "LLM_API_KEY": "candidate-dev-key-with-enough-private-entropy-123",
        "LLM_MODEL_ID": candidate.served_model_name,
        "LLM_MODEL_VERSION": candidate.candidate_id,
        "LLM_MAX_OUTPUT_TOKENS": str(candidate.max_output_tokens),
        "LLM_TEMPERATURE": "0",
        "LLM_TLS_VERIFY": "false",
        "LLM_TASK_RUNTIMES": "{}",
        "MODEL_RELEASE_ENFORCEMENT": "false",
        "MODEL_ROUTE_ENFORCEMENT": "false",
        "DATABASE_URL": "postgresql+psycopg://local:test@127.0.0.1:5432/csight",
        "EMBEDDING_BASE_URL": "http://127.0.0.1:8091",
    }


def _post_start_evidence() -> driver.LocalDevPostStartEvidence:
    matrix = driver.evaluator._load_json(  # pyright: ignore[reportPrivateUsage]
        driver.DEFAULT_MATRIX,
        driver.evaluator.Qwen4090CandidateMatrixV2,
    )
    candidate = next(item for item in matrix.candidates if item.candidate_id == CANDIDATE_ID)
    identity = driver.LocalUnpublishedGGUFDevIdentity.from_candidate(
        candidate,
        candidate_matrix_digest=matrix.matrix_digest,
        quantization_run_evidence_digest=DIGEST,
    )
    return driver.LocalDevPostStartEvidence(
        schema_version="qwen4090_local_gguf_dev_post_start/1.0.0",
        status="DEV_LOCAL_RUNNING",
        candidate_id=candidate.candidate_id,
        candidate_matrix_digest=matrix.matrix_digest,
        local_dev_identity_digest=identity.identity_digest,
        artifact_revision=None,
        artifact_content_digest=identity.artifact_content_digest,
        artifact_weight_bytes=identity.artifact_weight_bytes,
        quantization_run_evidence_digest=identity.quantization_run_evidence_digest,
        runtime_image_digest=identity.runtime_image_digest,
        runtime_binary_digest=identity.runtime_binary_digest,
        runtime_build_manifest_digest=identity.runtime_build_manifest_digest,
        sbom_digest=identity.sbom_digest,
        llama_cpp_revision=identity.llama_cpp_revision,
        served_model_name=identity.served_model_name,
        compose_config_digest=DIGEST,
        container_inspect_digest=DIGEST,
        container_instance_digest=DIGEST,
        authenticated_canary=True,
        release_eligible=False,
        primary_allowed=False,
        core_routing_allowed=False,
        sealed_test_allowed=False,
    )


def test_evaluation_env_binds_remote_candidate_and_mac_local_retrieval() -> None:
    endpoint = driver._validate_evaluation_env(  # pyright: ignore[reportPrivateUsage]
        _evaluation_values(),
        candidate=_candidate(),
    )

    assert endpoint.hostname == "100.116.246.125"
    assert endpoint.port == 18002


@pytest.mark.parametrize(
    ("name", "value", "code"),
    (
        ("LLM_MODEL_REVISION", "1" * 40, "RELEASE_IDENTITY_FORBIDDEN"),
        ("LLM_TASK_RUNTIMES", '{"POLICY_QUERY_BUILDER_V1":{}}', "TASK_RUNTIME_OVERRIDE_FORBIDDEN"),
        ("MODEL_ROUTE_ENFORCEMENT", "true", "ROUTING_FORBIDDEN"),
        ("LLM_BASE_URL", "http://127.0.0.1:18002/v1", "LLM_ENDPOINT_INVALID"),
        (
            "DATABASE_URL",
            "postgresql+psycopg://local:test@100.64.0.2:5432/csight",
            "LOCAL_RETRIEVAL_INVALID",
        ),
        ("EMBEDDING_BASE_URL", "http://100.64.0.2:8091", "LOCAL_RETRIEVAL_INVALID"),
    ),
)
def test_evaluation_env_rejects_release_overrides_and_remote_retrieval(
    name: str,
    value: str,
    code: str,
) -> None:
    values = _evaluation_values()
    values[name] = value

    with pytest.raises(driver.CandidateDevDriverError) as captured:
        driver._validate_evaluation_env(  # pyright: ignore[reportPrivateUsage]
            values,
            candidate=_candidate(),
        )

    assert captured.value.code == code


def test_post_start_evidence_recomputes_local_identity_and_binds_matrix(
    tmp_path: Path,
) -> None:
    path = tmp_path / "post-start.json"
    evidence = _post_start_evidence()
    path.write_text(evidence.model_dump_json(), encoding="utf-8")
    path.chmod(0o600)

    loaded, digest = driver._validate_local_dev_preflight_evidence(  # pyright: ignore[reportPrivateUsage]
        path,
        matrix=driver.DEFAULT_MATRIX,
        candidate=_candidate(),
    )

    assert loaded.local_dev_identity_digest == evidence.local_dev_identity_digest
    assert digest.startswith("sha256:")

    path.write_text(
        evidence.model_copy(update={"local_dev_identity_digest": DIGEST}).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(driver.CandidateDevDriverError) as mismatch:
        driver._validate_local_dev_preflight_evidence(  # pyright: ignore[reportPrivateUsage]
            path,
            matrix=driver.DEFAULT_MATRIX,
            candidate=_candidate(),
        )
    assert mismatch.value.code == "LOCAL_DEV_PREFLIGHT_MISMATCH"


def test_private_evaluation_env_requires_exact_mode_and_unique_keys(tmp_path: Path) -> None:
    env_file = tmp_path / "evaluation.env"
    env_file.write_text("ENVIRONMENT=local\nENVIRONMENT=local\n", encoding="utf-8")
    env_file.chmod(0o600)

    with pytest.raises(driver.CandidateDevDriverError) as duplicate:
        driver._private_env(env_file)  # pyright: ignore[reportPrivateUsage]
    assert duplicate.value.code == "EVALUATION_ENV_INVALID"

    env_file.write_text("ENVIRONMENT=local\n", encoding="utf-8")
    env_file.chmod(0o644)
    with pytest.raises(driver.CandidateDevDriverError) as public:
        driver._private_env(env_file)  # pyright: ignore[reportPrivateUsage]
    assert public.value.code == "EVALUATION_ENV_INVALID"


def test_private_evaluation_env_rejects_every_non_allowlisted_key(tmp_path: Path) -> None:
    env_file = tmp_path / "evaluation.env"
    values = _evaluation_values()
    env_file.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )
    env_file.chmod(0o600)

    assert driver._private_env(env_file) == values  # pyright: ignore[reportPrivateUsage]

    values["MINIO_SECRET_KEY"] = "must-never-enter-the-evaluator"
    env_file.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )
    env_file.chmod(0o600)

    with pytest.raises(driver.CandidateDevDriverError) as forbidden:
        driver._private_env(env_file)  # pyright: ignore[reportPrivateUsage]

    assert forbidden.value.code == "EVALUATION_ENV_KEY_FORBIDDEN"
    assert "MINIO_SECRET_KEY" not in str(forbidden.value)


def test_child_environment_does_not_inherit_application_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "must-not-cross-the-process-boundary")
    monkeypatch.setenv("DATABASE_URL", "must-not-cross-the-process-boundary")

    child = driver._child_environment()  # pyright: ignore[reportPrivateUsage]

    assert "LLM_API_KEY" not in child
    assert "DATABASE_URL" not in child
    assert child["UV_OFFLINE"] == "1"
    assert child["HF_HUB_OFFLINE"] == "1"


def test_task_process_treats_gate_failure_as_completed_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        signal = (
            "CANDIDATE_TASK_EVALUATED "
            f"candidate={CANDIDATE_ID} "
            "task=PRODUCT_DEFECT_TEXT_EXTRACTION_V2 split=dev passed=false\n"
        ).encode()
        return subprocess.CompletedProcess(command, 1, stdout=signal, stderr=b"")

    monkeypatch.setattr(driver.subprocess, "run", fake_run)

    return_code = driver._run_task_process(  # pyright: ignore[reportPrivateUsage]
        task="extraction",
        candidate_id=CANDIDATE_ID,
        matrix=driver.DEFAULT_MATRIX,
        evaluation_env=tmp_path / "evaluation.env",
        result_root=tmp_path,
        timeout_seconds=60,
    )

    assert return_code == 1
    command = cast(list[str], captured["command"])
    environment = cast(dict[str, str], captured["env"])
    assert "--generate-live" in command
    assert "--freeze" not in command
    assert "--allow-sealed-test" not in command
    assert environment["UV_OFFLINE"] == "1"


def test_task_process_rejects_exit_one_without_safe_completion_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def crashed_evaluator(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        return subprocess.CompletedProcess(command, 1, b"", b"Traceback (redacted)")

    monkeypatch.setattr(driver.subprocess, "run", crashed_evaluator)

    with pytest.raises(driver.CandidateDevDriverError) as captured:
        driver._run_task_process(  # pyright: ignore[reportPrivateUsage]
            task="grounding",
            candidate_id=CANDIDATE_ID,
            matrix=driver.DEFAULT_MATRIX,
            evaluation_env=tmp_path / "evaluation.env",
            result_root=tmp_path,
            timeout_seconds=60,
        )

    assert captured.value.code == "TASK_EXECUTION_FAILED"


def test_task_process_rejects_technical_failure_without_replaying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def technical_failure(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        return subprocess.CompletedProcess(command, 2, b"", b"technical")

    monkeypatch.setattr(
        driver.subprocess,
        "run",
        technical_failure,
    )

    with pytest.raises(driver.CandidateDevDriverError) as captured:
        driver._run_task_process(  # pyright: ignore[reportPrivateUsage]
            task="grounding",
            candidate_id=CANDIDATE_ID,
            matrix=driver.DEFAULT_MATRIX,
            evaluation_env=tmp_path / "evaluation.env",
            result_root=tmp_path,
            timeout_seconds=60,
        )

    assert captured.value.code == "TASK_EXECUTION_FAILED"


def test_execution_manifest_is_dev_only_and_requires_frozen_task_order() -> None:
    candidate = _candidate()
    profile = driver.evaluator._profile(  # pyright: ignore[reportPrivateUsage]
        "extraction",
        candidate,
    )
    assert isinstance(profile, CandidateEvaluationProfile)

    manifest = _execution_manifest(candidate.candidate_id)

    assert manifest.execution_scope == "DEV_LOCAL"
    assert manifest.artifact_revision is None
    assert manifest.sealed_test_used is False
    assert manifest.release_eligible is False
    assert manifest.external_business_actions_performed is False
    assert manifest.raw_customer_data_retained is False


@pytest.mark.parametrize(
    ("distribution_digest", "python_version"),
    (("sha256:" + "b" * 64, "3.12.11"), (DIGEST, "3.12.12")),
)
def test_selection_rejects_candidate_runtime_drift(
    tmp_path: Path,
    distribution_digest: str,
    python_version: str,
) -> None:
    matrix = driver.evaluator._load_json(  # pyright: ignore[reportPrivateUsage]
        driver.DEFAULT_MATRIX,
        driver.evaluator.Qwen4090CandidateMatrixV2,
    )
    for index, candidate in enumerate(matrix.candidates):
        candidate_root = tmp_path / candidate.candidate_id
        candidate_root.mkdir(mode=0o700)
        manifest = _execution_manifest(
            candidate.candidate_id,
            distribution_digest=distribution_digest if index else DIGEST,
            python_version=python_version if index else "3.12.11",
        )
        path = candidate_root / "candidate_dev_execution.json"
        path.write_text(manifest.model_dump_json(), encoding="utf-8")
        path.chmod(0o600)

    with pytest.raises(driver.CandidateDevDriverError) as mismatch:
        driver._candidate_execution_manifests(  # pyright: ignore[reportPrivateUsage]
            matrix=driver.DEFAULT_MATRIX,
            result_root=tmp_path,
            matrix_digest=DIGEST,
            source_digest=DIGEST,
            lock_digest=DIGEST,
            distribution_digest=DIGEST,
            python_version="3.12.11",
        )

    assert mismatch.value.code == "CANDIDATE_EXECUTION_BINDING_INVALID"


def test_source_bundle_and_input_digest_report_are_privacy_safe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert driver.source_bundle_digest().startswith("sha256:")

    assert driver.input_digests(driver.DEFAULT_MATRIX) == 0
    report = json.loads(capsys.readouterr().out)

    assert set(report) == {
        "schema_version",
        "candidate_matrix_digest",
        "source_bundle_digest",
        "dependency_lock_digest",
    }
    assert all("/Users/" not in str(value) for value in report.values())


def test_completion_sentinel_is_owner_only_one_shot_and_shell_valid(tmp_path: Path) -> None:
    script = ROOT / "infra/llm/qwen4090_candidate_dev_completion.sh"
    parent = tmp_path / "sentinels"
    parent.mkdir(mode=0o700)
    parent.chmod(0o700)
    state = parent / "run-1"

    subprocess.run(
        [str(script), "prepare", CANDIDATE_ID, str(state)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert stat.S_IMODE((state / "request.tsv").stat().st_mode) == 0o600

    subprocess.run(
        [str(script), "complete", CANDIDATE_ID, str(state), "COMPLETE", DIGEST],
        check=True,
        capture_output=True,
        text=True,
    )
    completed = subprocess.run(
        [str(script), "wait", CANDIDATE_ID, str(state), "60"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "status=COMPLETE" in completed.stdout
    assert stat.S_IMODE((state / "completion.tsv").stat().st_mode) == 0o600

    duplicate = subprocess.run(
        [str(script), "complete", CANDIDATE_ID, str(state), "COMPLETE", DIGEST],
        check=False,
        capture_output=True,
        text=True,
    )
    assert duplicate.returncode == 2
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_completion_sentinel_propagates_failed_dev_status(tmp_path: Path) -> None:
    script = ROOT / "infra/llm/qwen4090_candidate_dev_completion.sh"
    parent = tmp_path / "sentinels"
    parent.mkdir(mode=0o700)
    parent.chmod(0o700)
    state = parent / "run-failed"
    subprocess.run(
        [str(script), "prepare", CANDIDATE_ID, str(state)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [str(script), "complete", CANDIDATE_ID, str(state), "FAILED", DIGEST],
        check=True,
        capture_output=True,
        text=True,
    )

    failed = subprocess.run(
        [str(script), "wait", CANDIDATE_ID, str(state), "60"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert failed.returncode == 1
    assert "status=FAILED" in failed.stdout
