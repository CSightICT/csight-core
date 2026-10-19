"""Run one unpublished GGUF candidate across the three synthetic Dev tasks.

The llama.cpp server stays on the protected RTX 4090 host.  This client runs on
the Mac so Query Builder continues to use the real local PostgreSQL and
Embedding retrieval path.  It never opens sealed Test, freezes a profile, or
routes the candidate into Core.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import importlib.metadata
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import SplitResult, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform.candidate_evaluation import (  # noqa: E402
    CandidateEvaluationError,
    CandidateEvaluationProfile,
    EvaluationCandidate,
    EvaluationGateResult,
    ExtractionEvaluationMetrics,
    GroundingEvaluationMetrics,
    InjectionEvaluationMetrics,
    QueryEvaluationMetrics,
    canonical_digest,
)
from app.platform.qwen4090_gguf import LocalUnpublishedGGUFDevIdentity  # noqa: E402
from scripts import evaluate_qwen4090_candidate_tasks as evaluator  # noqa: E402

DEFAULT_MATRIX = ROOT / "evaluation/llm/qwen4090_candidate_matrix_v2.json"
DEFAULT_RESULT_ROOT = ROOT / "evaluation/results/qwen4090_candidate_tasks"

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_DIGEST_RE = re.compile(_DIGEST_PATTERN)
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")
_REMOTE_PORT = 18002
_MAX_ENV_BYTES = 64 * 1024
_MAX_HTTP_BYTES = 1024 * 1024
_MAX_CHILD_OUTPUT_BYTES = 1024 * 1024
_TASKS = ("extraction", "query-builder", "grounding")

_SOURCE_FIXED_FILES = (
    "pyproject.toml",
    "uv.lock",
    "scripts/evaluate_qwen4090_candidate_tasks.py",
    "scripts/run_qwen4090_candidate_dev.py",
    "evaluation/llm_extraction_v2/gold.jsonl",
    "evaluation/llm_extraction_v2/manifest.json",
    "evaluation/policy_query_builder_v1/gold.jsonl",
    "evaluation/policy_query_builder_v1/manifest.json",
    "evaluation/rag_grounding_v1/gold.jsonl",
    "evaluation/rag_grounding_v1/manifest.json",
    "evaluation/prompt_injection_v1/gold.jsonl",
    "evaluation/prompt_injection_v1/manifest.json",
    "data/policy_corpus/clauses/policy_clauses_v1.jsonl",
)

_ALLOWED_EVALUATION_KEYS = {
    "DATABASE_URL",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_TIMEOUT_SECONDS",
    "ENVIRONMENT",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_CONNECT_TIMEOUT_SECONDS",
    "LLM_MAX_INPUT_CHARS",
    "LLM_MAX_OUTPUT_CHARS",
    "LLM_MAX_OUTPUT_TOKENS",
    "LLM_MODEL_ID",
    "LLM_MODEL_VERSION",
    "LLM_PROVIDER",
    "LLM_READ_TIMEOUT_SECONDS",
    "LLM_TASK_RUNTIMES",
    "LLM_TEMPERATURE",
    "LLM_TLS_VERIFY",
    "MODEL_RELEASE_ENFORCEMENT",
    "MODEL_ROUTE_ENFORCEMENT",
    "PROVIDER_CIRCUIT_FAILURE_THRESHOLD",
    "PROVIDER_CIRCUIT_OPEN_SECONDS",
}

_FORBIDDEN_EVALUATION_KEYS = {
    "LLM_ARTIFACT_CONTENT_DIGEST",
    "LLM_DEPENDENCY_LOCK_DIGEST",
    "LLM_GGUF_RUNTIME_IDENTITIES",
    "LLM_GGUF_RUNTIME_IDENTITY",
    "LLM_MODEL_REVISION",
    "LLM_RUNTIME_IMAGE_DIGEST",
    "LLM_SBOM_DIGEST",
    "MODEL_RELEASE_SIGNING_KEY_ID",
    "MODEL_RELEASE_SIGNING_PUBLIC_KEY_FILE",
    "MODEL_ROUTE_DEPLOYMENT_ID",
    "PILOT_QUALIFICATION_EVIDENCE",
}


class CandidateDevDriverError(RuntimeError):
    """One stable technical failure that is safe to report without raw model data."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _StrictEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CandidateDevTaskSummary(_StrictEvidence):
    task: Literal["extraction", "query-builder", "grounding"]
    gate_passed: bool
    record_count: int = Field(gt=0)
    success_count: int = Field(ge=0)
    profile_digest: str = Field(pattern=_DIGEST_PATTERN)
    observation_evidence_digest: str = Field(pattern=_DIGEST_PATTERN)
    metrics_digest: str = Field(pattern=_DIGEST_PATTERN)
    injection_metrics_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    gate_digest: str = Field(pattern=_DIGEST_PATTERN)
    typed_synthetic_predictions_retained: Literal[True] = True
    raw_provider_response_retained: Literal[False] = False
    provider_request_id_retained: Literal[False] = False
    raw_customer_data_retained: Literal[False] = False


