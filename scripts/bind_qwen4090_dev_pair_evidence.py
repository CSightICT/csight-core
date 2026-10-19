"""Bind one clean local GGUF Dev pair to candidate-matrix v2, without promotion.

The binder is deliberately narrower than a general matrix editor.  It accepts
only the two audited ``DEV_QUALIFICATION_PAIR`` recipes, proves that their run
plan used the clean importance matrix and the exact llama.cpp build, and then
changes only content/runtime identity fields.  Publication revision and model
qualification remain null, so the release assessment must stay fail closed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.platform.quantization_assets import (
    FinalCandidateSet,
    LlamaCppQuantizationRunPlan,
    QuantizationRecipeName,
)
from app.platform.qwen4090_gguf import (
    CandidateReleaseStatusV2,
    GGUFQuantizationVariant,
    Qwen4090CandidateMatrixV2,
    assess_gguf_matrix,
)
from scripts.qwen4090_imatrix_maintenance import (
    LlamaCppBuildManifest,
    canonical_command_contract_digest,
    imatrix_command_contract,
)
from scripts.run_qwen38_quantization_plan import load_run_plan
from scripts.verify_qwen4090_gguf_candidates import DEFAULT_MATRIX

MAX_JSON_BYTES = 128 * 1024 * 1024
WRITE_CONFIRMATION = "BIND_DEV_QUALIFICATION_PAIR"
_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_DIGEST = re.compile(_DIGEST_PATTERN)
_RUNTIME_IMAGE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]{1,254}$")
_EXPECTED_BLOCKERS = (
    "ARTIFACT_REVISION_UNPINNED",
    "ORG_OWNED_ARTIFACT_MIRROR_REQUIRED",
)
_EXPECTED_CANDIDATES: dict[
    str,
    tuple[GGUFQuantizationVariant, QuantizationRecipeName],
] = {
    "qwen38-27b-csight-q4-k-m-llama-cpp": (
        GGUFQuantizationVariant.MIXED_Q4_Q6,
        QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
    ),
    "qwen38-27b-csight-q5-k-s-llama-cpp": (
        GGUFQuantizationVariant.IMATRIX_Q5_K_S,
        QuantizationRecipeName.Q5_K_S_IMATRIX,
    ),
}
_MUTABLE_ARTIFACT_FIELDS = frozenset(
    {
        "artifact_content_digest",
        "weight_bytes",
        "quantization_recipe_digest",
        "importance_matrix_digest",
        "quantizer_binary_digest",
    }
)
_MUTABLE_SERVING_FIELDS = frozenset(
    {
        "runtime_image",
        "runtime_image_digest",
        "llama_cpp_revision",
        "runtime_binary_digest",
        "runtime_build_manifest_digest",
        "sbom_digest",
    }
)


class MatrixBindingError(RuntimeError):
    """The supplied evidence cannot be bound without weakening a release gate."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DockerLimits(_StrictModel):
    cpus: Literal["16"]
    memory: Literal["56g"]
    memory_swap: Literal["56g"]
    pids: Literal["1024"]
    network: Literal["NONE"]
    root_filesystem: Literal["READ_ONLY"]
    gpu_devices: Literal["NONE"]
    pull: Literal["NEVER"]
    uid: int = Field(ge=0)
    gid: int = Field(ge=0)


class PairCommandEvidence(_StrictModel):
    order: int = Field(ge=1, le=2)
    operation: Literal["QUANTIZE_FINAL_CANDIDATE_DIRECTLY_FROM_BF16"]
    recipe_name: QuantizationRecipeName
    recipe_digest: str = Field(pattern=_DIGEST_PATTERN)
    output_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{1,254}\.gguf$")
    output_digest: str = Field(pattern=_DIGEST_PATTERN)
    output_bytes: int = Field(gt=0)
    execution: Literal["EXECUTED", "REUSED_VERIFIED"]


class DevQualificationPairEvidence(_StrictModel):
    schema_version: Literal["llama_cpp_quantization_run_evidence/1.1.0"]
    status: Literal["PASS"]
    execution_mode: Literal["DOCKER_OFFLINE"]
    phase: Literal["FINAL_CANDIDATES"]
    plan_digest: str = Field(pattern=_DIGEST_PATTERN)
    llama_cpp_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    tool_image_id: str = Field(pattern=_DIGEST_PATTERN)
    quantize_binary_path: Literal["/app/llama-quantize"]
    quantize_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    docker_limits: DockerLimits
    commands: tuple[PairCommandEvidence, ...] = Field(min_length=2, max_length=2)
    all_host_inputs_reverified_after_execution: Literal[True]
    final_candidates_from_bf16: Literal[True]
    q8_helper_used_as_final_source: Literal[False]
    sealed_test_data_used: Literal[False]
    shell_interpolation_used: Literal[False]


