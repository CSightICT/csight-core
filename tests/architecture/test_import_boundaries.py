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
    "multipart",
    "openai",
    "pwdlib",
    "sqlalchemy",
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