class LocalDevPostStartEvidence(_StrictEvidence):
    schema_version: Literal["qwen4090_local_gguf_dev_post_start/1.0.0"]
    status: Literal["DEV_LOCAL_RUNNING"]
    candidate_id: str
    candidate_matrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    local_dev_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    artifact_revision: None
    artifact_content_digest: str = Field(pattern=_DIGEST_PATTERN)
    artifact_weight_bytes: int = Field(gt=0)
    quantization_run_evidence_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_build_manifest_digest: str = Field(pattern=_DIGEST_PATTERN)
    sbom_digest: str = Field(pattern=_DIGEST_PATTERN)
    llama_cpp_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    served_model_name: str
    compose_config_digest: str = Field(pattern=_DIGEST_PATTERN)
    container_inspect_digest: str = Field(pattern=_DIGEST_PATTERN)
    container_instance_digest: str = Field(pattern=_DIGEST_PATTERN)
    authenticated_canary: Literal[True]
    release_eligible: Literal[False]
    primary_allowed: Literal[False]
    core_routing_allowed: Literal[False]
    sealed_test_allowed: Literal[False]


class CandidateDevExecutionManifest(_StrictEvidence):
    schema_version: Literal["qwen4090_candidate_dev_execution/1.0.0"] = (
        "qwen4090_candidate_dev_execution/1.0.0"
    )
    status: Literal["COMPLETE"] = "COMPLETE"
    candidate_id: str
    candidate_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    local_dev_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    local_dev_preflight_evidence_digest: str = Field(pattern=_DIGEST_PATTERN)
    candidate_matrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    source_bundle_digest: str = Field(pattern=_DIGEST_PATTERN)
    dependency_lock_digest: str = Field(pattern=_DIGEST_PATTERN)
    installed_distribution_digest: str = Field(pattern=_DIGEST_PATTERN)
    python_version: str
    endpoint_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    started_at: datetime
    completed_at: datetime
    tasks: tuple[CandidateDevTaskSummary, CandidateDevTaskSummary, CandidateDevTaskSummary]
    all_task_gates_passed: bool
    split: Literal["dev"] = "dev"
    execution_scope: Literal["DEV_LOCAL"] = "DEV_LOCAL"
    artifact_revision: None = None
    frozen_profile_created: Literal[False] = False
    sealed_test_used: Literal[False] = False
    release_eligible: Literal[False] = False
    primary_allowed: Literal[False] = False
    core_routing_allowed: Literal[False] = False
    automatic_cross_model_fallback: Literal[False] = False
    external_business_actions_performed: Literal[False] = False
    raw_customer_data_retained: Literal[False] = False

    @model_validator(mode="after")
    def require_task_order_and_gate_summary(self) -> CandidateDevExecutionManifest:
        if tuple(item.task for item in self.tasks) != _TASKS:
            raise ValueError("candidate Dev tasks must use the frozen execution order")
        if self.all_task_gates_passed != all(item.gate_passed for item in self.tasks):
            raise ValueError("candidate gate summary differs from task evidence")
        if self.completed_at < self.started_at:
            raise ValueError("candidate completion precedes its start")
        return self


class CandidateDevFailureEvidence(_StrictEvidence):
    schema_version: Literal["qwen4090_candidate_dev_failure/1.0.0"] = (
        "qwen4090_candidate_dev_failure/1.0.0"
    )
    status: Literal["FAILED"] = "FAILED"
    candidate_id: str
    failure_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    candidate_matrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    source_bundle_digest: str = Field(pattern=_DIGEST_PATTERN)
    dependency_lock_digest: str = Field(pattern=_DIGEST_PATTERN)
    failed_at: datetime
    split: Literal["dev"] = "dev"
    sealed_test_used: Literal[False] = False
    release_eligible: Literal[False] = False
    external_business_actions_performed: Literal[False] = False
    raw_customer_data_retained: Literal[False] = False


class CandidateDevSelectionManifest(_StrictEvidence):
    schema_version: Literal["qwen4090_candidate_dev_selection/1.0.0"] = (
        "qwen4090_candidate_dev_selection/1.0.0"
    )
    candidate_matrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    source_bundle_digest: str = Field(pattern=_DIGEST_PATTERN)
    dependency_lock_digest: str = Field(pattern=_DIGEST_PATTERN)
    candidate_execution_manifest_digests: tuple[str, str]
    decision_digest: str = Field(pattern=_DIGEST_PATTERN)
    decision_status: str
    winner_candidate_id: str | None
    selected_at: datetime
    split: Literal["dev"] = "dev"
    test_evidence_used: Literal[False] = False
    release_eligible: Literal[False] = False
    core_activation_created: Literal[False] = False


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    inputs = subparsers.add_parser("inputs", help="print non-secret input digests")
    inputs.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)

    run = subparsers.add_parser("run-candidate", help="run all three Dev tasks for one candidate")
    run.add_argument("--candidate-id", required=True)
    run.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    run.add_argument("--evaluation-env", type=Path, required=True)
    run.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    run.add_argument("--expected-source-bundle-digest", required=True)
    run.add_argument("--expected-lock-digest", required=True)
    run.add_argument("--local-dev-preflight-evidence", type=Path, required=True)
    run.add_argument("--task-timeout-seconds", type=int, default=14_400)

    select = subparsers.add_parser("select-winner", help="select from two complete Dev packages")
    select.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    select.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    select.add_argument("--expected-source-bundle-digest", required=True)
    select.add_argument("--expected-lock-digest", required=True)
    return parser.parse_args()


