"""Validate offline llama-imatrix inputs and write privacy-safe run evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import struct
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PINNED_IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:([0-9a-f]{64})$")
LLAMA_CPP_B10419_REVISION = "aee56b3abfeb134218fe5c496c329a1faac1ef28"
MAX_Q8_BYTES = 40 * 1024 * 1024 * 1024
MAX_CORPUS_BYTES = 1024 * 1024 * 1024
MAX_BUILD_MANIFEST_BYTES = 1024 * 1024
MAX_LOG_BYTES = 256 * 1024 * 1024
MAX_IMATRIX_BYTES = 8 * 1024 * 1024 * 1024
GGUF_HEADER_BYTES = 24
SUPPORTED_GGUF_VERSIONS = frozenset({2, 3})
IMATRIX_COMMAND_SCHEMA_VERSION = "qwen4090_imatrix_command_contract/1.0.0"
IMATRIX_OUTPUT_FILE_ARGUMENT = "/output/qwen38-27b-imatrix.gguf"
IMATRIX_CONTEXT_SIZE = 512
IMATRIX_BATCH_SIZE = 512
IMATRIX_UBATCH_SIZE = 128
IMATRIX_CHUNKS = -1
IMATRIX_THREADS = 16
IMATRIX_THREADS_BATCH = 16
IMATRIX_OUTPUT_FREQUENCY = 1_000_000
IMATRIX_SAVE_FREQUENCY = 0


class ImatrixMaintenanceError(RuntimeError):
    """Maintenance inputs or evidence violate the protected offline contract."""


class LlamaCppBuildManifest(BaseModel):
    """Standalone subset of the exact llama.cpp build-manifest v1 contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal["csight_llama_cpp_build/1.0.0"]
    source_repository: Literal["ggml-org/llama.cpp"]
    source_revision: Literal["aee56b3abfeb134218fe5c496c329a1faac1ef28"]
    dockerfile_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    tool_image_reference: str | None = None
    tool_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    runtime_image_reference: str | None = None
    runtime_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    runtime_binary_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    quantizer_binary_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    imatrix_binary_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    tokenizer_binary_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    cuda_architectures: tuple[str, ...] = Field(min_length=1)
    cmake_options: dict[str, str | bool] = Field(min_length=1)
    base_image_digests: dict[str, str] = Field(min_length=2)
    sbom_tool_image: str = Field(min_length=3, max_length=512)

    @field_validator("base_image_digests")
    @classmethod
    def require_pinned_base_images(cls, value: dict[str, str]) -> dict[str, str]:
        if any(_DIGEST.fullmatch(item) is None for item in value.values()):
            raise ValueError("base images must use exact SHA-256 digests")
        return value


def _owned_mode(path: Path, *, directory: bool) -> os.stat_result:
    if path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise ImatrixMaintenanceError("required owner-only path is missing or unsafe")
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ImatrixMaintenanceError(
            "required path must be owned by this user with no shared mode"
        )
    return metadata


def _stream_digest(path: Path, *, maximum_bytes: int) -> tuple[str, int]:
    before = _owned_mode(path, directory=False)
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise ImatrixMaintenanceError("required input has an invalid size")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ImatrixMaintenanceError("input changed while it was being hashed")
    return "sha256:" + digest.hexdigest(), before.st_size


def validate_imatrix_gguf_header(path: Path) -> dict[str, int | bool]:
    """Reject non-GGUF or structurally empty output before granting PASS evidence."""

    metadata = _owned_mode(path, directory=False)
    if metadata.st_size < GGUF_HEADER_BYTES:
        return {"valid": False, "version": 0, "tensor_count": 0, "metadata_count": 0}
    with path.open("rb") as stream:
        header = stream.read(GGUF_HEADER_BYTES)
    magic, version, tensor_count, metadata_count = struct.unpack("<4sIQQ", header)
    valid = (
        magic == b"GGUF"
        and version in SUPPORTED_GGUF_VERSIONS
        and 0 < tensor_count <= 1_000_000
        and 0 < metadata_count <= 1_000_000
    )
    return {
        "valid": valid,
        "version": version,
        "tensor_count": tensor_count,
        "metadata_count": metadata_count,
    }


def _expected_digest(value: str, *, label: str) -> str:
    if _DIGEST.fullmatch(value) is None:
        raise ImatrixMaintenanceError(f"{label} must be an exact SHA-256 digest")
    return value


