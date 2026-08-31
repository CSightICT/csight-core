"""RTX 4090 Qwen extraction qualification harness tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.llm import MockLLMProvider
from app.bootstrap.settings import Settings
from app.platform.qwen4090_release import Qwen4090Candidate
from scripts.evaluate_extraction_v2_qwen import (
    DEFAULT_DATASET,
    DEFAULT_MATRIX,
    GPUMemorySampler,
    QualificationInputError,
    build_profile,
    evaluate_records,
    freeze_profile,
    load_matrix,
    load_records,
    parse_nvidia_smi_output,
    require_sealed_test,
    select_candidate,
    validate_runtime_identity,
    verify_result_package,
    write_result_package,
)

pytestmark = pytest.mark.unit

BASELINE_ID = "qwen38-27b-awq-int4-community-vllm026"


def _candidate():
    matrix, matrix_digest = load_matrix(DEFAULT_MATRIX)
    return matrix, matrix_digest, select_candidate(matrix, BASELINE_ID)


def _passing_metrics() -> dict[str, object]:
    return {
        "record_count": 1,
        "json_schema_valid_rate": 1.0,
        "pydantic_valid_rate": 1.0,
        "exact_quote_rate": 1.0,
        "issue_type_micro": {"f1": 0.95},
        "requested_action_set": {"f1": 0.9},
        "requested_action_exact_accuracy": 0.85,
        "system_missing_exact_accuracy": 0.98,
        "action_consistency_accuracy": 0.95,
        "text_ambiguity_set": {"f1": 0.75},
        "forbidden_field_rate": 0.0,
        "injection_violation_rate": 0.0,
        "reasoning_leakage_rate": 0.0,
    }


def _write_dev_package(
    *,
    root: Path,
    candidate: Qwen4090Candidate,
    matrix_digest: str,
    dataset_digest: str,
    metrics: dict[str, object],
) -> dict[str, object]:
    profile = build_profile(
        candidate=candidate,
        matrix_digest=matrix_digest,
        dataset_digest=dataset_digest,
        frozen=False,
    )
    root.mkdir(parents=True)
    (root / "dev_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_result_package(
        root=root,
        split="dev",
        candidate=candidate,
        profile=profile,
        dataset_digest=dataset_digest,
        metrics=metrics,
        observations=(
            {"record_id": "EXT2-0001", "split": "dev", "success": True, "latency_ms": 1},
        ),
    )
    return profile


def test_frozen_dataset_is_strict_and_matches_candidate_matrix() -> None:
    matrix, _matrix_digest = load_matrix(DEFAULT_MATRIX)
    dev, digest = load_records(DEFAULT_DATASET, "dev")
    test, test_digest = load_records(DEFAULT_DATASET, "test")

    assert len(dev) == 120
    assert len(test) == 40
    assert digest == test_digest == matrix.qualification_dataset_digest


def test_nvidia_smi_parser_is_strict_and_sampler_fails_closed() -> None:
    assert parse_nvidia_smi_output("NVIDIA GeForce RTX 4090, 24564, 2048\n") == (
        ("NVIDIA GeForce RTX 4090", 24564, 2048),
    )
    with pytest.raises(ValueError, match="memory values"):
        parse_nvidia_smi_output("NVIDIA GeForce RTX 4090, 24564, 30000\n")

    sampler = GPUMemorySampler()
    sampler._binary = None  # pyright: ignore[reportPrivateUsage]
    sampler.start()
    sampler.stop()
    report = sampler.report()
    assert report["status"] == "NOT_AVAILABLE"
    assert report["observed_min_free_vram_mib"] is None


def test_hardware_excluded_candidate_cannot_be_selected() -> None:
    matrix, _matrix_digest = load_matrix(DEFAULT_MATRIX)

    with pytest.raises(QualificationInputError, match="hardware-excluded"):
        select_candidate(matrix, "qwen38-27b-bf16-official-preflight")


def test_runtime_identity_must_match_selected_candidate() -> None:
    _matrix, _matrix_digest, candidate = _candidate()
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        llm_provider="vllm",
        llm_base_url="http://127.0.0.1:18000/v1",
        llm_model_id=candidate.serving.served_model_name,
        llm_model_version="qualification",
        llm_model_revision=candidate.artifact.artifact_revision,
        llm_temperature=0.0,
    )

    validate_runtime_identity(settings, candidate)

    mismatched = settings.model_copy(update={"llm_model_id": "wrong-model"})
    with pytest.raises(QualificationInputError, match="served model name"):
        validate_runtime_identity(mismatched, candidate)


def test_evaluator_retains_only_privacy_safe_observations() -> None:
    records, _digest = load_records(DEFAULT_DATASET, "dev")
    record = records[0]

    metrics, observations = evaluate_records(MockLLMProvider(), (record,))

    serialized = json.dumps(observations, ensure_ascii=False)
    assert record.customer_message not in serialized
    assert "prediction" not in serialized
    assert "provider_request_id" not in serialized
    assert metrics["record_count"] == 1
    assert metrics["raw_customer_text_retained"] is False
    assert metrics["model_predictions_retained"] is False
    assert metrics["provider_responses_retained"] is False


def test_result_package_contains_digests_but_no_predictions(
    tmp_path: Path,
) -> None:
    matrix, matrix_digest, candidate = _candidate()
    records, dataset_digest = load_records(DEFAULT_DATASET, "dev")
    metrics, observations = evaluate_records(MockLLMProvider(), (records[0],))
    profile = build_profile(
        candidate=candidate,
        matrix_digest=matrix_digest,
        dataset_digest=dataset_digest,
        frozen=False,
    )

    digest = write_result_package(
        root=tmp_path,
        split="dev",
        candidate=candidate,
        profile=profile,
        dataset_digest=dataset_digest,
        metrics=metrics,
        observations=observations,
    )

    assert digest.startswith("sha256:")
    assert len(digest) == 71
    persisted = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.iterdir())
    assert records[0].customer_message not in persisted
    assert '"prediction"' not in persisted
    manifest = json.loads((tmp_path / "dev_result_manifest.json").read_text(encoding="utf-8"))
    assert manifest["contains_customer_text"] is False
    assert manifest["contains_model_predictions"] is False
    assert manifest["result_digest"] == digest
    assert matrix.qualification_dataset_digest == dataset_digest


def test_dev_must_pass_before_freeze_and_test_is_single_use(tmp_path: Path) -> None:
    matrix, matrix_digest, candidate = _candidate()
    _records, dataset_digest = load_records(DEFAULT_DATASET, "dev")
    root = tmp_path / candidate.candidate_id
    _write_dev_package(
        root=root,
        candidate=candidate,
        matrix_digest=matrix_digest,
        dataset_digest=dataset_digest,
        metrics=_passing_metrics(),
    )

    assert (
        freeze_profile(
            result_root=tmp_path,
            candidate=candidate,
            matrix=matrix,
            matrix_digest=matrix_digest,
            dataset_digest=dataset_digest,
        )
        == 0
    )
    frozen = build_profile(
        candidate=candidate,
        matrix_digest=matrix_digest,
        dataset_digest=dataset_digest,
        frozen=True,
    )
    require_sealed_test(root=root, expected_profile=frozen, allow_sealed_test=True)

    (root / "test_result_manifest.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(QualificationInputError, match="rerun"):
        require_sealed_test(root=root, expected_profile=frozen, allow_sealed_test=True)


def test_failed_dev_gate_does_not_freeze_profile(tmp_path: Path) -> None:
    matrix, matrix_digest, candidate = _candidate()
    _records, dataset_digest = load_records(DEFAULT_DATASET, "dev")
    root = tmp_path / candidate.candidate_id
    failed = _passing_metrics() | {"injection_violation_rate": 0.01}
    _write_dev_package(
        root=root,
        candidate=candidate,
        matrix_digest=matrix_digest,
        dataset_digest=dataset_digest,
        metrics=failed,
    )

    with pytest.raises(QualificationInputError, match="not frozen"):
        freeze_profile(
            result_root=tmp_path,
            candidate=candidate,
            matrix=matrix,
            matrix_digest=matrix_digest,
            dataset_digest=dataset_digest,
        )

    assert not (root / "frozen_profile.json").exists()


def test_tampered_result_digest_is_rejected(tmp_path: Path) -> None:
    _matrix, matrix_digest, candidate = _candidate()
    _records, dataset_digest = load_records(DEFAULT_DATASET, "dev")
    root = tmp_path / candidate.candidate_id
    profile = _write_dev_package(
        root=root,
        candidate=candidate,
        matrix_digest=matrix_digest,
        dataset_digest=dataset_digest,
        metrics=_passing_metrics(),
    )
    with (root / "dev_observations.jsonl").open("a", encoding="utf-8") as stream:
        stream.write('{"record_id":"tampered","success":true}\n')

    with pytest.raises(QualificationInputError, match="digest mismatched"):
        verify_result_package(
            root=root,
            split="dev",
            candidate=candidate,
            expected_profile=profile,
            dataset_digest=dataset_digest,
        )
