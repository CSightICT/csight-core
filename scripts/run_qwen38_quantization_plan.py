"""Validate or explicitly execute one pinned Qwen3.8 llama.cpp quantization plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.platform.quantization_assets import (
    LlamaCppQuantizationRunPlan,
    QuantizationAssetError,
)

MAX_PLAN_BYTES = 4 * 1024 * 1024
EXECUTION_CONFIRMATION = "YES"
DOCKER_IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
DOCKER_QUANTIZE_BINARY = "/app/llama-quantize"
DOCKER_CPU_LIMIT = "16"
DOCKER_MEMORY_LIMIT = "56g"
DOCKER_PIDS_LIMIT = "1024"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--evidence-output", type=Path)
    parser.add_argument(
        "--docker-image-id",
        help="exact local sha256 image ID; required for execution",
    )
    return parser.parse_args()


def load_run_plan(path: Path) -> LlamaCppQuantizationRunPlan:
    if path.is_symlink() or not path.is_file():
        raise QuantizationAssetError("run plan must be a regular non-symlink file")
    content = path.read_bytes()
    if not content or len(content) > MAX_PLAN_BYTES:
        raise QuantizationAssetError("run plan is empty or exceeds its size limit")
    try:
        return LlamaCppQuantizationRunPlan.model_validate_json(content)
    except ValidationError as error:
        raise QuantizationAssetError("run plan failed its strict schema or digest") from error


def digest_regular_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise QuantizationAssetError(f"required input is not a regular file: {path}")
    before = path.stat()
    if before.st_size <= 0:
        raise QuantizationAssetError(f"required input is empty: {path}")
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
        raise QuantizationAssetError(f"input changed while it was hashed: {path}")
    return "sha256:" + digest.hexdigest()


def validate_command_inputs(
    *,
    expected: dict[str, str],
    generated: tuple[str, ...],
    observed_outputs: dict[str, str],
) -> None:
    for raw_path, expected_digest in expected.items():
        observed = digest_regular_file(Path(raw_path))
        if observed != expected_digest:
            raise QuantizationAssetError(f"input digest mismatch: {raw_path}")
    for raw_path in generated:
        if raw_path not in observed_outputs:
            raise QuantizationAssetError(f"generated input is not from this run: {raw_path}")
        if digest_regular_file(Path(raw_path)) != observed_outputs[raw_path]:
            raise QuantizationAssetError(f"generated input changed after creation: {raw_path}")


def _strictly_revalidate_final_plan(
    plan: LlamaCppQuantizationRunPlan,
) -> LlamaCppQuantizationRunPlan:
    """Re-run every schema and canonical digest guard before Docker is touched."""

    try:
        validated = LlamaCppQuantizationRunPlan.model_validate(plan.model_dump(mode="json"))
    except ValidationError as error:
        raise QuantizationAssetError("final run plan failed strict revalidation") from error
    if validated.phase != "FINAL_CANDIDATES":
        raise QuantizationAssetError("Docker execution accepts final-candidate plans only")
    if not validated.final_candidates_from_bf16:
        raise QuantizationAssetError("every Docker candidate must be sourced directly from BF16")
    if validated.paths.quantize_binary != DOCKER_QUANTIZE_BINARY:
        raise QuantizationAssetError(
            f"Docker plan must use the image binary at {DOCKER_QUANTIZE_BINARY}"
        )
    if any(
        command.final_quantization_source != "BF16_GGUF"
        or validated.paths.source_bf16_gguf not in command.argv
        or validated.paths.q8_helper_gguf in command.argv
        or command.argv[0] != DOCKER_QUANTIZE_BINARY
        for command in validated.commands
    ):
        raise QuantizationAssetError("Docker plan contains a non-BF16 final candidate")
    return validated


def _require_canonical_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
        raise QuantizationAssetError(f"Docker input must be a canonical regular file: {path}")
    if "," in str(path) or ":" in str(path):
        raise QuantizationAssetError(f"Docker input path contains an unsafe bind character: {path}")


def _require_output_parent(path: Path, *, owner_uid: int) -> None:
    parent = path.parent
    if (
        parent == Path("/")
        or parent.is_symlink()
        or not parent.is_dir()
        or parent.resolve(strict=True) != parent
    ):
        raise QuantizationAssetError(f"Docker output parent is unsafe: {parent}")
    metadata = parent.stat()
    if metadata.st_uid != owner_uid:
        raise QuantizationAssetError("Docker output parent must be owned by the executing user")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise QuantizationAssetError("Docker output parent must be owner-only mode 700")
    if "," in str(parent) or ":" in str(parent):
        raise QuantizationAssetError("Docker output parent contains an unsafe bind character")


def _require_owner_only_evidence_target(path: Path, *, owner_uid: int) -> None:
    if path.exists() or path.is_symlink():
        raise QuantizationAssetError("refusing to overwrite run evidence")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir() or parent.resolve(strict=True) != parent:
        raise QuantizationAssetError("run evidence parent must be an existing canonical directory")
    metadata = parent.stat()
    if metadata.st_uid != owner_uid or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise QuantizationAssetError("run evidence parent must be owner-only")


def _write_owner_only_json_once(path: Path, value: dict[str, object]) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise QuantizationAssetError("refusing to overwrite run evidence") from error
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _partial_output_evidence(
    plan: LlamaCppQuantizationRunPlan,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for command in plan.commands:
        output = Path(command.output_path)
        record: dict[str, object] = {
            "order": command.order,
            "output_name": output.name,
            "state": "ABSENT",
        }
        if output.is_symlink():
            record["state"] = "UNSAFE_SYMLINK"
        elif output.is_file():
            try:
                record.update(
                    {
                        "state": "PRESENT_UNQUALIFIED",
                        "output_bytes": output.stat().st_size,
                        "output_digest": digest_regular_file(output),
                    }
                )
            except (OSError, QuantizationAssetError):
                record["state"] = "UNREADABLE_OR_CHANGED"
        elif output.exists():
            record["state"] = "UNSAFE_NON_FILE"
        records.append(record)
    return records


def _run_docker_checked(
    arguments: list[str], *, capture_output: bool = True
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            arguments,
            check=True,
            capture_output=capture_output,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise QuantizationAssetError("offline Docker quantization command failed") from error


def _verify_local_tool_image(
    *,
    image_id: str,
    expected_binary_digest: str,
    owner_uid: int,
    owner_gid: int,
) -> None:
    if DOCKER_IMAGE_ID_PATTERN.fullmatch(image_id) is None:
        raise QuantizationAssetError("Docker tool image must be an exact local sha256 image ID")
    inspect = _run_docker_checked(["docker", "image", "inspect", "--format", "{{.Id}}", image_id])
    if inspect.stdout.strip() != image_id:
        raise QuantizationAssetError("local Docker image ID does not match the requested image")
    binary_check = _run_docker_checked(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cpus=1",
            "--memory=256m",
            "--memory-swap=256m",
            "--pids-limit=64",
            f"--user={owner_uid}:{owner_gid}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--entrypoint=/usr/bin/sha256sum",
            image_id,
            DOCKER_QUANTIZE_BINARY,
        ]
    )
    match = re.fullmatch(
        rf"([0-9a-f]{{64}})\s+{re.escape(DOCKER_QUANTIZE_BINARY)}\s*",
        binary_check.stdout,
    )
    observed = "sha256:" + match.group(1) if match is not None else None
    if observed != expected_binary_digest:
        raise QuantizationAssetError("image llama-quantize digest does not match the plan")


def _docker_quantize_argv(
    *,
    command_argv: tuple[str, ...],
    input_paths: tuple[Path, ...],
    output_parent: Path,
    image_id: str,
    owner_uid: int,
    owner_gid: int,
) -> list[str]:
    arguments = [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        f"--cpus={DOCKER_CPU_LIMIT}",
        f"--memory={DOCKER_MEMORY_LIMIT}",
        f"--memory-swap={DOCKER_MEMORY_LIMIT}",
        f"--pids-limit={DOCKER_PIDS_LIMIT}",
        f"--user={owner_uid}:{owner_gid}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--env=HF_HUB_OFFLINE=1",
        "--env=TRANSFORMERS_OFFLINE=1",
        "--env=NO_PROXY=*",
    ]
    for path in input_paths:
        arguments.extend(("--mount", f"type=bind,source={path},target={path},readonly"))
    arguments.extend(
        (
            "--mount",
            f"type=bind,source={output_parent},target={output_parent}",
            f"--entrypoint={DOCKER_QUANTIZE_BINARY}",
            image_id,
            *command_argv[1:],
        )
    )
    return arguments


def execute_final_run_plan_in_docker(
    plan: LlamaCppQuantizationRunPlan,
    *,
    image_id: str,
    evidence_output: Path,
) -> dict[str, object]:
    """Execute the exact admitted BF16 candidate set in a bounded offline container."""

    if os.environ.get("ALLOW_QWEN38_QUANTIZATION") != EXECUTION_CONFIRMATION:
        raise QuantizationAssetError("set ALLOW_QWEN38_QUANTIZATION=YES for explicit execution")
    plan = _strictly_revalidate_final_plan(plan)
    if DOCKER_IMAGE_ID_PATTERN.fullmatch(image_id) is None:
        raise QuantizationAssetError("Docker tool image must be an exact local sha256 image ID")
    owner_uid = os.getuid()
    owner_gid = os.getgid()
    _require_owner_only_evidence_target(evidence_output, owner_uid=owner_uid)

    # Complete all host-path and digest checks before inspecting or running Docker.
    input_digests: dict[str, str] = {}
    reuse_digests: dict[str, str] = {}
    for command in plan.commands:
        output = Path(command.output_path)
        _require_output_parent(output, owner_uid=owner_uid)
        for raw_path, expected_digest in command.input_digests.items():
            if raw_path == DOCKER_QUANTIZE_BINARY:
                if expected_digest != plan.quantize_binary_digest:
                    raise QuantizationAssetError("quantizer digest differs within the plan")
                continue
            path = Path(raw_path)
            _require_canonical_regular_file(path)
            if output.parent in path.parents:
                raise QuantizationAssetError(
                    "Docker input cannot be inside the writable output parent"
                )
            observed = input_digests.get(raw_path)
            if observed is None:
                observed = digest_regular_file(path)
                input_digests[raw_path] = observed
            if observed != expected_digest:
                raise QuantizationAssetError(f"input digest mismatch: {raw_path}")
        if output.exists() or output.is_symlink():
            if command.expected_output_digest is None:
                raise QuantizationAssetError(f"refusing to overwrite quantization output: {output}")
            output_digest = digest_regular_file(output)
            if output_digest != command.expected_output_digest:
                raise QuantizationAssetError(
                    f"existing output digest mismatch at quantization step {command.order}"
                )
            reuse_digests[str(output)] = output_digest

    _verify_local_tool_image(
        image_id=image_id,
        expected_binary_digest=plan.quantize_binary_digest,
        owner_uid=owner_uid,
        owner_gid=owner_gid,
    )

    command_evidence: list[dict[str, object]] = []
    try:
        for command in plan.commands:
            output = Path(command.output_path)
            output_digest = reuse_digests.get(str(output))
            reused = output_digest is not None
            if not reused:
                if output.exists() or output.is_symlink():
                    raise QuantizationAssetError(
                        f"quantization output appeared after preflight: {output}"
                    )
                mounted_inputs = tuple(
                    Path(path) for path in command.input_digests if path != DOCKER_QUANTIZE_BINARY
                )
                docker_argv = _docker_quantize_argv(
                    command_argv=command.argv,
                    input_paths=mounted_inputs,
                    output_parent=output.parent,
                    image_id=image_id,
                    owner_uid=owner_uid,
                    owner_gid=owner_gid,
                )
                _run_docker_checked(docker_argv, capture_output=False)
                output_digest = digest_regular_file(output)
            assert output_digest is not None
            if (
                command.expected_output_digest is not None
                and output_digest != command.expected_output_digest
            ):
                raise QuantizationAssetError(
                    f"output digest mismatch at quantization step {command.order}"
                )
            command_evidence.append(
                {
                    "order": command.order,
                    "operation": command.operation,
                    "recipe_name": command.recipe_name,
                    "recipe_digest": command.recipe_digest,
                    "output_name": output.name,
                    "output_digest": output_digest,
                    "output_bytes": output.stat().st_size,
                    "execution": "REUSED_VERIFIED" if reused else "EXECUTED",
                }
            )

        # A later command shares the output-parent mount. Re-hash every candidate so
        # the recorded values describe the final on-disk state, not an intermediate one.
        for command, record in zip(plan.commands, command_evidence, strict=True):
            output = Path(command.output_path)
            final_digest = digest_regular_file(output)
            if final_digest != record["output_digest"]:
                raise QuantizationAssetError(
                    f"candidate changed after quantization step {command.order}"
                )
            record["output_bytes"] = output.stat().st_size

        # Docker receives host bind mounts by pathname. Re-hash every pinned host
        # input after all commands so an accidental concurrent change cannot produce
        # PASS evidence for candidates built from different bytes.
        for raw_path, expected_digest in input_digests.items():
            if digest_regular_file(Path(raw_path)) != expected_digest:
                raise QuantizationAssetError("quantization input changed during execution")
    except QuantizationAssetError:
        failure_evidence: dict[str, object] = {
            "schema_version": "llama_cpp_quantization_run_evidence/1.1.0",
            "status": "FAIL",
            "failure_code": "QUANTIZATION_EXECUTION_FAILED",
            "execution_mode": "DOCKER_OFFLINE",
            "phase": plan.phase,
            "plan_digest": plan.plan_digest,
            "llama_cpp_revision": plan.llama_cpp_revision,
            "tool_image_id": image_id,
            "quantize_binary_path": DOCKER_QUANTIZE_BINARY,
            "quantize_binary_digest": plan.quantize_binary_digest,
            "completed_commands": command_evidence,
            "partial_outputs": _partial_output_evidence(plan),
            "final_candidates_from_bf16": True,
            "q8_helper_used_as_final_source": False,
            "sealed_test_data_used": False,
            "shell_interpolation_used": False,
        }
        _write_owner_only_json_once(evidence_output, failure_evidence)
        raise

    evidence: dict[str, object] = {
        "schema_version": "llama_cpp_quantization_run_evidence/1.1.0",
        "status": "PASS",
        "execution_mode": "DOCKER_OFFLINE",
        "phase": plan.phase,
        "plan_digest": plan.plan_digest,
        "llama_cpp_revision": plan.llama_cpp_revision,
        "tool_image_id": image_id,
        "quantize_binary_path": DOCKER_QUANTIZE_BINARY,
        "quantize_binary_digest": plan.quantize_binary_digest,
        "docker_limits": {
            "cpus": DOCKER_CPU_LIMIT,
            "memory": DOCKER_MEMORY_LIMIT,
            "memory_swap": DOCKER_MEMORY_LIMIT,
            "pids": DOCKER_PIDS_LIMIT,
            "network": "NONE",
            "root_filesystem": "READ_ONLY",
            "gpu_devices": "NONE",
            "pull": "NEVER",
            "uid": owner_uid,
            "gid": owner_gid,
        },
        "commands": command_evidence,
        "all_host_inputs_reverified_after_execution": True,
        "final_candidates_from_bf16": True,
        "q8_helper_used_as_final_source": False,
        "sealed_test_data_used": False,
        "shell_interpolation_used": False,
    }
    _write_owner_only_json_once(evidence_output, evidence)
    return evidence


def execute_run_plan(
    plan: LlamaCppQuantizationRunPlan,
    *,
    evidence_output: Path,
) -> dict[str, object]:
    if os.environ.get("ALLOW_QWEN38_QUANTIZATION") != EXECUTION_CONFIRMATION:
        raise QuantizationAssetError("set ALLOW_QWEN38_QUANTIZATION=YES for explicit execution")
    if evidence_output.is_symlink() or evidence_output.exists():
        raise QuantizationAssetError("refusing to overwrite run evidence")
    if not evidence_output.parent.is_dir() or evidence_output.parent.is_symlink():
        raise QuantizationAssetError("run evidence parent must be an existing regular directory")
    observed_outputs: dict[str, str] = {}
    command_evidence: list[dict[str, object]] = []
    for command in plan.commands:
        output = Path(command.output_path)
        if not output.parent.is_dir() or output.parent.is_symlink():
            raise QuantizationAssetError(f"output parent is not a regular directory: {output}")
        validate_command_inputs(
            expected=command.input_digests,
            generated=command.generated_input_paths,
            observed_outputs=observed_outputs,
        )
        reused = output.exists() or output.is_symlink()
        if reused:
            if command.expected_output_digest is None:
                raise QuantizationAssetError(f"refusing to overwrite quantization output: {output}")
            output_digest = digest_regular_file(output)
            if output_digest != command.expected_output_digest:
                raise QuantizationAssetError(
                    f"existing output digest mismatch at quantization step {command.order}"
                )
        else:
            try:
                subprocess.run(list(command.argv), check=True)
            except (FileNotFoundError, subprocess.CalledProcessError) as error:
                raise QuantizationAssetError(
                    f"quantization command failed at step {command.order}"
                ) from error
            output_digest = digest_regular_file(output)
        if (
            command.expected_output_digest is not None
            and output_digest != command.expected_output_digest
        ):
            raise QuantizationAssetError(
                f"output digest mismatch at quantization step {command.order}"
            )
        observed_outputs[str(output)] = output_digest
        command_evidence.append(
            {
                "order": command.order,
                "operation": command.operation,
                "recipe_name": command.recipe_name,
                "recipe_digest": command.recipe_digest,
                "output_path": str(output),
                "output_digest": output_digest,
                "execution": "REUSED_VERIFIED" if reused else "EXECUTED",
            }
        )
    evidence: dict[str, object] = {
        "schema_version": "llama_cpp_quantization_run_evidence/1.0.0",
        "plan_digest": plan.plan_digest,
        "phase": plan.phase,
        "llama_cpp_revision": plan.llama_cpp_revision,
        "commands": command_evidence,
        "final_candidates_from_bf16": plan.final_candidates_from_bf16,
        "q8_helper_used_as_final_source": False,
        "sealed_test_data_used": False,
    }
    evidence_output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence


def main() -> int:
    arguments = _arguments()
    plan = load_run_plan(arguments.plan)
    if not arguments.execute:
        print(
            "QWEN38_QUANTIZATION_PLAN_VALID "
            f"phase={plan.phase} commands={len(plan.commands)} digest={plan.plan_digest}"
        )
        return 0
    if arguments.evidence_output is None:
        raise QuantizationAssetError("--evidence-output is required with --execute")
    if arguments.docker_image_id is None:
        raise QuantizationAssetError("--docker-image-id is required with --execute")
    execute_final_run_plan_in_docker(
        plan,
        image_id=arguments.docker_image_id,
        evidence_output=arguments.evidence_output,
    )
    print(
        "QWEN38_QUANTIZATION_PLAN_EXECUTED "
        f"phase={plan.phase} commands={len(plan.commands)} evidence={arguments.evidence_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