def _file_bytes(path: Path, *, maximum_bytes: int | None = None) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CandidateDevDriverError("INPUT_FILE_INVALID", "required input is not a regular file")
    before = path.stat()
    if maximum_bytes is not None and (before.st_size <= 0 or before.st_size > maximum_bytes):
        raise CandidateDevDriverError("INPUT_FILE_INVALID", "required input size is invalid")
    content = path.read_bytes()
    after = path.stat()
    if (
        before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise CandidateDevDriverError("INPUT_FILE_CHANGED", "required input changed while read")
    return content


def _digest_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _file_digest(path: Path) -> str:
    return _digest_bytes(_file_bytes(path))


def _source_paths() -> tuple[Path, ...]:
    app_sources = tuple(
        path for path in (ROOT / "app").rglob("*.py") if "__pycache__" not in path.parts
    )
    paths = (*app_sources, *(ROOT / value for value in _SOURCE_FIXED_FILES))
    if len(paths) != len(set(paths)):
        raise CandidateDevDriverError("SOURCE_BUNDLE_INVALID", "source bundle has duplicates")
    return tuple(sorted(paths, key=lambda value: value.relative_to(ROOT).as_posix()))


def source_bundle_digest() -> str:
    digest = hashlib.sha256()
    for path in _source_paths():
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        content = _file_bytes(path)
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def installed_distribution_digest() -> str:
    distributions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        if not raw_name:
            continue
        name = re.sub(r"[-_.]+", "-", raw_name).lower()
        version = distribution.version
        prior = distributions.get(name)
        if prior is not None and prior != version:
            raise CandidateDevDriverError(
                "PYTHON_ENVIRONMENT_INVALID",
                "installed environment contains duplicate distribution versions",
            )
        distributions[name] = version
    return _digest_bytes(
        json.dumps(distributions, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _verify_python_environment(expected_lock_digest: str) -> tuple[str, str]:
    if not _DIGEST_RE.fullmatch(expected_lock_digest):
        raise CandidateDevDriverError("LOCK_DIGEST_INVALID", "expected lock digest is invalid")
    if sys.version_info[:2] != (3, 12):
        raise CandidateDevDriverError("PYTHON_VERSION_INVALID", "Python 3.12 is required")
    if sys.prefix == sys.base_prefix:
        raise CandidateDevDriverError(
            "PYTHON_ENVIRONMENT_INVALID",
            "an isolated virtual environment is required",
        )
    lock_digest = _file_digest(ROOT / "uv.lock")
    if lock_digest != expected_lock_digest:
        raise CandidateDevDriverError("LOCK_DIGEST_MISMATCH", "dependency lock digest drifted")

    project = tomllib.loads(_file_bytes(ROOT / "pyproject.toml").decode("utf-8"))
    dependencies = project.get("project", {}).get("dependencies", [])
    for declaration in dependencies:
        if not isinstance(declaration, str) or "==" not in declaration:
            raise CandidateDevDriverError(
                "DEPENDENCY_CONTRACT_INVALID",
                "project runtime dependencies must remain exactly pinned",
            )
        raw_name, expected_version = declaration.split("==", 1)
        package_name = raw_name.split("[", 1)[0]
        try:
            installed_version = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError as error:
            raise CandidateDevDriverError(
                "PYTHON_ENVIRONMENT_INVALID",
                "a pinned runtime distribution is missing",
            ) from error
        if installed_version != expected_version:
            raise CandidateDevDriverError(
                "PYTHON_ENVIRONMENT_INVALID",
                "a pinned runtime distribution version differs",
            )
    return lock_digest, installed_distribution_digest()


def _private_env(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise CandidateDevDriverError("EVALUATION_ENV_INVALID", "evaluation env is not regular")
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise CandidateDevDriverError(
            "EVALUATION_ENV_INVALID",
            "evaluation env must be caller-owned mode 600",
        )
    content = _file_bytes(path, maximum_bytes=_MAX_ENV_BYTES).decode("utf-8")
    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise CandidateDevDriverError("EVALUATION_ENV_INVALID", "malformed env line")
        name, value = line.split("=", 1)
        if not _ENV_NAME.fullmatch(name) or name in values:
            raise CandidateDevDriverError("EVALUATION_ENV_INVALID", "invalid or duplicate env key")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    if set(values).difference(_ALLOWED_EVALUATION_KEYS):
        raise CandidateDevDriverError(
            "EVALUATION_ENV_KEY_FORBIDDEN",
            "evaluation env contains a key outside the candidate-evaluation allowlist",
        )
    return values


def _false(value: str | None) -> bool:
    return value is None or value.strip().lower() in {"", "0", "false", "no", "off"}


def _url(value: str, *, code: str) -> SplitResult:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise CandidateDevDriverError(code, "configured URL is not an allowed HTTP endpoint")
    return parsed


def _validate_evaluation_env(
    values: Mapping[str, str],
    *,
    candidate: EvaluationCandidate,
) -> SplitResult:
    forbidden = tuple(
        sorted(name for name in _FORBIDDEN_EVALUATION_KEYS if values.get(name, "").strip())
    )
    if forbidden:
        raise CandidateDevDriverError(
            "RELEASE_IDENTITY_FORBIDDEN",
            "DEV_LOCAL evaluation cannot receive release identity fields",
        )
    expected = {
        "ENVIRONMENT": "local",
        "LLM_PROVIDER": "llama_cpp",
        "LLM_MODEL_ID": candidate.served_model_name,
        "LLM_MODEL_VERSION": candidate.candidate_id,
        "LLM_MAX_OUTPUT_TOKENS": str(candidate.max_output_tokens),
        "LLM_TLS_VERIFY": "false",
    }
    if any(values.get(name) != required for name, required in expected.items()):
        raise CandidateDevDriverError(
            "EVALUATION_IDENTITY_MISMATCH",
            "evaluation env differs from the selected candidate",
        )
    if values.get("LLM_TASK_RUNTIMES", "{}").strip() not in {"", "{}"}:
        raise CandidateDevDriverError(
            "TASK_RUNTIME_OVERRIDE_FORBIDDEN",
            "task-specific runtime overrides are forbidden in candidate comparison",
        )
    if not _false(values.get("MODEL_RELEASE_ENFORCEMENT")) or not _false(
        values.get("MODEL_ROUTE_ENFORCEMENT")
    ):
        raise CandidateDevDriverError(
            "ROUTING_FORBIDDEN",
            "DEV_LOCAL cannot enable release or route enforcement",
        )
    try:
        if float(values.get("LLM_TEMPERATURE", "0")) != 0.0:
            raise ValueError
    except ValueError as error:
        raise CandidateDevDriverError(
            "NONDETERMINISTIC_PROFILE",
            "candidate comparison requires temperature zero",
        ) from error

    api_key = values.get("LLM_API_KEY", "")
    lowered_key = api_key.lower()
    if (
        len(api_key) < 32
        or any(value in lowered_key for value in ("replace", "example", "change-me", "redacted"))
        or any(character.isspace() for character in api_key)
    ):
        raise CandidateDevDriverError("LLM_AUTH_INVALID", "private endpoint API key is invalid")

    endpoint = _url(values.get("LLM_BASE_URL", ""), code="LLM_ENDPOINT_INVALID")
    try:
        endpoint_ip = ipaddress.ip_address(endpoint.hostname or "")
    except ValueError as error:
        raise CandidateDevDriverError(
            "LLM_ENDPOINT_INVALID",
            "candidate endpoint must use its Tailscale IPv4 address",
        ) from error
    if (
        endpoint.scheme != "http"
        or endpoint_ip not in _TAILSCALE_NETWORK
        or endpoint.port != _REMOTE_PORT
        or endpoint.path.rstrip("/") != "/v1"
    ):
        raise CandidateDevDriverError(
            "LLM_ENDPOINT_INVALID",
            "candidate endpoint must be Tailscale HTTP port 18002 /v1",
        )

    database_url = values.get("DATABASE_URL", "")
    try:
        database = make_url(database_url)
    except (ArgumentError, TypeError, ValueError) as error:
        raise CandidateDevDriverError(
            "LOCAL_RETRIEVAL_INVALID", "DATABASE_URL is invalid"
        ) from error
    if not database.drivername.startswith("postgresql") or database.host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise CandidateDevDriverError(
            "LOCAL_RETRIEVAL_INVALID",
            "query evaluation must use the Mac-local PostgreSQL",
        )
    embedding = _url(
        values.get("EMBEDDING_BASE_URL", ""),
        code="LOCAL_RETRIEVAL_INVALID",
    )
    if (
        embedding.scheme != "http"
        or embedding.hostname not in {"127.0.0.1", "localhost", "::1"}
        or embedding.port != 8091
        or embedding.path not in {"", "/"}
    ):
        raise CandidateDevDriverError(
            "LOCAL_RETRIEVAL_INVALID",
            "query evaluation must use the Mac-local embedding endpoint on 8091",
        )
    return endpoint


def _validate_local_dev_preflight_evidence(
    path: Path,
    *,
    matrix: Path,
    candidate: EvaluationCandidate,
) -> tuple[LocalDevPostStartEvidence, str]:
    if path.is_symlink() or not path.is_file():
        raise CandidateDevDriverError(
            "LOCAL_DEV_PREFLIGHT_INVALID",
            "Khrin post-start evidence must be a regular file",
        )
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise CandidateDevDriverError(
            "LOCAL_DEV_PREFLIGHT_INVALID",
            "Khrin post-start evidence must be caller-owned mode 600",
        )
    content = _file_bytes(path, maximum_bytes=1024 * 1024)
    try:
        evidence = LocalDevPostStartEvidence.model_validate_json(content)
    except ValidationError as error:
        raise CandidateDevDriverError(
            "LOCAL_DEV_PREFLIGHT_INVALID",
            "Khrin post-start evidence failed its strict schema",
        ) from error
    matrix_value = evaluator._load_json(  # pyright: ignore[reportPrivateUsage]
        matrix,
        evaluator.Qwen4090CandidateMatrixV2,
    )
    matches = tuple(
        item for item in matrix_value.candidates if item.candidate_id == candidate.candidate_id
    )
    if len(matches) != 1:
        raise CandidateDevDriverError(
            "LOCAL_DEV_PREFLIGHT_INVALID",
            "selected candidate is not present exactly once in the matrix",
        )
    matrix_candidate = matches[0]
    artifact = matrix_candidate.artifact
    serving = matrix_candidate.serving
    expected = {
        "candidate_id": candidate.candidate_id,
        "candidate_matrix_digest": matrix_value.matrix_digest,
        "artifact_content_digest": candidate.artifact_content_digest,
        "artifact_weight_bytes": candidate.artifact_weight_bytes,
        "runtime_image_digest": serving.runtime_image_digest,
        "runtime_binary_digest": serving.runtime_binary_digest,
        "runtime_build_manifest_digest": serving.runtime_build_manifest_digest,
        "sbom_digest": serving.sbom_digest,
        "llama_cpp_revision": serving.llama_cpp_revision,
        "served_model_name": candidate.served_model_name,
    }
    observed = {
        "candidate_id": evidence.candidate_id,
        "candidate_matrix_digest": evidence.candidate_matrix_digest,
        "artifact_content_digest": evidence.artifact_content_digest,
        "artifact_weight_bytes": evidence.artifact_weight_bytes,
        "runtime_image_digest": evidence.runtime_image_digest,
        "runtime_binary_digest": evidence.runtime_binary_digest,
        "runtime_build_manifest_digest": evidence.runtime_build_manifest_digest,
        "sbom_digest": evidence.sbom_digest,
        "llama_cpp_revision": evidence.llama_cpp_revision,
        "served_model_name": evidence.served_model_name,
    }
    try:
        expected_local_identity = LocalUnpublishedGGUFDevIdentity.from_candidate(
            matrix_candidate,
            candidate_matrix_digest=matrix_value.matrix_digest,
            quantization_run_evidence_digest=evidence.quantization_run_evidence_digest,
        )
    except ValueError as error:
        raise CandidateDevDriverError(
            "LOCAL_DEV_PREFLIGHT_MISMATCH",
            "matrix candidate cannot reproduce the Khrin local Dev identity",
        ) from error
    if (
        observed != expected
        or artifact.artifact_revision is not None
        or evidence.local_dev_identity_digest != expected_local_identity.identity_digest
    ):
        raise CandidateDevDriverError(
            "LOCAL_DEV_PREFLIGHT_MISMATCH",
            "Khrin post-start evidence differs from the local unpublished candidate matrix",
        )
    return evidence, _digest_bytes(content)


def _safe_result_root(path: Path, *, create: bool) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise CandidateDevDriverError("RESULT_ROOT_INVALID", "result root must be absolute")
    if create and not path.exists():
        path.mkdir(parents=True, mode=0o700)
    if not path.is_dir():
        raise CandidateDevDriverError("RESULT_ROOT_INVALID", "result root is not a directory")
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise CandidateDevDriverError(
            "RESULT_ROOT_INVALID",
            "result root must be caller-owned mode 700",
        )
    return path.resolve(strict=True)


def _probe_endpoint(
    endpoint: SplitResult,
    *,
    api_key: str,
    expected_model: str,
) -> str:
    host = endpoint.hostname or ""
    port = endpoint.port or 80
    connection = http.client.HTTPConnection(host, port, timeout=15)
    try:
        connection.request(
            "GET",
            endpoint.path.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response = connection.getresponse()
        content = response.read(_MAX_HTTP_BYTES + 1)
    except (OSError, TimeoutError, http.client.HTTPException) as error:
        raise CandidateDevDriverError(
            "CANDIDATE_ENDPOINT_UNAVAILABLE",
            "candidate endpoint probe failed",
        ) from error
    finally:
        connection.close()
    if response.status != 200 or len(content) > _MAX_HTTP_BYTES:
        raise CandidateDevDriverError(
            "CANDIDATE_ENDPOINT_INVALID",
            "candidate endpoint did not return bounded HTTP 200",
        )
    try:
        document = json.loads(content)
        model_ids = [item["id"] for item in document["data"]]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise CandidateDevDriverError(
            "CANDIDATE_ENDPOINT_INVALID",
            "candidate endpoint model response is invalid",
        ) from error
    if model_ids != [expected_model]:
        raise CandidateDevDriverError(
            "CANDIDATE_ENDPOINT_IDENTITY_MISMATCH",
            "candidate endpoint returned a different model identity",
        )
    return _digest_bytes(
        json.dumps(
            {"schema_version": "candidate_endpoint_identity/1.0.0", "models": model_ids},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _child_environment() -> dict[str, str]:
    allowed = ("PATH", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE")
    child = {name: os.environ[name] for name in allowed if os.environ.get(name)}
    child.update(
        {
            "HF_HUB_OFFLINE": "1",
            "PIP_NO_INDEX": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": str(ROOT),
            "TRANSFORMERS_OFFLINE": "1",
            "UV_OFFLINE": "1",
        }
    )
    return child


def _run_task_process(
    *,
    task: str,
    candidate_id: str,
    matrix: Path,
    evaluation_env: Path,
    result_root: Path,
    timeout_seconds: int,
) -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts/evaluate_qwen4090_candidate_tasks.py"),
        "--task",
        task,
        "--split",
        "dev",
        "--matrix",
        str(matrix),
        "--candidate-id",
        candidate_id,
        "--env-file",
        str(evaluation_env),
        "--result-root",
        str(result_root),
        "--generate-live",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=_child_environment(),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise CandidateDevDriverError(
            "TASK_TIMEOUT", "candidate task exceeded its timeout"
        ) from error
    if len(result.stdout) > _MAX_CHILD_OUTPUT_BYTES or len(result.stderr) > _MAX_CHILD_OUTPUT_BYTES:
        raise CandidateDevDriverError(
            "TASK_OUTPUT_UNBOUNDED", "candidate task output was unbounded"
        )
    if result.returncode not in {0, 1}:
        raise CandidateDevDriverError("TASK_EXECUTION_FAILED", "candidate task failed technically")
    expected_signal = (
        "CANDIDATE_TASK_EVALUATED "
        f"candidate={candidate_id} "
        f"task={evaluator._TASK_CANDIDATE[task].value} "  # pyright: ignore[reportPrivateUsage]
        "split=dev "
        f"passed={'true' if result.returncode == 0 else 'false'}"
    ).encode()
    if result.stdout.strip() != expected_signal or result.stderr.strip():
        raise CandidateDevDriverError(
            "TASK_EXECUTION_FAILED",
            "candidate task did not emit the exact privacy-safe completion signal",
        )
    return result.returncode


def _private_evidence_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise CandidateDevDriverError("TASK_EVIDENCE_INVALID", "task evidence file is missing")
    if path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise CandidateDevDriverError(
            "TASK_EVIDENCE_INVALID",
            "task evidence file must be caller-owned mode 600",
        )


def _load_model[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    _private_evidence_file(path)
    try:
        return model.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise CandidateDevDriverError(
            "TASK_EVIDENCE_INVALID",
            "task evidence failed strict validation",
        ) from error


def _validate_task_evidence(
    *,
    task: str,
    candidate: EvaluationCandidate,
    result_root: Path,
    return_code: int,
) -> CandidateDevTaskSummary:
    task_root = result_root / candidate.candidate_id / task
    if task_root.is_symlink() or not task_root.is_dir():
        raise CandidateDevDriverError("TASK_EVIDENCE_INVALID", "task evidence directory is missing")
    expected_files = {
        "dev_gate.json",
        "dev_metrics.json",
        "dev_observation_evidence.json",
        "dev_observation_score_binding.json",
        "dev_typed_observations.jsonl",
        "evaluation_profile.json",
    }
    if task == "grounding":
        expected_files.add("injection_dev_metrics.json")
    actual_files = {path.name for path in task_root.iterdir() if path.is_file()}
    if actual_files != expected_files:
        raise CandidateDevDriverError(
            "TASK_EVIDENCE_INVALID",
            "task evidence contains missing or unexpected files",
        )
    for path in task_root.iterdir():
        _private_evidence_file(path)

    profile = _load_model(task_root / "evaluation_profile.json", CandidateEvaluationProfile)
    expected_profile = evaluator._profile(task, candidate)  # pyright: ignore[reportPrivateUsage]
    if profile.profile_digest != expected_profile.profile_digest:
        raise CandidateDevDriverError("TASK_EVIDENCE_INVALID", "task profile identity drifted")
    gate = _load_model(task_root / "dev_gate.json", EvaluationGateResult)
    evidence = _load_model(
        task_root / "dev_observation_evidence.json",
        evaluator.CandidateObservationEvidence,
    )
    binding = _load_model(
        task_root / "dev_observation_score_binding.json",
        evaluator.ObservationScoreBinding,
    )
    if task == "extraction":
        metrics: ExtractionEvaluationMetrics | QueryEvaluationMetrics | GroundingEvaluationMetrics
        metrics = _load_model(task_root / "dev_metrics.json", ExtractionEvaluationMetrics)
        injection = None
    elif task == "query-builder":
        metrics = _load_model(task_root / "dev_metrics.json", QueryEvaluationMetrics)
        injection = None
    else:
        metrics = _load_model(task_root / "dev_metrics.json", GroundingEvaluationMetrics)
        injection = _load_model(
            task_root / "injection_dev_metrics.json",
            InjectionEvaluationMetrics,
        )
    try:
        evaluator._validate_observation_score_binding(  # pyright: ignore[reportPrivateUsage]
            binding=binding,
            evidence=evidence,
            profile=profile,
            metrics=metrics,
            injection_metrics=injection,
            gate=gate,
        )
    except CandidateEvaluationError as error:
        raise CandidateDevDriverError(
            "TASK_EVIDENCE_INVALID",
            "task score binding is invalid",
        ) from error
    if evidence.raw_customer_data_retained or evidence.raw_predictions_retained_in_result_package:
        raise CandidateDevDriverError(
            "TASK_PRIVACY_BOUNDARY_FAILED",
            "task evidence retained a forbidden raw payload",
        )
    if metrics.success_count == 0:
        raise CandidateDevDriverError(
            "TASK_PROVIDER_ZERO_SUCCESS",
            "candidate task produced no valid provider result",
        )
    if return_code != (0 if gate.passed else 1):
        raise CandidateDevDriverError(
            "TASK_EXIT_GATE_MISMATCH",
            "task process exit differs from its validated gate",
        )
    return CandidateDevTaskSummary(
        task=task,  # type: ignore[arg-type]
        gate_passed=gate.passed,
        record_count=metrics.record_count,
        success_count=metrics.success_count,
        profile_digest=profile.profile_digest,
        observation_evidence_digest=canonical_digest(evidence),
        metrics_digest=canonical_digest(metrics),
        injection_metrics_digest=(canonical_digest(injection) if injection is not None else None),
        gate_digest=canonical_digest(gate),
    )


def _write_json_exclusive(path: Path, value: BaseModel) -> str:
    if path.is_symlink() or path.exists():
        raise CandidateDevDriverError("EVIDENCE_ALREADY_EXISTS", "evidence is immutable")
    payload = (
        json.dumps(
            value.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return _digest_bytes(payload)


def _validate_expected_inputs(
    *,
    matrix: Path,
    expected_source_bundle_digest: str,
    expected_lock_digest: str,
) -> tuple[str, str, str, str]:
    if not _DIGEST_RE.fullmatch(expected_source_bundle_digest):
        raise CandidateDevDriverError("SOURCE_DIGEST_INVALID", "expected source digest is invalid")
    observed_source_digest = source_bundle_digest()
    if observed_source_digest != expected_source_bundle_digest:
        raise CandidateDevDriverError("SOURCE_DIGEST_MISMATCH", "evaluation source bundle drifted")
    lock_digest, distribution_digest = _verify_python_environment(expected_lock_digest)
    matrix_digest = _file_digest(matrix)
    return matrix_digest, observed_source_digest, lock_digest, distribution_digest


def run_candidate(arguments: argparse.Namespace) -> int:
    if not 60 <= arguments.task_timeout_seconds <= 43_200:
        raise CandidateDevDriverError("TASK_TIMEOUT_INVALID", "task timeout is outside bounds")
    matrix = arguments.matrix.resolve(strict=True)
    matrix_digest, source_digest, lock_digest, distribution_digest = _validate_expected_inputs(
        matrix=matrix,
        expected_source_bundle_digest=arguments.expected_source_bundle_digest,
        expected_lock_digest=arguments.expected_lock_digest,
    )
    candidate = evaluator.load_evaluation_candidate(matrix, arguments.candidate_id)
    if candidate.artifact_revision is not None:
        raise CandidateDevDriverError(
            "PUBLISHED_CANDIDATE_FORBIDDEN",
            "this driver accepts only local unpublished candidates",
        )
    result_root = _safe_result_root(arguments.result_root, create=True)
    candidate_root = result_root / candidate.candidate_id
    if candidate_root.exists() or candidate_root.is_symlink():
        raise CandidateDevDriverError(
            "CANDIDATE_EVIDENCE_ALREADY_EXISTS",
            "use a fresh result root for immutable candidate evidence",
        )
    candidate_root.mkdir(mode=0o700)
    started_at = datetime.now(UTC)
    summaries: list[CandidateDevTaskSummary] = []
    try:
        preflight_path = arguments.local_dev_preflight_evidence.resolve(strict=True)
        preflight, preflight_evidence_digest = _validate_local_dev_preflight_evidence(
            preflight_path,
            matrix=matrix,
            candidate=candidate,
        )
        evaluation_env = arguments.evaluation_env.resolve(strict=True)
        env_values = _private_env(evaluation_env)
        endpoint = _validate_evaluation_env(env_values, candidate=candidate)
        endpoint_digest = _probe_endpoint(
            endpoint,
            api_key=env_values["LLM_API_KEY"],
            expected_model=candidate.served_model_name,
        )
        for task in _TASKS:
            before_digest = _probe_endpoint(
                endpoint,
                api_key=env_values["LLM_API_KEY"],
                expected_model=candidate.served_model_name,
            )
            if before_digest != endpoint_digest:
                raise CandidateDevDriverError(
                    "CANDIDATE_ENDPOINT_CHANGED",
                    "candidate endpoint identity changed during Dev",
                )
            return_code = _run_task_process(
                task=task,
                candidate_id=candidate.candidate_id,
                matrix=matrix,
                evaluation_env=evaluation_env,
                result_root=result_root,
                timeout_seconds=arguments.task_timeout_seconds,
            )
            summaries.append(
                _validate_task_evidence(
                    task=task,
                    candidate=candidate,
                    result_root=result_root,
                    return_code=return_code,
                )
            )
        after_digest = _probe_endpoint(
            endpoint,
            api_key=env_values["LLM_API_KEY"],
            expected_model=candidate.served_model_name,
        )
        if after_digest != endpoint_digest:
            raise CandidateDevDriverError(
                "CANDIDATE_ENDPOINT_CHANGED",
                "candidate endpoint identity changed during Dev",
            )
        manifest = CandidateDevExecutionManifest(
            candidate_id=candidate.candidate_id,
            candidate_identity_digest=candidate.identity_digest,
            local_dev_identity_digest=preflight.local_dev_identity_digest,
            local_dev_preflight_evidence_digest=preflight_evidence_digest,
            candidate_matrix_digest=matrix_digest,
            source_bundle_digest=source_digest,
            dependency_lock_digest=lock_digest,
            installed_distribution_digest=distribution_digest,
            python_version=".".join(str(value) for value in sys.version_info[:3]),
            endpoint_identity_digest=endpoint_digest,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            tasks=tuple(summaries),  # type: ignore[arg-type]
            all_task_gates_passed=all(item.gate_passed for item in summaries),
        )
        manifest_digest = _write_json_exclusive(
            candidate_root / "candidate_dev_execution.json",
            manifest,
        )
    except CandidateDevDriverError as error:
        failure = CandidateDevFailureEvidence(
            candidate_id=candidate.candidate_id,
            failure_code=error.code,
            candidate_matrix_digest=matrix_digest,
            source_bundle_digest=source_digest,
            dependency_lock_digest=lock_digest,
            failed_at=datetime.now(UTC),
        )
        failure_path = candidate_root / "candidate_dev_failure.json"
        if not failure_path.exists():
            failure_digest = _write_json_exclusive(failure_path, failure)
            print(
                "QWEN4090_CANDIDATE_DEV_FAILURE_EVIDENCE "
                f"candidate={candidate.candidate_id} "
                f"failure_code={error.code} "
                f"manifest_digest={failure_digest}",
                file=sys.stderr,
            )
        raise
    print(
        "QWEN4090_CANDIDATE_DEV_COMPLETE "
        f"candidate={candidate.candidate_id} "
        f"all_gates_passed={str(manifest.all_task_gates_passed).lower()} "
        f"manifest_digest={manifest_digest}"
    )
    return 0


def _candidate_execution_manifests(
    *,
    matrix: Path,
    result_root: Path,
    matrix_digest: str,
    source_digest: str,
    lock_digest: str,
    distribution_digest: str,
    python_version: str,
) -> tuple[str, str]:
    matrix_value = evaluator._load_json(  # pyright: ignore[reportPrivateUsage]
        matrix,
        evaluator.Qwen4090CandidateMatrixV2,
    )
    candidate_ids = tuple(item.candidate_id for item in matrix_value.candidates)
    if len(candidate_ids) != 2:
        raise CandidateDevDriverError(
            "CANDIDATE_MATRIX_INVALID",
            "Dev selection requires exactly two candidates",
        )
    digests: list[str] = []
    for matrix_candidate in matrix_value.candidates:
        candidate_id = matrix_candidate.candidate_id
        candidate = evaluator.load_evaluation_candidate(matrix, candidate_id)
        path = result_root / candidate_id / "candidate_dev_execution.json"
        manifest = _load_model(path, CandidateDevExecutionManifest)
        if (
            manifest.candidate_id != candidate_id
            or manifest.candidate_identity_digest != candidate.identity_digest
            or manifest.candidate_matrix_digest != matrix_digest
            or manifest.source_bundle_digest != source_digest
            or manifest.dependency_lock_digest != lock_digest
            or manifest.installed_distribution_digest != distribution_digest
            or manifest.python_version != python_version
        ):
            raise CandidateDevDriverError(
                "CANDIDATE_EXECUTION_BINDING_INVALID",
                "candidate execution manifest differs from selection inputs",
            )
        digests.append(_file_digest(path))
    return digests[0], digests[1]


def select_winner(arguments: argparse.Namespace) -> int:
    matrix = arguments.matrix.resolve(strict=True)
    matrix_digest, source_digest, lock_digest, distribution_digest = _validate_expected_inputs(
        matrix=matrix,
        expected_source_bundle_digest=arguments.expected_source_bundle_digest,
        expected_lock_digest=arguments.expected_lock_digest,
    )
    result_root = _safe_result_root(arguments.result_root, create=False)
    execution_digests = _candidate_execution_manifests(
        matrix=matrix,
        result_root=result_root,
        matrix_digest=matrix_digest,
        source_digest=source_digest,
        lock_digest=lock_digest,
        distribution_digest=distribution_digest,
        python_version=".".join(str(value) for value in sys.version_info[:3]),
    )
    try:
        decision = evaluator.select_winner_from_result_root(
            matrix_path=matrix,
            result_root=result_root,
        )
    except CandidateEvaluationError as error:
        raise CandidateDevDriverError(
            "WINNER_EVIDENCE_INVALID",
            "winner evidence failed deterministic rescoring",
        ) from error
    decision_digest = _write_json_exclusive(
        result_root / "three_task_dev_winner.json",
        decision,
    )
    selection = CandidateDevSelectionManifest(
        candidate_matrix_digest=matrix_digest,
        source_bundle_digest=source_digest,
        dependency_lock_digest=lock_digest,
        candidate_execution_manifest_digests=execution_digests,
        decision_digest=canonical_digest(decision),
        decision_status=decision.status.value,
        winner_candidate_id=decision.winner_candidate_id,
        selected_at=datetime.now(UTC),
    )
    selection_digest = _write_json_exclusive(
        result_root / "three_task_dev_selection_manifest.json",
        selection,
    )
    if decision_digest != _file_digest(result_root / "three_task_dev_winner.json"):
        raise CandidateDevDriverError("WINNER_WRITE_INVALID", "winner evidence digest drifted")
    print(
        "QWEN4090_DEV_SELECTION_COMPLETE "
        f"status={decision.status.value} "
        f"winner={decision.winner_candidate_id or 'none'} "
        f"manifest_digest={selection_digest}"
    )
    return 0


def input_digests(matrix: Path) -> int:
    document = {
        "schema_version": "qwen4090_candidate_dev_inputs/1.0.0",
        "candidate_matrix_digest": _file_digest(matrix.resolve(strict=True)),
        "source_bundle_digest": source_bundle_digest(),
        "dependency_lock_digest": _file_digest(ROOT / "uv.lock"),
    }
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


def main() -> int:
    os.umask(0o077)
    arguments = _arguments()
    try:
        if arguments.operation == "inputs":
            return input_digests(arguments.matrix)
        if arguments.operation == "run-candidate":
            return run_candidate(arguments)
        return select_winner(arguments)
    except (
        CandidateDevDriverError,
        CandidateEvaluationError,
        OSError,
        ValidationError,
        ValueError,
    ) as error:
        code = getattr(error, "code", "CANDIDATE_DEV_DRIVER_FAILED")
        print(f"QWEN4090_CANDIDATE_DEV_FAILED code={code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
