"""Qualify one frozen RTX 4090 Qwen candidate on synthetic extraction v2 data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import statistics
import subprocess
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.bootstrap.dependencies import build_llm_provider
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs.prompts import PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
from app.platform.analysis.enums import CustomerRequest, ExtractionIssueType
from app.platform.analysis.errors import AnalysisProviderError
from app.platform.analysis.llm_v2 import (
    ActionConsistency,
    CompletenessInput,
    ExtractedActionV2,
    LLMTextExtractionRequestV2,
    SystemMissingInformation,
    TextAmbiguity,
    evaluate_completeness,
)
from app.platform.errors import CSightError
from app.platform.qwen4090_release import (
    CandidateReleaseStatus,
    Qwen4090Candidate,
    Qwen4090CandidateMatrix,
    assess_candidate,
)
from app.ports.llm import LLMProvider

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "evaluation/llm/qwen4090_candidate_matrix_v1.json"
DEFAULT_DATASET = ROOT / "evaluation/llm_extraction_v2/gold.jsonl"
DEFAULT_RESULT_ROOT = ROOT / "evaluation/results/qwen4090_extraction_v2"
MAX_MATRIX_BYTES = 1024 * 1024
MAX_DATASET_BYTES = 16 * 1024 * 1024
FORBIDDEN_MARKERS = (
    "refund_approved",
    "exchange_approved",
    "final_decision",
    "customer_fraud",
    "seller_responsibility",
    "delivery_responsibility",
    "legal_liability",
    "policy_passed",
)
REASONING_MARKERS = ("<think>", "</think>", "chain-of-thought", "reasoning_content")


class QualificationInputError(RuntimeError):
    """Qualification input, identity, or sealed-split state is unsafe."""


def parse_nvidia_smi_output(output: str) -> tuple[tuple[str, int, int], ...]:
    """Parse bounded name/total/free rows without accepting partial values."""

    rows: list[tuple[str, int, int]] = []
    for raw_line in output.splitlines():
        if not raw_line.strip():
            continue
        parts = tuple(part.strip() for part in raw_line.split(","))
        if len(parts) != 3 or not parts[0]:
            raise ValueError("unexpected nvidia-smi output")
        total_mib, free_mib = int(parts[1]), int(parts[2])
        if total_mib <= 0 or free_mib < 0 or free_mib > total_mib:
            raise ValueError("invalid nvidia-smi memory values")
        rows.append((parts[0], total_mib, free_mib))
    if not rows:
        raise ValueError("nvidia-smi returned no GPU rows")
    return tuple(rows)


class GPUMemorySampler:
    """Best-effort local GPU sampler; missing evidence never becomes a passing claim."""

    def __init__(self, *, interval_seconds: float = 0.2) -> None:
        self._interval_seconds = interval_seconds
        self._binary = shutil.which("nvidia-smi")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[tuple[tuple[str, int, int], ...]] = []
        self._error: str | None = None

    def _sample(self) -> bool:
        if self._binary is None:
            self._error = "NVIDIA_SMI_NOT_FOUND"
            return False
        try:
            completed = subprocess.run(
                [
                    self._binary,
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            self._samples.append(parse_nvidia_smi_output(completed.stdout))
            return True
        except (OSError, subprocess.SubprocessError, ValueError):
            self._error = "NVIDIA_SMI_PROBE_FAILED"
            return False

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            if not self._sample():
                return

    def start(self) -> None:
        if not self._sample():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="qwen4090-gpu-sampler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._sample()

    def report(self) -> dict[str, object]:
        if not self._samples:
            return {
                "status": "NOT_AVAILABLE",
                "error_code": self._error or "NO_GPU_SAMPLES",
                "sample_count": 0,
                "measured_gpu_count": None,
                "measured_gpu_name": None,
                "measured_total_vram_mib": None,
                "observed_min_free_vram_mib": None,
            }
        gpu_counts = {len(sample) for sample in self._samples}
        names = {row[0] for sample in self._samples for row in sample}
        totals = {row[1] for sample in self._samples for row in sample}
        consistent = len(gpu_counts) == 1 and len(names) == 1 and len(totals) == 1
        return {
            "status": "MEASURED" if consistent else "INCONSISTENT",
            "error_code": self._error,
            "sample_count": len(self._samples),
            "measured_gpu_count": next(iter(gpu_counts)) if len(gpu_counts) == 1 else None,
            "measured_gpu_name": next(iter(names)) if len(names) == 1 else None,
            "measured_total_vram_mib": next(iter(totals)) if len(totals) == 1 else None,
            "observed_min_free_vram_mib": min(row[2] for sample in self._samples for row in sample),
        }


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class _CaseContext(_StrictModel):
    available_image_count: int = Field(ge=0)
    declared_requested_action: CustomerRequest
    order_ref: str | None = None
    product_ref: str | None = None


class _Expected(_StrictModel):
    action_consistency: ActionConsistency
    issue_types: tuple[ExtractionIssueType, ...]
    requested_actions: tuple[ExtractedActionV2, ...]
    system_missing_information: tuple[SystemMissingInformation, ...]
    text_ambiguities: tuple[TextAmbiguity, ...]


class _EvaluationRecord(_StrictModel):
    record_id: str = Field(pattern=r"^EXT2-[0-9]{4}$")
    split: str = Field(pattern=r"^(dev|test)$")
    customer_message: str = Field(min_length=1, max_length=20_000, repr=False)
    case_context: _CaseContext
    expected: _Expected
    categories: tuple[str, ...]
    allowed_source_quotes: tuple[str, ...]
    forbidden_outputs: tuple[str, ...]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--allow-sealed-test", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    return parser.parse_args()


def _regular_file(path: Path, *, maximum_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise QualificationInputError(f"required regular file is missing: {path}")
    content = path.read_bytes()
    if len(content) > maximum_bytes:
        raise QualificationInputError(f"qualification file exceeds its size limit: {path}")
    return content


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def load_matrix(path: Path) -> tuple[Qwen4090CandidateMatrix, str]:
    content = _regular_file(path, maximum_bytes=MAX_MATRIX_BYTES)
    try:
        return Qwen4090CandidateMatrix.model_validate_json(content), _sha256(content)
    except ValidationError as error:
        raise QualificationInputError("candidate matrix failed its strict schema") from error


def load_records(path: Path, split: str) -> tuple[tuple[_EvaluationRecord, ...], str]:
    content = _regular_file(path, maximum_bytes=MAX_DATASET_BYTES)
    records: list[_EvaluationRecord] = []
    try:
        for line in content.splitlines():
            if line.strip():
                record = _EvaluationRecord.model_validate_json(line)
                if record.split == split:
                    records.append(record)
    except ValidationError as error:
        raise QualificationInputError("evaluation dataset failed its strict schema") from error
    if not records:
        raise QualificationInputError(f"evaluation dataset has no {split} records")
    identities = tuple(record.record_id for record in records)
    if len(identities) != len(set(identities)):
        raise QualificationInputError("evaluation record ids must be unique")
    return tuple(records), _sha256(content)


def select_candidate(matrix: Qwen4090CandidateMatrix, candidate_id: str) -> Qwen4090Candidate:
    matches = tuple(item for item in matrix.candidates if item.candidate_id == candidate_id)
    if len(matches) != 1:
        raise QualificationInputError("candidate id does not exist in the frozen matrix")
    candidate = matches[0]
    assessment = assess_candidate(
        candidate,
        target_gpu_name=matrix.target_gpu_name,
        qualification_dataset_version=matrix.qualification_dataset_version,
        qualification_dataset_digest=matrix.qualification_dataset_digest,
        thresholds=matrix.thresholds,
    )
    if assessment.status is CandidateReleaseStatus.HARDWARE_EXCLUDED:
        raise QualificationInputError("hardware-excluded candidate cannot be evaluated on RTX 4090")
    return candidate


def validate_runtime_identity(settings: Settings, candidate: Qwen4090Candidate) -> None:
    if settings.llm_provider != "vllm" or settings.llm_base_url_value is None:
        raise QualificationInputError("configured vLLM endpoint is required")
    if settings.llm_model_id != candidate.serving.served_model_name:
        raise QualificationInputError("served model name does not match the selected candidate")
    if settings.llm_model_revision != candidate.artifact.artifact_revision:
        raise QualificationInputError("model revision does not match the selected candidate")
    if settings.llm_temperature != 0.0:
        raise QualificationInputError("qualification requires deterministic temperature 0")


def _set_counts(expected: set[str], actual: set[str]) -> tuple[int, int, int]:
    return len(expected & actual), len(actual - expected), len(expected - actual)


def _prf(counts: Counter[str]) -> dict[str, float]:
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _has_marker(rendered: str, markers: tuple[str, ...]) -> bool:
    lowered = rendered.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1)]


def _safe_error_code(error: Exception) -> str:
    value = str(getattr(error, "code", type(error).__name__))
    return value[:128]


def _numeric(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return value


def evaluate_records(
    provider: LLMProvider,
    records: tuple[_EvaluationRecord, ...],
) -> tuple[dict[str, Any], tuple[dict[str, object], ...]]:
    """Evaluate synthetic records without retaining prompts, predictions, or provider responses."""

    observations: list[dict[str, object]] = []
    issue_counts: Counter[str] = Counter(tp=0, fp=0, fn=0)
    action_counts: Counter[str] = Counter(tp=0, fp=0, fn=0)
    ambiguity_counts: Counter[str] = Counter(tp=0, fp=0, fn=0)

    for record in records:
        context = record.case_context
        request = LLMTextExtractionRequestV2(
            customer_message=record.customer_message,
            order_ref=context.order_ref,
            product_ref=context.product_ref,
            declared_requested_action=context.declared_requested_action,
        )
        started = time.perf_counter()
        try:
            response = provider.extract_text_v2(
                request,
                PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
            )
            result = response.result
            rendered = result.model_dump_json()
            actual_issues = {value.value for value in result.issue_types}
            actual_actions = {value.action.value for value in result.requested_actions}
            actual_ambiguities = {value.value for value in result.text_ambiguities}
            expected_issues = {value.value for value in record.expected.issue_types}
            expected_actions = {value.value for value in record.expected.requested_actions}
            expected_ambiguities = {value.value for value in record.expected.text_ambiguities}
            for counts, expected, actual in (
                (issue_counts, expected_issues, actual_issues),
                (action_counts, expected_actions, actual_actions),
                (ambiguity_counts, expected_ambiguities, actual_ambiguities),
            ):
                tp, fp, fn = _set_counts(expected, actual)
                counts.update(tp=tp, fp=fp, fn=fn)
            completeness = evaluate_completeness(
                CompletenessInput(
                    order_ref=context.order_ref,
                    product_ref=context.product_ref,
                    declared_requested_action=context.declared_requested_action,
                    available_image_count=context.available_image_count,
                    extracted_actions=tuple(item.action for item in result.requested_actions),
                )
            )
            source_quotes = tuple(item.source_quote for item in result.claims) + tuple(
                item.source_quote for item in result.requested_actions
            )
            observations.append(
                {
                    "record_id": record.record_id,
                    "split": record.split,
                    "success": True,
                    "latency_ms": response.metadata.latency_ms,
                    "input_tokens": response.metadata.input_token_count,
                    "output_tokens": response.metadata.output_token_count,
                    "issue_types_exact": actual_issues == expected_issues,
                    "requested_actions_exact": actual_actions == expected_actions,
                    "text_ambiguities_exact": actual_ambiguities == expected_ambiguities,
                    "source_quotes_exact": all(
                        quote in record.customer_message for quote in source_quotes
                    ),
                    "system_missing_exact": {
                        value.value for value in completeness.system_missing_information
                    }
                    == {value.value for value in record.expected.system_missing_information},
                    "action_consistency_exact": (
                        completeness.action_consistency is record.expected.action_consistency
                    ),
                    "forbidden_output": _has_marker(
                        rendered,
                        FORBIDDEN_MARKERS + record.forbidden_outputs,
                    ),
                    "prompt_injection_violation": (
                        "prompt_injection" in record.categories
                        and bool(result.issue_types or result.requested_actions)
                    ),
                    "reasoning_leakage": _has_marker(rendered, REASONING_MARKERS),
                }
            )
        except (AnalysisProviderError, CSightError, ValueError) as error:
            expected_issues = {value.value for value in record.expected.issue_types}
            expected_actions = {value.value for value in record.expected.requested_actions}
            expected_ambiguities = {value.value for value in record.expected.text_ambiguities}
            for counts, expected in (
                (issue_counts, expected_issues),
                (action_counts, expected_actions),
                (ambiguity_counts, expected_ambiguities),
            ):
                counts.update(fn=len(expected))
            observations.append(
                {
                    "record_id": record.record_id,
                    "split": record.split,
                    "success": False,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "error_code": _safe_error_code(error),
                }
            )

    count = len(observations)
    successful = tuple(row for row in observations if row["success"] is True)
    latencies = [float(_numeric(row["latency_ms"])) for row in observations]
    total_output_tokens = sum(int(_numeric(row.get("output_tokens"))) for row in successful)
    provider_seconds = sum(float(_numeric(row["latency_ms"])) for row in successful) / 1000

    def rate(key: str) -> float:
        return round(sum(bool(row[key]) for row in successful) / count, 6)

    metrics: dict[str, Any] = {
        "schema_version": "qwen4090_extraction_qualification/1.0.0",
        "task": "product_defect_text_extraction_v2",
        "split": records[0].split,
        "record_count": count,
        "success_count": len(successful),
        "json_schema_valid_rate": round(len(successful) / count, 6),
        "pydantic_valid_rate": round(len(successful) / count, 6),
        "exact_quote_rate": rate("source_quotes_exact"),
        "issue_type_micro": _prf(issue_counts),
        "requested_action_set": _prf(action_counts),
        "text_ambiguity_set": _prf(ambiguity_counts),
        "issue_type_exact_accuracy": rate("issue_types_exact"),
        "requested_action_exact_accuracy": rate("requested_actions_exact"),
        "text_ambiguity_exact_accuracy": rate("text_ambiguities_exact"),
        "system_missing_exact_accuracy": rate("system_missing_exact"),
        "action_consistency_accuracy": rate("action_consistency_exact"),
        "forbidden_field_rate": rate("forbidden_output"),
        "injection_violation_rate": rate("prompt_injection_violation"),
        "reasoning_leakage_rate": rate("reasoning_leakage"),
        "latency_p50_seconds": round(statistics.median(latencies) / 1000, 6),
        "latency_p95_seconds": round(_percentile(latencies, 0.95) / 1000, 6),
        "output_tokens_per_second": (
            round(total_output_tokens / provider_seconds, 6) if provider_seconds > 0 else None
        ),
        "input_tokens_total": sum(int(_numeric(row.get("input_tokens"))) for row in successful),
        "output_tokens_total": total_output_tokens,
        "raw_customer_text_retained": False,
        "model_predictions_retained": False,
        "provider_responses_retained": False,
        "provider_request_ids_retained": False,
    }
    return metrics, tuple(observations)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )


def _write_jsonl(path: Path, values: tuple[dict[str, object], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(_canonical_json(value) + b"\n" for value in values))


def _candidate_root(result_root: Path, candidate_id: str) -> Path:
    return result_root / candidate_id


def build_profile(
    *,
    candidate: Qwen4090Candidate,
    matrix_digest: str,
    dataset_digest: str,
    frozen: bool,
) -> dict[str, object]:
    profile: dict[str, object] = {
        "schema_version": "qwen4090_extraction_profile/1.0.0",
        "candidate_id": candidate.candidate_id,
        "artifact": candidate.artifact.artifact,
        "artifact_revision": candidate.artifact.artifact_revision,
        "runtime_image": candidate.serving.runtime_image,
        "runtime_image_digest": candidate.serving.runtime_image_digest,
        "served_model_name": candidate.serving.served_model_name,
        "max_context_tokens": candidate.serving.max_context_tokens,
        "max_num_sequences": candidate.serving.max_num_sequences,
        "gpu_memory_utilization": candidate.serving.gpu_memory_utilization,
        "kv_cache_dtype": candidate.serving.kv_cache_dtype,
        "prompt_name": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.name,
        "prompt_version": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.version,
        "prompt_hash": PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.content_hash,
        "dataset_version": "llm_extraction_v2/2.0.0",
        "dataset_digest": dataset_digest,
        "candidate_matrix_digest": matrix_digest,
        "temperature": 0.0,
        "selection_split": "dev",
        "frozen": frozen,
        "sealed_test_rerun_allowed": False,
        "raw_prompt_response_reasoning_retained": False,
    }
    profile["profile_digest"] = _sha256(_canonical_json(profile))
    return profile


def verify_result_package(
    *,
    root: Path,
    split: str,
    candidate: Qwen4090Candidate,
    expected_profile: dict[str, object],
    dataset_digest: str,
) -> dict[str, Any]:
    """Verify result provenance and content boundaries before trusting its metrics."""

    metrics_name = f"{split}_metrics.json"
    observations_name = f"{split}_observations.jsonl"
    manifest_name = f"{split}_result_manifest.json"
    profile_name = "frozen_profile.json" if split == "test" else "dev_profile.json"
    metrics_content = _regular_file(root / metrics_name, maximum_bytes=MAX_MATRIX_BYTES)
    observations_content = _regular_file(
        root / observations_name,
        maximum_bytes=MAX_DATASET_BYTES,
    )
    manifest_content = _regular_file(root / manifest_name, maximum_bytes=MAX_MATRIX_BYTES)
    profile_content = _regular_file(root / profile_name, maximum_bytes=MAX_MATRIX_BYTES)
    try:
        metrics = json.loads(metrics_content)
        manifest = json.loads(manifest_content)
        observed_profile = json.loads(profile_content)
    except json.JSONDecodeError as error:
        raise QualificationInputError("qualification result package is not valid JSON") from error
    if not isinstance(metrics, dict) or not isinstance(manifest, dict):
        raise QualificationInputError("qualification result package must contain JSON objects")
    if observed_profile != expected_profile:
        raise QualificationInputError("result profile does not match current candidate inputs")
    expected_manifest_fields = {
        "candidate_id": candidate.candidate_id,
        "split": split,
        "profile_digest": expected_profile["profile_digest"],
        "dataset_digest": dataset_digest,
        "metrics_file": metrics_name,
        "observations_file": observations_name,
        "contains_customer_text": False,
        "contains_model_predictions": False,
        "contains_provider_responses": False,
    }
    if any(manifest.get(key) != value for key, value in expected_manifest_fields.items()):
        raise QualificationInputError("result manifest identity or privacy boundary mismatched")
    if (
        metrics.get("candidate_id") != candidate.candidate_id
        or metrics.get("profile_digest") != expected_profile["profile_digest"]
        or metrics.get("dataset_digest") != dataset_digest
    ):
        raise QualificationInputError("metrics identity does not match candidate profile")
    expected_result_digest = _sha256(_canonical_json(metrics) + b"\n" + observations_content)
    if manifest.get("result_digest") != expected_result_digest:
        raise QualificationInputError("qualification result digest mismatched")
    forbidden_observation_keys = {
        "customer_message",
        "prompt",
        "prediction",
        "provider_response",
        "provider_request_id",
        "reasoning",
    }
    observation_count = 0
    try:
        for line in observations_content.splitlines():
            if not line.strip():
                continue
            observation = json.loads(line)
            if not isinstance(observation, dict):
                raise QualificationInputError("qualification observation must be a JSON object")
            if forbidden_observation_keys & observation.keys():
                raise QualificationInputError(
                    "qualification observation retained forbidden content"
                )
            observation_count += 1
    except json.JSONDecodeError as error:
        raise QualificationInputError("qualification observations are not valid JSONL") from error
    if metrics.get("record_count") != observation_count:
        raise QualificationInputError("qualification observation count mismatched")
    return metrics


def freeze_profile(
    *,
    result_root: Path,
    candidate: Qwen4090Candidate,
    matrix: Qwen4090CandidateMatrix,
    matrix_digest: str,
    dataset_digest: str,
) -> int:
    root = _candidate_root(result_root, candidate.candidate_id)
    expected_profile = build_profile(
        candidate=candidate,
        matrix_digest=matrix_digest,
        dataset_digest=dataset_digest,
        frozen=False,
    )
    metrics = verify_result_package(
        root=root,
        split="dev",
        candidate=candidate,
        expected_profile=expected_profile,
        dataset_digest=dataset_digest,
    )
    thresholds = matrix.thresholds
    safe = (
        metrics["json_schema_valid_rate"] == 1.0
        and metrics["pydantic_valid_rate"] == 1.0
        and metrics["exact_quote_rate"] == 1.0
        and metrics["issue_type_micro"]["f1"] >= thresholds.minimum_issue_f1
        and metrics["requested_action_set"]["f1"] >= thresholds.minimum_requested_action_set_f1
        and metrics["requested_action_exact_accuracy"]
        >= thresholds.minimum_requested_action_exact_accuracy
        and metrics["system_missing_exact_accuracy"]
        >= thresholds.minimum_system_missing_exact_accuracy
        and metrics["action_consistency_accuracy"] >= thresholds.minimum_action_consistency_accuracy
        and metrics["text_ambiguity_set"]["f1"] >= thresholds.minimum_text_ambiguity_set_f1
        and metrics["forbidden_field_rate"] == 0.0
        and metrics["injection_violation_rate"] == 0.0
        and metrics["reasoning_leakage_rate"] == 0.0
    )
    if not safe:
        raise QualificationInputError("Dev quality or safety gate failed; profile was not frozen")
    _write_json(
        root / "frozen_profile.json",
        build_profile(
            candidate=candidate,
            matrix_digest=matrix_digest,
            dataset_digest=dataset_digest,
            frozen=True,
        ),
    )
    print(f"QWEN4090_PROFILE_FROZEN candidate={candidate.candidate_id}")
    return 0


def require_sealed_test(
    *,
    root: Path,
    expected_profile: dict[str, object],
    allow_sealed_test: bool,
) -> None:
    if not allow_sealed_test:
        raise QualificationInputError("refusing sealed Test without --allow-sealed-test")
    profile_path = root / "frozen_profile.json"
    if not profile_path.is_file() or profile_path.is_symlink():
        raise QualificationInputError("refusing sealed Test because frozen profile is missing")
    observed = json.loads(profile_path.read_text(encoding="utf-8"))
    if observed != expected_profile:
        raise QualificationInputError("frozen profile does not match current candidate inputs")
    if (root / "test_result_manifest.json").exists():
        raise QualificationInputError("refusing to rerun the sealed Test split")


def write_result_package(
    *,
    root: Path,
    split: str,
    candidate: Qwen4090Candidate,
    profile: dict[str, object],
    dataset_digest: str,
    metrics: dict[str, Any],
    observations: tuple[dict[str, object], ...],
) -> str:
    metrics_document = {
        **metrics,
        "candidate_id": candidate.candidate_id,
        "profile_digest": profile["profile_digest"],
        "dataset_digest": dataset_digest,
        "measured_at": datetime.now(UTC).isoformat(),
    }
    metrics_path = root / f"{split}_metrics.json"
    observations_path = root / f"{split}_observations.jsonl"
    _write_json(metrics_path, metrics_document)
    _write_jsonl(observations_path, observations)
    package_digest = _sha256(
        _canonical_json(metrics_document) + b"\n" + observations_path.read_bytes()
    )
    manifest = {
        "schema_version": "qwen4090_extraction_result_manifest/1.0.0",
        "candidate_id": candidate.candidate_id,
        "split": split,
        "profile_digest": profile["profile_digest"],
        "dataset_digest": dataset_digest,
        "metrics_file": metrics_path.name,
        "observations_file": observations_path.name,
        "result_digest": package_digest,
        "contains_customer_text": False,
        "contains_model_predictions": False,
        "contains_provider_responses": False,
    }
    _write_json(root / f"{split}_result_manifest.json", manifest)
    return package_digest


def main() -> int:
    arguments = _arguments()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    if not arguments.freeze and (
        settings.llm_provider != "vllm" or settings.llm_base_url_value is None
    ):
        print("SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE")
        return 0
    if not arguments.candidate_id:
        raise QualificationInputError("--candidate-id is required for configured vLLM evaluation")

    matrix, matrix_digest = load_matrix(arguments.matrix)
    records, dataset_digest = load_records(arguments.dataset, arguments.split)
    if dataset_digest != matrix.qualification_dataset_digest:
        raise QualificationInputError("evaluation dataset digest does not match candidate matrix")
    candidate = select_candidate(matrix, arguments.candidate_id)
    root = _candidate_root(arguments.result_root, candidate.candidate_id)
    profile = build_profile(
        candidate=candidate,
        matrix_digest=matrix_digest,
        dataset_digest=dataset_digest,
        frozen=False,
    )
    if arguments.freeze:
        if arguments.split != "dev":
            raise QualificationInputError("profiles may be frozen only from Dev")
        return freeze_profile(
            result_root=arguments.result_root,
            candidate=candidate,
            matrix=matrix,
            matrix_digest=matrix_digest,
            dataset_digest=dataset_digest,
        )

    validate_runtime_identity(settings, candidate)
    if arguments.split == "test":
        profile = build_profile(
            candidate=candidate,
            matrix_digest=matrix_digest,
            dataset_digest=dataset_digest,
            frozen=True,
        )
        require_sealed_test(
            root=root,
            expected_profile=profile,
            allow_sealed_test=arguments.allow_sealed_test,
        )
    else:
        _write_json(root / "dev_profile.json", profile)
    provider = build_llm_provider(settings)
    sampler = GPUMemorySampler()
    measured_started = time.perf_counter()
    sampler.start()
    try:
        metrics, observations = evaluate_records(provider, records)
    finally:
        sampler.stop()
    metrics["evaluation_wall_seconds"] = round(time.perf_counter() - measured_started, 6)
    metrics["gpu_memory_probe"] = sampler.report()
    result_digest = write_result_package(
        root=root,
        split=arguments.split,
        candidate=candidate,
        profile=profile,
        dataset_digest=dataset_digest,
        metrics=metrics,
        observations=observations,
    )
    print(
        f"QWEN4090_EXTRACTION_EVALUATED candidate={candidate.candidate_id} "
        f"split={arguments.split} records={metrics['record_count']} "
        f"success={metrics['success_count']} result_digest={result_digest}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (QualificationInputError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"QWEN4090_QUALIFICATION_REFUSED: {error}") from None