def pinned_image_digest(value: str) -> str:
    if _DIGEST.fullmatch(value) is not None:
        return value
    match = _PINNED_IMAGE.fullmatch(value)
    if match is not None:
        return "sha256:" + match.group(1)
    raise ImatrixMaintenanceError(
        "llama.cpp tool image must be an exact local image ID or repository digest"
    )


def imatrix_command_contract(
    *,
    context_size: int = IMATRIX_CONTEXT_SIZE,
    batch_size: int = IMATRIX_BATCH_SIZE,
    ubatch_size: int = IMATRIX_UBATCH_SIZE,
    chunks: int = IMATRIX_CHUNKS,
) -> dict[str, object]:
    """Return the one approved b10419 calibration command contract."""
    observed_profile = (context_size, batch_size, ubatch_size, chunks)
    approved_profile = (
        IMATRIX_CONTEXT_SIZE,
        IMATRIX_BATCH_SIZE,
        IMATRIX_UBATCH_SIZE,
        IMATRIX_CHUNKS,
    )
    if observed_profile != approved_profile:
        raise ImatrixMaintenanceError(
            "imatrix command settings do not match the approved b10419 profile"
        )
    return {
        "schema_version": IMATRIX_COMMAND_SCHEMA_VERSION,
        "llama_cpp_revision": LLAMA_CPP_B10419_REVISION,
        "executable": "/app/llama-imatrix",
        "model_file_argument": "/inputs/helper-q8.gguf",
        "input_file_argument": "/inputs/calibration.txt",
        "output_file_argument": IMATRIX_OUTPUT_FILE_ARGUMENT,
        "output_format": "gguf",
        "context_size": context_size,
        "batch_size": batch_size,
        "ubatch_size": ubatch_size,
        "gpu_layers": "auto",
        "threads": IMATRIX_THREADS,
        "threads_batch": IMATRIX_THREADS_BATCH,
        "chunks": chunks,
        "output_frequency": IMATRIX_OUTPUT_FREQUENCY,
        "save_frequency": IMATRIX_SAVE_FREQUENCY,
        "process_output": True,
        "no_ppl": True,
        "parse_special": True,
        "flash_attention": "on",
    }