class ImatrixGGUF(_StrictModel):
    valid: Literal[True]
    version: Literal[2, 3]
    tensor_count: int = Field(gt=0, le=1_000_000)
    metadata_count: int = Field(gt=0, le=1_000_000)


class CleanImatrixEvidence(_StrictModel):
    schema_version: Literal["qwen4090_imatrix_run_evidence/1.1.0"]
    status: Literal["PASS"]
    run_exit_code: Literal[0]
    vlm_restored: Literal[True]
    started_at: datetime
    finished_at: datetime
    q8_helper_digest: str = Field(pattern=_DIGEST_PATTERN)
    calibration_corpus_digest: str = Field(pattern=_DIGEST_PATTERN)
    llama_cpp_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    build_manifest_digest: str = Field(pattern=_DIGEST_PATTERN)
    tool_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    imatrix_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    imatrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    imatrix_bytes: int = Field(gt=0)
    imatrix_gguf: ImatrixGGUF
    log_digest: str = Field(pattern=_DIGEST_PATTERN)
    log_bytes: int = Field(gt=0)
    command_contract: dict[str, object]
    command_contract_digest: str = Field(pattern=_DIGEST_PATTERN)
    output_file_argument: Literal["/output/qwen38-27b-imatrix.gguf"]
    context_size: Literal[512]
    batch_size: Literal[512]
    ubatch_size: Literal[128]
    gpu_layers: Literal["auto"]
    threads: Literal[16]
    threads_batch: Literal[16]
    chunks: Literal[-1]
    output_frequency: Literal[1_000_000]
    save_frequency: Literal[0]
    process_output: Literal[True]
    no_ppl: Literal[True]
    flash_attention: Literal["on"]
    network_mode: Literal["NONE"]
    output_format: Literal["GGUF"]
    parse_special: Literal[True]
    perplexity_computed: Literal[False]
    test_data_used: Literal[False]

    @field_validator("started_at", "finished_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("imatrix timestamps must be timezone-aware")
        return value.astimezone(UTC)


def _read_regular(path: Path, *, maximum_bytes: int = MAX_JSON_BYTES) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise MatrixBindingError("required input must be a regular non-symlink file")
    before = path.stat()
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise MatrixBindingError("required input has an invalid size")
    content = path.read_bytes()
    after = path.stat()
    if (
        before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise MatrixBindingError("required input changed while it was read")
    return content


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _load_json_object(
    path: Path, *, maximum_bytes: int = MAX_JSON_BYTES
) -> tuple[bytes, dict[str, Any]]:
    content = _read_regular(path, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MatrixBindingError("evidence input is not valid JSON") from error
    if not isinstance(value, dict):
        raise MatrixBindingError("evidence JSON root must be an object")
    return content, value


def _canonical_utc(value: str) -> tuple[str, datetime]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MatrixBindingError("recorded_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MatrixBindingError("recorded_at must be timezone-aware")
    utc = parsed.astimezone(UTC)
    canonical = utc.isoformat().replace("+00:00", "Z")
    return canonical, utc


def _load_pair_evidence(path: Path) -> tuple[bytes, DevQualificationPairEvidence]:
    content = _read_regular(path)
    try:
        return content, DevQualificationPairEvidence.model_validate_json(content)
    except ValidationError as error:
        raise MatrixBindingError(
            "Dev qualification-pair evidence failed its strict schema"
        ) from error


def _load_imatrix_evidence(path: Path) -> tuple[bytes, CleanImatrixEvidence]:
    content = _read_regular(path)
    try:
        evidence = CleanImatrixEvidence.model_validate_json(content)
    except ValidationError as error:
        raise MatrixBindingError("clean imatrix evidence failed its strict schema") from error
    expected_contract = imatrix_command_contract()
    if evidence.command_contract != expected_contract or evidence.command_contract_digest != (
        canonical_command_contract_digest(expected_contract)
    ):
        raise MatrixBindingError("clean imatrix command contract drifted")
    if evidence.finished_at < evidence.started_at:
        raise MatrixBindingError("clean imatrix timestamps are out of order")
    return content, evidence


def _load_build_manifest(path: Path) -> tuple[bytes, LlamaCppBuildManifest]:
    content = _read_regular(path, maximum_bytes=1024 * 1024)
    try:
        manifest = LlamaCppBuildManifest.model_validate_json(content)
    except ValidationError as error:
        raise MatrixBindingError("llama.cpp build manifest failed its strict schema") from error
    if "89" not in manifest.cuda_architectures:
        raise MatrixBindingError("llama.cpp build does not target CUDA architecture 89")
    if manifest.cmake_options.get("GGML_CUDA") not in {True, "ON"}:
        raise MatrixBindingError("llama.cpp build did not enable GGML_CUDA")
    reference = manifest.runtime_image_reference
    if reference is not None and (
        _RUNTIME_IMAGE_REFERENCE.fullmatch(reference) is None or "@" in reference
    ):
        raise MatrixBindingError("build manifest contains an invalid runtime image tag")
    if "@sha256:" not in manifest.sbom_tool_image:
        raise MatrixBindingError("build manifest must pin the SBOM tool image by digest")
    return content, manifest


def _string_leaves(value: object) -> tuple[str, ...]:
    leaves: list[str] = []
    if isinstance(value, str):
        leaves.append(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            leaves.extend(_string_leaves(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            leaves.extend(_string_leaves(item))
    return tuple(leaves)


def _load_sbom(path: Path, *, runtime_image_digest: str) -> tuple[bytes, str]:
    content, document = _load_json_object(path)
    if not (
        document.get("bomFormat") == "CycloneDX" or isinstance(document.get("spdxVersion"), str)
    ):
        raise MatrixBindingError("SBOM is not CycloneDX or SPDX JSON")
    digest_forms = {runtime_image_digest, runtime_image_digest.removeprefix("sha256:")}
    if not any(
        leaf in digest_forms or any(leaf.endswith("@" + item) for item in digest_forms)
        for leaf in _string_leaves(document)
    ):
        raise MatrixBindingError("SBOM does not identify the exact runtime image digest")
    return content, _digest(content)


def _validate_plan_and_evidence(
    *,
    plan: LlamaCppQuantizationRunPlan,
    pair: DevQualificationPairEvidence,
    imatrix: CleanImatrixEvidence,
    build: LlamaCppBuildManifest,
    matrix: Qwen4090CandidateMatrixV2,
) -> dict[str, PairCommandEvidence]:
    if (
        plan.schema_version != "llama_cpp_quantization_run_plan/1.1.0"
        or plan.phase != "FINAL_CANDIDATES"
        or plan.final_candidate_set is not FinalCandidateSet.DEV_QUALIFICATION_PAIR
        or len(plan.commands) != 2
    ):
        raise MatrixBindingError("run plan is not the exact DEV_QUALIFICATION_PAIR contract")
    if pair.plan_digest != plan.plan_digest:
        raise MatrixBindingError("quantization evidence does not match the exact run plan")
    expected_build = (
        (plan.llama_cpp_revision, build.source_revision),
        (plan.quantize_binary_digest, build.quantizer_binary_digest),
        (plan.imatrix_binary_digest, build.imatrix_binary_digest),
        (pair.llama_cpp_revision, build.source_revision),
        (pair.tool_image_id, build.tool_image_digest),
        (pair.quantize_binary_digest, build.quantizer_binary_digest),
        (imatrix.llama_cpp_revision, build.source_revision),
        (imatrix.tool_image_digest, build.tool_image_digest),
        (imatrix.imatrix_binary_digest, build.imatrix_binary_digest),
    )
    if any(observed != expected for observed, expected in expected_build):
        raise MatrixBindingError("quantization or imatrix tool identity differs from the build")
    if (
        plan.imatrix_digest != imatrix.imatrix_digest
        or plan.calibration_text_digest != imatrix.calibration_corpus_digest
        or plan.calibration_helper_q8_digest != imatrix.q8_helper_digest
    ):
        raise MatrixBindingError("Dev pair plan does not consume the clean imatrix inputs")

    matrix_by_id = {candidate.candidate_id: candidate for candidate in matrix.candidates}
    if set(matrix_by_id) != set(_EXPECTED_CANDIDATES):
        raise MatrixBindingError("candidate matrix must contain exactly the audited Dev pair")
    if any(
        candidate.artifact.base_artifact_content_digest != plan.source_bf16_gguf_digest
        or candidate.artifact.calibration_dataset_digest != imatrix.calibration_corpus_digest
        for candidate in matrix.candidates
    ):
        raise MatrixBindingError("source BF16 or calibration corpus differs from the matrix")

    evidence_by_order = {command.order: command for command in pair.commands}
    if set(evidence_by_order) != {1, 2}:
        raise MatrixBindingError(
            "Dev pair evidence must contain command order 1 and 2 exactly once"
        )
    result: dict[str, PairCommandEvidence] = {}
    for planned in plan.commands:
        evidence = evidence_by_order.get(planned.order)
        if evidence is None or planned.recipe_name is None or planned.recipe_digest is None:
            raise MatrixBindingError("Dev pair command identity is incomplete")
        expected_candidate = next(
            (
                candidate
                for candidate in matrix.candidates
                if candidate.artifact.gguf_filename == evidence.output_name
            ),
            None,
        )
        if expected_candidate is None:
            raise MatrixBindingError("Dev pair output filename is not an audited candidate")
        expected_variant, expected_recipe = _EXPECTED_CANDIDATES[expected_candidate.candidate_id]
        if (
            expected_candidate.artifact.quantization_variant is not expected_variant
            or evidence.recipe_name is not expected_recipe
            or planned.recipe_name is not expected_recipe
            or planned.operation != evidence.operation
            or planned.recipe_digest != evidence.recipe_digest
            or Path(planned.output_path).name != evidence.output_name
            or (
                planned.expected_output_digest is not None
                and planned.expected_output_digest != evidence.output_digest
            )
        ):
            raise MatrixBindingError("Dev pair command, recipe, or output identity drifted")
        if expected_candidate.candidate_id in result:
            raise MatrixBindingError("Dev pair evidence identifies a candidate more than once")
        result[expected_candidate.candidate_id] = evidence
    if set(result) != set(_EXPECTED_CANDIDATES):
        raise MatrixBindingError("Dev pair evidence does not contain both audited candidates")
    return result


def _changed_paths(
    before: object, after: object, prefix: tuple[object, ...] = ()
) -> set[tuple[object, ...]]:
    if type(before) is not type(after):
        return {prefix}
    if isinstance(before, dict):
        paths: set[tuple[object, ...]] = set()
        keys = set(before) | set(after)
        for key in keys:
            if key not in before or key not in after:
                paths.add((*prefix, key))
            else:
                paths.update(_changed_paths(before[key], after[key], (*prefix, key)))
        return paths
    if isinstance(before, list):
        paths = set()
        if len(before) != len(after):
            paths.add(prefix)
        for index, (left, right) in enumerate(zip(before, after, strict=False)):
            paths.update(_changed_paths(left, right, (*prefix, index)))
        return paths
    return set() if before == after else {prefix}


def _permitted_paths(matrix: Qwen4090CandidateMatrixV2) -> set[tuple[object, ...]]:
    permitted: set[tuple[object, ...]] = {("recorded_at",)}
    for index, _ in enumerate(matrix.candidates):
        permitted.update(
            ("candidates", index, "artifact", field) for field in _MUTABLE_ARTIFACT_FIELDS
        )
        permitted.update(
            ("candidates", index, "serving", field) for field in _MUTABLE_SERVING_FIELDS
        )
    return permitted


def build_bound_matrix(
    *,
    matrix_document: dict[str, Any],
    matrix: Qwen4090CandidateMatrixV2,
    pair_commands: Mapping[str, PairCommandEvidence],
    imatrix: CleanImatrixEvidence,
    build_manifest_content: bytes,
    build: LlamaCppBuildManifest,
    runtime_image_reference: str,
    sbom_digest: str,
    recorded_at: str,
) -> tuple[bytes, Qwen4090CandidateMatrixV2, tuple[str, ...]]:
    canonical_time, recorded_time = _canonical_utc(recorded_at)
    if recorded_time < imatrix.finished_at:
        raise MatrixBindingError("recorded_at cannot precede the clean imatrix completion")
    if recorded_time < matrix.recorded_at:
        raise MatrixBindingError("recorded_at cannot move the candidate matrix backwards")

    proposed = copy.deepcopy(matrix_document)
    proposed["recorded_at"] = canonical_time
    raw_candidates = proposed.get("candidates")
    if not isinstance(raw_candidates, list):
        raise MatrixBindingError("candidate matrix candidates are malformed")
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            raise MatrixBindingError("candidate matrix candidate is malformed")
        candidate_id = raw_candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id not in pair_commands:
            raise MatrixBindingError("candidate matrix contains an unexpected candidate")
        artifact = raw_candidate.get("artifact")
        serving = raw_candidate.get("serving")
        if not isinstance(artifact, dict) or not isinstance(serving, dict):
            raise MatrixBindingError("candidate matrix identity is malformed")
        if (
            artifact.get("artifact_revision") is not None
            or raw_candidate.get("qualification") is not None
        ):
            raise MatrixBindingError("binder accepts only unpublished, unqualified candidates")
        command = pair_commands[candidate_id]
        artifact.update(
            {
                "artifact_content_digest": command.output_digest,
                "weight_bytes": command.output_bytes,
                "quantization_recipe_digest": command.recipe_digest,
                "importance_matrix_digest": imatrix.imatrix_digest,
                "quantizer_binary_digest": build.quantizer_binary_digest,
            }
        )
        serving.update(
            {
                "runtime_image": runtime_image_reference,
                "runtime_image_digest": build.runtime_image_digest,
                "llama_cpp_revision": build.source_revision,
                "runtime_binary_digest": build.runtime_binary_digest,
                "runtime_build_manifest_digest": _digest(build_manifest_content),
                "sbom_digest": sbom_digest,
            }
        )

    changes = _changed_paths(matrix_document, proposed)
    unexpected = changes - _permitted_paths(matrix)
    if unexpected:
        rendered = ", ".join("/".join(map(str, path)) for path in sorted(unexpected, key=str))
        raise MatrixBindingError("binder attempted a forbidden matrix change: " + rendered)
    encoded = (json.dumps(proposed, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        validated = Qwen4090CandidateMatrixV2.model_validate_json(encoded)
    except ValidationError as error:
        raise MatrixBindingError("bound candidate matrix failed its strict schema") from error
    assessments = assess_gguf_matrix(validated)
    if any(
        assessment.status is not CandidateReleaseStatusV2.PENDING_QUALIFICATION
        or assessment.reason_codes != _EXPECTED_BLOCKERS
        for assessment in assessments
    ):
        raise MatrixBindingError("bound matrix no longer has the exact unpublished Dev blockers")
    if any(
        candidate.artifact.artifact_revision is not None or candidate.qualification is not None
        for candidate in validated.candidates
    ):
        raise MatrixBindingError("binder must not publish or qualify a candidate")
    changed = tuple(sorted("/".join(map(str, path)) for path in changes))
    return encoded, validated, changed


def bind_evidence(
    *,
    matrix_path: Path,
    run_plan_path: Path,
    pair_evidence_path: Path,
    imatrix_evidence_path: Path,
    build_manifest_path: Path,
    sbom_path: Path,
    runtime_image_reference: str,
    recorded_at: str,
) -> tuple[bytes, dict[str, object]]:
    matrix_content, matrix_document = _load_json_object(matrix_path, maximum_bytes=1024 * 1024)
    try:
        matrix = Qwen4090CandidateMatrixV2.model_validate_json(matrix_content)
        plan = load_run_plan(run_plan_path)
    except (OSError, ValueError, ValidationError) as error:
        raise MatrixBindingError("matrix or Dev pair run plan failed strict validation") from error
    pair_content, pair = _load_pair_evidence(pair_evidence_path)
    imatrix_content, imatrix = _load_imatrix_evidence(imatrix_evidence_path)
    build_content, build = _load_build_manifest(build_manifest_path)
    if (
        _RUNTIME_IMAGE_REFERENCE.fullmatch(runtime_image_reference) is None
        or "@" in runtime_image_reference
    ):
        raise MatrixBindingError("runtime image reference must be one unambiguous tag")
    if (
        build.runtime_image_reference is not None
        and build.runtime_image_reference != runtime_image_reference
    ):
        raise MatrixBindingError(
            "runtime image reference differs from the optional build-manifest value"
        )
    if imatrix.build_manifest_digest != _digest(build_content):
        raise MatrixBindingError("clean imatrix evidence does not match the build manifest")
    sbom_content, sbom_digest = _load_sbom(
        sbom_path,
        runtime_image_digest=build.runtime_image_digest,
    )
    pair_commands = _validate_plan_and_evidence(
        plan=plan,
        pair=pair,
        imatrix=imatrix,
        build=build,
        matrix=matrix,
    )
    proposed_content, proposed, changed_fields = build_bound_matrix(
        matrix_document=matrix_document,
        matrix=matrix,
        pair_commands=pair_commands,
        imatrix=imatrix,
        build_manifest_content=build_content,
        build=build,
        runtime_image_reference=runtime_image_reference,
        sbom_digest=sbom_digest,
        recorded_at=recorded_at,
    )
    report: dict[str, object] = {
        "schema_version": "qwen4090_dev_pair_matrix_binding/1.0.0",
        "status": "PASS",
        "release_status": "NO_RELEASE_ELIGIBLE",
        "input_matrix_file_digest": _digest(matrix_content),
        "input_matrix_semantic_digest": matrix.matrix_digest,
        "proposed_matrix_file_digest": _digest(proposed_content),
        "proposed_matrix_semantic_digest": proposed.matrix_digest,
        "run_plan_digest": plan.plan_digest,
        "quantization_evidence_digest": _digest(pair_content),
        "imatrix_evidence_digest": _digest(imatrix_content),
        "importance_matrix_digest": imatrix.imatrix_digest,
        "build_manifest_digest": _digest(build_content),
        "runtime_image_digest": build.runtime_image_digest,
        "runtime_image_reference": runtime_image_reference,
        "sbom_digest": _digest(sbom_content),
        "candidate_outputs": {
            candidate_id: {
                "filename": command.output_name,
                "digest": command.output_digest,
                "bytes": command.output_bytes,
                "recipe_name": command.recipe_name,
                "recipe_digest": command.recipe_digest,
            }
            for candidate_id, command in sorted(pair_commands.items())
        },
        "changed_fields": changed_fields,
        "artifact_revision": None,
        "qualification": None,
    }
    return proposed_content, report


def atomic_compare_and_replace(
    path: Path,
    *,
    expected_file_digest: str,
    content: bytes,
) -> Literal["WRITTEN", "ALREADY_BOUND"]:
    if _DIGEST.fullmatch(expected_file_digest) is None:
        raise MatrixBindingError("write requires an exact expected matrix file digest")
    current = _read_regular(path, maximum_bytes=1024 * 1024)
    if _digest(current) != expected_file_digest:
        raise MatrixBindingError(
            "candidate matrix changed after check; refusing ambiguous overwrite"
        )
    if current == content:
        return "ALREADY_BOUND"
    metadata = path.stat()
    temporary = path.with_name(f".{path.name}.{os.getpid()}.binding.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise MatrixBindingError("atomic matrix temporary path already exists")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fchmod(descriptor, stat.S_IMODE(metadata.st_mode))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        latest = _read_regular(path, maximum_bytes=1024 * 1024)
        if _digest(latest) != expected_file_digest:
            raise MatrixBindingError(
                "candidate matrix changed during write; refusing ambiguous overwrite"
            )
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()
    return "WRITTEN"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--run-plan", type=Path, required=True)
    parser.add_argument("--pair-evidence", type=Path, required=True)
    parser.add_argument("--imatrix-evidence", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--runtime-image-reference", required=True)
    parser.add_argument("--recorded-at", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--expected-matrix-file-digest")
    parser.add_argument("--confirm-write")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        proposed, report = bind_evidence(
            matrix_path=arguments.matrix,
            run_plan_path=arguments.run_plan,
            pair_evidence_path=arguments.pair_evidence,
            imatrix_evidence_path=arguments.imatrix_evidence,
            build_manifest_path=arguments.build_manifest,
            sbom_path=arguments.sbom,
            runtime_image_reference=arguments.runtime_image_reference,
            recorded_at=arguments.recorded_at,
        )
        if arguments.write:
            if arguments.confirm_write != WRITE_CONFIRMATION:
                raise MatrixBindingError(f"write requires --confirm-write {WRITE_CONFIRMATION}")
            if arguments.expected_matrix_file_digest is None:
                raise MatrixBindingError("write requires --expected-matrix-file-digest")
            report["status"] = atomic_compare_and_replace(
                arguments.matrix,
                expected_file_digest=arguments.expected_matrix_file_digest,
                content=proposed,
            )
        else:
            report["status"] = "CHECKED"
    except (MatrixBindingError, OSError, ValueError) as error:
        print(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
