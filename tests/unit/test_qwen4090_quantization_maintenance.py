"""Fail-closed contract for the no-argument Khrin quantization launcher."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "infra/llm/run_qwen4090_quantization_maintenance.sh"
IMAGE_ID = "sha256:" + "d" * 64


def _write_private(path: Path, content: str, *, mode: int) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def _launcher_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    deployment_root = tmp_path / "deployed root"
    dependency_root = tmp_path / "dependency root"
    scripts_dir = deployment_root / "scripts"
    plan_dir = tmp_path / "plan files"
    evidence_dir = tmp_path / "evidence files"
    fake_bin = tmp_path / "fake bin"
    for directory in (
        deployment_root,
        dependency_root,
        dependency_root / "pydantic",
        dependency_root / "pydantic_core",
        scripts_dir,
        plan_dir,
        evidence_dir,
        fake_bin,
    ):
        directory.mkdir(mode=0o700)

    runner = scripts_dir / "run_qwen38_quantization_plan.py"
    plan = plan_dir / "final;plan $(not-expanded).json"
    evidence = evidence_dir / "final evidence;not-expanded.json"
    capture = tmp_path / "captured-argv.bin"
    _write_private(runner, "# deployed runner fixture\n", mode=0o600)
    _write_private(
        dependency_root / "pydantic" / "__init__.py",
        "# pydantic fixture\n",
        mode=0o600,
    )
    _write_private(
        dependency_root / "pydantic_core" / "__init__.py",
        "# pydantic-core fixture\n",
        mode=0o600,
    )
    _write_private(plan, "{}\n", mode=0o600)
    _write_private(
        fake_bin / "python3",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        '{ printf \'%s\\0\' "${PYTHONPATH}"; printf \'%s\\0\' "$@"; } >"${CAPTURE_PATH}"\n',
        mode=0o700,
    )

    environment = {
        "ALLOW_QWEN38_QUANTIZATION": "YES",
        "CAPTURE_PATH": str(capture),
        "CSIGHT_QWEN38_QUANTIZATION_DOCKER_IMAGE_ID": IMAGE_ID,
        "CSIGHT_QWEN38_QUANTIZATION_DEPENDENCY_ROOT": str(dependency_root),
        "CSIGHT_QWEN38_QUANTIZATION_EVIDENCE_OUTPUT": str(evidence),
        "CSIGHT_QWEN38_QUANTIZATION_PLAN": str(plan),
        "CSIGHT_QWEN38_QUANTIZATION_PYTHONPATH_ROOT": str(deployment_root),
        "CSIGHT_QWEN38_QUANTIZATION_RUNNER": str(runner),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
    }
    return environment, capture


def _run_wrapper(environment: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WRAPPER), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_quantization_maintenance_passes_exact_argv_without_interpolation(
    tmp_path: Path,
) -> None:
    environment, capture = _launcher_environment(tmp_path)

    result = _run_wrapper(environment)

    assert result.returncode == 0, result.stderr
    values = capture.read_bytes().split(b"\0")[:-1]
    assert [value.decode() for value in values] == [
        (
            environment["CSIGHT_QWEN38_QUANTIZATION_PYTHONPATH_ROOT"]
            + ":"
            + environment["CSIGHT_QWEN38_QUANTIZATION_DEPENDENCY_ROOT"]
        ),
        environment["CSIGHT_QWEN38_QUANTIZATION_RUNNER"],
        "--plan",
        environment["CSIGHT_QWEN38_QUANTIZATION_PLAN"],
        "--execute",
        "--evidence-output",
        environment["CSIGHT_QWEN38_QUANTIZATION_EVIDENCE_OUTPUT"],
        "--docker-image-id",
        IMAGE_ID,
    ]
    assert not (tmp_path / "not-expanded").exists()


@pytest.mark.parametrize(
    ("environment_key", "environment_value", "expected_error"),
    [
        (
            "ALLOW_QWEN38_QUANTIZATION",
            None,
            "ALLOW_QWEN38_QUANTIZATION=YES",
        ),
        (
            "CSIGHT_QWEN38_QUANTIZATION_DOCKER_IMAGE_ID",
            "llama-cpp:latest",
            "exact sha256 image ID",
        ),
    ],
)
def test_quantization_maintenance_fails_closed_before_python(
    tmp_path: Path,
    environment_key: str,
    environment_value: str | None,
    expected_error: str,
) -> None:
    environment, capture = _launcher_environment(tmp_path)
    if environment_value is None:
        environment.pop(environment_key)
    else:
        environment[environment_key] = environment_value

    result = _run_wrapper(environment)

    assert result.returncode == 2
    assert expected_error in result.stderr
    assert not capture.exists()


def test_quantization_maintenance_refuses_arguments(tmp_path: Path) -> None:
    environment, capture = _launcher_environment(tmp_path)

    result = _run_wrapper(environment, "--execute")

    assert result.returncode == 2
    assert "accepts no arguments" in result.stderr
    assert not capture.exists()


def test_quantization_maintenance_refuses_symlink_plan(tmp_path: Path) -> None:
    environment, capture = _launcher_environment(tmp_path)
    original = Path(environment["CSIGHT_QWEN38_QUANTIZATION_PLAN"])
    link = original.parent / "linked-plan.json"
    link.symlink_to(original)
    environment["CSIGHT_QWEN38_QUANTIZATION_PLAN"] = str(link)

    result = _run_wrapper(environment)

    assert result.returncode == 2
    assert "regular non-symlink file" in result.stderr
    assert not capture.exists()


def test_quantization_maintenance_refuses_group_writable_plan(tmp_path: Path) -> None:
    environment, capture = _launcher_environment(tmp_path)
    Path(environment["CSIGHT_QWEN38_QUANTIZATION_PLAN"]).chmod(0o660)

    result = _run_wrapper(environment)

    assert result.returncode == 2
    assert "must not be group- or world-writable" in result.stderr
    assert not capture.exists()


def test_quantization_maintenance_refuses_noncanonical_pythonpath_root(
    tmp_path: Path,
) -> None:
    environment, capture = _launcher_environment(tmp_path)
    deployment_root = environment["CSIGHT_QWEN38_QUANTIZATION_PYTHONPATH_ROOT"]
    environment["CSIGHT_QWEN38_QUANTIZATION_PYTHONPATH_ROOT"] = (
        f"{deployment_root}/../{Path(deployment_root).name}"
    )

    result = _run_wrapper(environment)

    assert result.returncode == 2
    assert "must be canonical" in result.stderr
    assert not capture.exists()


def test_quantization_maintenance_requires_pinned_dependency_root(tmp_path: Path) -> None:
    environment, capture = _launcher_environment(tmp_path)
    environment.pop("CSIGHT_QWEN38_QUANTIZATION_DEPENDENCY_ROOT")

    result = _run_wrapper(environment)

    assert result.returncode == 2
    assert "CSIGHT_QWEN38_QUANTIZATION_DEPENDENCY_ROOT" in result.stderr
    assert not capture.exists()


def test_quantization_maintenance_refuses_existing_evidence(tmp_path: Path) -> None:
    environment, capture = _launcher_environment(tmp_path)
    evidence = Path(environment["CSIGHT_QWEN38_QUANTIZATION_EVIDENCE_OUTPUT"])
    _write_private(evidence, "do not overwrite\n", mode=0o600)

    result = _run_wrapper(environment)

    assert result.returncode == 2
    assert "refusing to overwrite" in result.stderr
    assert not capture.exists()


def test_quantization_maintenance_requires_owner_only_evidence_parent(
    tmp_path: Path,
) -> None:
    environment, capture = _launcher_environment(tmp_path)
    Path(environment["CSIGHT_QWEN38_QUANTIZATION_EVIDENCE_OUTPUT"]).parent.chmod(0o750)

    result = _run_wrapper(environment)

    assert result.returncode == 2
    assert "owner-only mode 700" in result.stderr
    assert not capture.exists()


def test_quantization_maintenance_rejects_an_unpinned_runner(tmp_path: Path) -> None:
    environment, capture = _launcher_environment(tmp_path)
    deployment_root = Path(environment["CSIGHT_QWEN38_QUANTIZATION_PYTHONPATH_ROOT"])
    alternate_runner = deployment_root / "scripts" / "alternate.py"
    _write_private(alternate_runner, "# alternate fixture\n", mode=0o600)
    environment["CSIGHT_QWEN38_QUANTIZATION_RUNNER"] = str(alternate_runner)

    result = _run_wrapper(environment)

    assert result.returncode == 2
    assert "deployed run_qwen38_quantization_plan.py" in result.stderr
    assert not capture.exists()


def test_quantization_maintenance_script_has_static_shell_guards() -> None:
    subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
    source = WRAPPER.read_text(encoding="utf-8")

    assert '[[ "$#" -eq 0 ]]' in source
    assert "ALLOW_QWEN38_QUANTIZATION" in source
    assert "readonly -a command=(" in source
    assert '"${command[@]}"' in source
    assert "eval " not in source
    assert "bash -c" not in source
    assert "sh -c" not in source