def canonical_command_contract_digest(contract: dict[str, object]) -> str:
    """Hash the canonical JSON representation of a command contract."""
    encoded = json.dumps(
        contract,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_inputs(
    *,
    q8_helper: Path,
    expected_q8_digest: str,
    calibration_corpus: Path,
    expected_corpus_digest: str,
    build_manifest_path: Path,
    expected_build_manifest_digest: str,
    tool_image: str,
    output_root: Path,
    evidence_root: Path,
    context_size: int = IMATRIX_CONTEXT_SIZE,
    batch_size: int = IMATRIX_BATCH_SIZE,
    ubatch_size: int = IMATRIX_UBATCH_SIZE,
    chunks: int = IMATRIX_CHUNKS,
) -> dict[str, object]:
    command_contract = imatrix_command_contract(
        context_size=context_size,
        batch_size=batch_size,
        ubatch_size=ubatch_size,
        chunks=chunks,
    )
    if q8_helper.suffix.casefold() != ".gguf":
        raise ImatrixMaintenanceError("Q8 calibration helper must be a GGUF file")
    if calibration_corpus.suffix.casefold() != ".txt":
        raise ImatrixMaintenanceError("calibration corpus must be the frozen text artifact")
    q8_digest, q8_bytes = _stream_digest(q8_helper, maximum_bytes=MAX_Q8_BYTES)
    corpus_digest, corpus_bytes = _stream_digest(
        calibration_corpus,
        maximum_bytes=MAX_CORPUS_BYTES,
    )
    if q8_digest != _expected_digest(expected_q8_digest, label="Q8 helper digest"):
        raise ImatrixMaintenanceError("Q8 helper digest does not match the approved input")
    if corpus_digest != _expected_digest(expected_corpus_digest, label="corpus digest"):
        raise ImatrixMaintenanceError("calibration corpus digest does not match the manifest")
    build_digest, _ = _stream_digest(
        build_manifest_path,
        maximum_bytes=MAX_BUILD_MANIFEST_BYTES,
    )
    if build_digest != _expected_digest(
        expected_build_manifest_digest,
        label="build manifest digest",
    ):
        raise ImatrixMaintenanceError(
            "llama.cpp build manifest digest does not match the approved input"
        )
    try:
        build_manifest = LlamaCppBuildManifest.model_validate_json(build_manifest_path.read_bytes())
    except ValueError as error:
        raise ImatrixMaintenanceError("llama.cpp build manifest is invalid") from error
    image_digest = pinned_image_digest(tool_image)
    if build_manifest.tool_image_digest != image_digest:
        raise ImatrixMaintenanceError("tool image does not match the signed build manifest")
    _owned_mode(output_root, directory=True)
    _owned_mode(evidence_root, directory=True)
    return {
        "schema_version": "qwen4090_imatrix_preflight/1.1.0",
        "q8_helper_digest": q8_digest,
        "q8_helper_bytes": q8_bytes,
        "calibration_corpus_digest": corpus_digest,
        "calibration_corpus_bytes": corpus_bytes,
        "llama_cpp_revision": build_manifest.source_revision,
        "build_manifest_digest": build_digest,
        "tool_image_digest": build_manifest.tool_image_digest,
        "imatrix_binary_digest": build_manifest.imatrix_binary_digest,
        "command_contract": command_contract,
        "command_contract_digest": canonical_command_contract_digest(command_contract),
        "network_mode": "NONE",
        "test_data_used": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    _owned_mode(path, directory=False)
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ImatrixMaintenanceError("preflight report is invalid JSON") from error
    supported_schemas = {
        "qwen4090_imatrix_preflight/1.0.0",
        "qwen4090_imatrix_preflight/1.1.0",
    }
    if not isinstance(value, dict) or value.get("schema_version") not in supported_schemas:
        raise ImatrixMaintenanceError("preflight report has the wrong schema")
    return value


def write_json_once(path: Path, value: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ImatrixMaintenanceError("refusing to overwrite maintenance evidence")
    parent = path.parent
    _owned_mode(parent, directory=True)
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def finalize_evidence(
    *,
    preflight_report: Path,
    output_file: Path,
    log_file: Path,
    evidence_file: Path,
    run_exit_code: int,
    vlm_restored: bool,
    started_at: str,
    finished_at: str,
    context_size: int,
    batch_size: int,
    ubatch_size: int,
    chunks: int,
) -> dict[str, object]:
    preflight = _read_json(preflight_report)
    expected_contract = imatrix_command_contract(
        context_size=context_size,
        batch_size=batch_size,
        ubatch_size=ubatch_size,
        chunks=chunks,
    )
    expected_contract_digest = canonical_command_contract_digest(expected_contract)
    preflight_contract = preflight.get("command_contract")
    preflight_contract_digest = preflight.get("command_contract_digest")
    if (preflight_contract is not None or preflight_contract_digest is not None) and (
        preflight_contract != expected_contract
        or preflight_contract_digest != expected_contract_digest
    ):
        raise ImatrixMaintenanceError(
            "final command settings do not match the preflight command contract"
        )
    log_digest, log_bytes = _stream_digest(log_file, maximum_bytes=MAX_LOG_BYTES)
    output_digest: str | None = None
    output_bytes = 0
    output_structure: dict[str, int | bool] = {
        "valid": False,
        "version": 0,
        "tensor_count": 0,
        "metadata_count": 0,
    }
    if output_file.exists() and not output_file.is_symlink():
        output_digest, output_bytes = _stream_digest(
            output_file,
            maximum_bytes=MAX_IMATRIX_BYTES,
        )
        output_structure = validate_imatrix_gguf_header(output_file)
    succeeded = (
        run_exit_code == 0
        and output_digest is not None
        and output_structure["valid"] is True
        and vlm_restored
    )
    evidence: dict[str, object] = {
        "schema_version": "qwen4090_imatrix_run_evidence/1.1.0",
        "status": "PASS" if succeeded else "FAIL",
        "run_exit_code": run_exit_code,
        "vlm_restored": vlm_restored,
        "started_at": started_at,
        "finished_at": finished_at,
        "q8_helper_digest": preflight["q8_helper_digest"],
        "calibration_corpus_digest": preflight["calibration_corpus_digest"],
        "llama_cpp_revision": preflight["llama_cpp_revision"],
        "build_manifest_digest": preflight["build_manifest_digest"],
        "tool_image_digest": preflight["tool_image_digest"],
        "imatrix_binary_digest": preflight["imatrix_binary_digest"],
        "imatrix_digest": output_digest,
        "imatrix_bytes": output_bytes,
        "imatrix_gguf": output_structure,
        "log_digest": log_digest,
        "log_bytes": log_bytes,
        "command_contract": expected_contract,
        "command_contract_digest": expected_contract_digest,
        "output_file_argument": expected_contract["output_file_argument"],
        "context_size": expected_contract["context_size"],
        "batch_size": expected_contract["batch_size"],
        "ubatch_size": expected_contract["ubatch_size"],
        "gpu_layers": expected_contract["gpu_layers"],
        "threads": expected_contract["threads"],
        "threads_batch": expected_contract["threads_batch"],
        "chunks": expected_contract["chunks"],
        "output_frequency": expected_contract["output_frequency"],
        "save_frequency": expected_contract["save_frequency"],
        "process_output": expected_contract["process_output"],
        "no_ppl": expected_contract["no_ppl"],
        "flash_attention": expected_contract["flash_attention"],
        "network_mode": "NONE",
        "output_format": "GGUF",
        "parse_special": True,
        "perplexity_computed": False,
        "test_data_used": False,
    }
    write_json_once(evidence_file, evidence)
    return evidence


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return parsed


def _chunks_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected -1 or a positive integer") from error
    if parsed != -1 and parsed <= 0:
        raise argparse.ArgumentTypeError("expected -1 or a positive integer")
    return parsed


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--q8-helper", type=Path, required=True)
    preflight.add_argument("--q8-digest", required=True)
    preflight.add_argument("--calibration-corpus", type=Path, required=True)
    preflight.add_argument("--calibration-digest", required=True)
    preflight.add_argument("--build-manifest", type=Path, required=True)
    preflight.add_argument("--build-manifest-digest", required=True)
    preflight.add_argument("--tool-image", required=True)
    preflight.add_argument("--output-root", type=Path, required=True)
    preflight.add_argument("--evidence-root", type=Path, required=True)
    preflight.add_argument("--context-size", type=_positive_int, default=IMATRIX_CONTEXT_SIZE)
    preflight.add_argument("--batch-size", type=_positive_int, default=IMATRIX_BATCH_SIZE)
    preflight.add_argument("--ubatch-size", type=_positive_int, default=IMATRIX_UBATCH_SIZE)
    preflight.add_argument("--chunks", type=_chunks_int, default=IMATRIX_CHUNKS)
    preflight.add_argument("--report", type=Path, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--preflight-report", type=Path, required=True)
    finalize.add_argument("--output-file", type=Path, required=True)
    finalize.add_argument("--log-file", type=Path, required=True)
    finalize.add_argument("--evidence-file", type=Path, required=True)
    finalize.add_argument("--run-exit-code", type=_positive_int, required=True)
    finalize.add_argument("--vlm-restored", choices=("true", "false"), required=True)
    finalize.add_argument("--started-at", required=True)
    finalize.add_argument("--finished-at", required=True)
    finalize.add_argument("--context-size", type=_positive_int, required=True)
    finalize.add_argument("--batch-size", type=_positive_int, required=True)
    finalize.add_argument("--ubatch-size", type=_positive_int, required=True)
    finalize.add_argument("--chunks", type=_chunks_int, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        if arguments.command == "preflight":
            report = validate_inputs(
                q8_helper=arguments.q8_helper,
                expected_q8_digest=arguments.q8_digest,
                calibration_corpus=arguments.calibration_corpus,
                expected_corpus_digest=arguments.calibration_digest,
                build_manifest_path=arguments.build_manifest,
                expected_build_manifest_digest=arguments.build_manifest_digest,
                tool_image=arguments.tool_image,
                output_root=arguments.output_root,
                evidence_root=arguments.evidence_root,
                context_size=arguments.context_size,
                batch_size=arguments.batch_size,
                ubatch_size=arguments.ubatch_size,
                chunks=arguments.chunks,
            )
            write_json_once(arguments.report, report)
        else:
            report = finalize_evidence(
                preflight_report=arguments.preflight_report,
                output_file=arguments.output_file,
                log_file=arguments.log_file,
                evidence_file=arguments.evidence_file,
                run_exit_code=arguments.run_exit_code,
                vlm_restored=arguments.vlm_restored == "true",
                started_at=arguments.started_at,
                finished_at=arguments.finished_at,
                context_size=arguments.context_size,
                batch_size=arguments.batch_size,
                ubatch_size=arguments.ubatch_size,
                chunks=arguments.chunks,
            )
    except (ImatrixMaintenanceError, OSError, ValueError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("status", "PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
