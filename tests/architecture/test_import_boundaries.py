"""Protect the dependency direction documented by the accepted ADRs."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PURE_ROOTS = (PROJECT_ROOT / "app" / "platform", PROJECT_ROOT / "app" / "domains")
FORBIDDEN_TECHNOLOGIES = {
    "PIL",
    "celery",
    "fastapi",
    "httpx",
    "httpx2",
    "jwt",
    "minio",
    "mlx",
    "mlx_vlm",
    "multipart",
    "openai",
    "pwdlib",
    "sentence_transformers",
    "sqlalchemy",
    "transformers",
    "vllm",
}
APPLICATION_FORBIDDEN_TECHNOLOGIES = FORBIDDEN_TECHNOLOGIES


def imported_roots(path: Path) -> set[str]:
    """Return top-level package names imported by one Python module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


@pytest.mark.unit
def test_platform_and_domains_do_not_import_frameworks() -> None:
    violations: list[str] = []
    for root in PURE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            forbidden = imported_roots(path) & FORBIDDEN_TECHNOLOGIES
            if forbidden:
                relative_path = path.relative_to(PROJECT_ROOT)
                violations.append(f"{relative_path}: {', '.join(sorted(forbidden))}")

    assert not violations, "Forbidden imports found:\n" + "\n".join(violations)


@pytest.mark.unit
def test_application_does_not_import_concrete_adapters() -> None:
    application_root = PROJECT_ROOT / "app" / "application"
    violations: list[str] = []
    for path in sorted(application_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module_names: list[str] = []
            if isinstance(node, ast.Import):
                module_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_names.append(node.module)
            if any(
                name == "app.adapters" or name.startswith("app.adapters.") for name in module_names
            ):
                violations.append(str(path.relative_to(PROJECT_ROOT)))

    assert not violations, "Application imports concrete adapters: " + ", ".join(violations)


@pytest.mark.unit
def test_application_does_not_import_infrastructure_frameworks() -> None:
    application_root = PROJECT_ROOT / "app" / "application"
    violations: list[str] = []
    for path in sorted(application_root.rglob("*.py")):
        forbidden = imported_roots(path) & APPLICATION_FORBIDDEN_TECHNOLOGIES
        if forbidden:
            relative_path = path.relative_to(PROJECT_ROOT)
            violations.append(f"{relative_path}: {', '.join(sorted(forbidden))}")

    assert not violations, "Infrastructure imports found:\n" + "\n".join(violations)


@pytest.mark.unit
def test_http_interface_does_not_import_persistence_entities() -> None:
    interface_root = PROJECT_ROOT / "app" / "interface" / "http"
    forbidden_prefixes = (
        "app.adapters.persistence",
        "sqlalchemy",
    )
    violations: list[str] = []
    for path in sorted(interface_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            if any(name.startswith(forbidden_prefixes) for name in names):
                violations.append(str(path.relative_to(PROJECT_ROOT)))

    assert not violations, "HTTP interface imports persistence types: " + ", ".join(violations)


@pytest.mark.unit
def test_policy_retrieval_router_contains_no_scoring_implementation() -> None:
    path = PROJECT_ROOT / "app" / "interface" / "http" / "routers" / "policy_retrieval.py"
    source = path.read_text(encoding="utf-8")
    forbidden = ("cosine_distance", "inverse_document_frequency", "rrf_k", "fusion_score =")
    assert not [token for token in forbidden if token in source]


@pytest.mark.unit
def test_private_embedding_service_has_no_core_database_dependency() -> None:
    path = PROJECT_ROOT / "infra" / "embedding" / "server.py"
    roots = imported_roots(path)
    assert not roots & {"sqlalchemy", "psycopg", "pgvector"}
    source = path.read_text(encoding="utf-8").lower()
    assert "database_url" not in source


@pytest.mark.unit
def test_private_reranker_service_has_no_core_database_dependency() -> None:
    path = PROJECT_ROOT / "infra" / "reranker" / "server.py"
    roots = imported_roots(path)
    assert not roots & {"sqlalchemy", "psycopg", "pgvector"}
    source = path.read_text(encoding="utf-8").lower()
    assert "database_url" not in source
    assert "tenant_id" not in source


@pytest.mark.unit
def test_local_llm_runtime_has_no_core_database_dependency() -> None:
    root = PROJECT_ROOT / "infra" / "local_llm"
    if not root.exists():
        return
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        roots = imported_roots(path)
        forbidden = roots & {"sqlalchemy", "psycopg", "pgvector"}
        source = path.read_text(encoding="utf-8").lower()
        if forbidden or "database_url" in source:
            violations.append(str(path.relative_to(PROJECT_ROOT)))
    assert not violations, "Local LLM runtime imports Core DB dependencies: " + ", ".join(
        violations
    )


@pytest.mark.unit
def test_application_does_not_construct_qwen_reranker_adapter() -> None:
    path = PROJECT_ROOT / "app" / "application" / "policy_retrieval.py"
    source = path.read_text(encoding="utf-8")
    assert "RemoteQwenRerankerAdapter" not in source
    assert "Qwen/Qwen3-Reranker" not in source
