"""Legacy evaluation is Dev-only, append-only, and explicit about ranking semantics."""

import json
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import evaluate_local_mlx as mlx
from scripts import evaluate_policy_query_builder as query
from scripts.evaluation_reporting import (
    private_observation_summary,
    unmeasured_metrics,
    write_json_new,
)


def _row() -> dict[str, Any]:
    return {
        "record_id": "SYNTHETIC-CASE-1",
        "strategy": "RAW",
        "split": "dev",
        "success": True,
        "relevant": ["RULE", "EXCEPTION"],
        "hard_negative": [],
        "hits": ["RULE"],
        "latency_ms": 1.0,
        "query_hashes": [],
    }


@pytest.mark.parametrize("module", [query, mlx])
def test_wrappers_separate_clause_recall_from_hit_rate(module: Any) -> None:
    scorer = module._metrics if module is query else module._retrieval_metrics
    metrics = scorer([_row()])
    assert metrics["recall_at_10"] == 0.5
    assert metrics["hit_rate_at_10"] == 1.0
    assert metrics["exact_gold_coverage_at_3"] == 0.0
    assert metrics["metrics_schema_version"] == "retrieval_ranking_metrics/1.0.0"
    assert metrics["release_eligible"] is False


@pytest.mark.parametrize("module", [query, mlx])
def test_unmeasured_retrieval_safety_is_not_reported_as_zero(module: Any) -> None:
    scorer = module._metrics if module is query else module._retrieval_metrics
    metrics = scorer([_row()])
    for name in (
        "cross_tenant_retrieval_rate",
        "wrong_version_retrieval_rate",
        "future_policy_retrieval_rate",
        "retired_policy_retrieval_rate",
    ):
        assert metrics[name] is None
        assert metrics["unmeasured_checks"][name] == "NOT_RUN"
    if module is query:
        assert metrics["determinism_rate"] is None
        assert metrics["unmeasured_checks"]["determinism_rate"] == "NOT_RUN"


def test_unmeasured_check_keeps_json_null_and_explicit_status() -> None:
    report = json.loads(json.dumps(unmeasured_metrics("citation_allowlist_violation_rate")))
    assert report == {
        "citation_allowlist_violation_rate": None,
        "unmeasured_checks": {"citation_allowlist_violation_rate": "NOT_RUN"},
    }


@pytest.mark.parametrize("module", [query, mlx])
@pytest.mark.parametrize("invalid", ["empty_gold", "duplicate_hits", "duplicate_gold"])
def test_wrappers_reject_invalid_ranking_inputs(module: Any, invalid: str) -> None:
    row = _row()
    if invalid == "empty_gold":
        row["relevant"] = []
    elif invalid == "duplicate_gold":
        row["relevant"] = ["RULE", "RULE"]
    else:
        row["hits"] = ["RULE", "RULE", "RULE"]
    scorer = module._metrics if module is query else module._retrieval_metrics
    with pytest.raises(ValueError):
        scorer([row])


@pytest.mark.parametrize("module", [query, mlx])
def test_wrappers_keep_failed_case_in_macro_denominator(module: Any) -> None:
    failed = {**_row(), "record_id": "SYNTHETIC-FAILED", "success": False, "hits": []}
    scorer = module._metrics if module is query else module._retrieval_metrics
    metrics = scorer([_row(), failed])
    assert metrics["recall_at_10"] == 0.25
    assert metrics["hit_rate_at_10"] == 0.5


def test_query_cli_default_never_evaluates_test_and_writes_private_new_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str]] = []

    def evaluate(strategy: str, split: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        calls.append((strategy, split))
        metrics = query._metrics([_row()])  # pyright: ignore[reportPrivateUsage]
        return metrics, [{**_row(), "raw_query": "PRIVATE_MARKER"}]

    output = tmp_path / "new-run"
    monkeypatch.setattr(query, "evaluate", evaluate)
    monkeypatch.setattr(sys, "argv", ["evaluate", "--output-dir", str(output)])
    assert query.main() == 0
    assert calls == [("RAW", "dev"), ("DETERMINISTIC", "dev")]
    payload = json.loads((output / "result.json").read_text())
    assert payload["split"] == "dev"
    assert payload["release_eligible"] is False
    assert payload["profile_frozen"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "result.json").stat().st_mode) == 0o600
    combined = (output / "result.json").read_text() + capsys.readouterr().out
    assert "PRIVATE_MARKER" not in combined
    assert "SYNTHETIC-CASE-1" not in combined
    assert not (output / "query_builder_profile_v1.json").exists()


@pytest.mark.parametrize("module", [query, mlx])
def test_legacy_cli_refuses_test_before_provider_or_data_access(
    module: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Test refusal must precede settings/provider/data access")

    monkeypatch.setattr(module, "Settings", forbidden)
    monkeypatch.setattr(
        sys, "argv", ["evaluate", "--split", "test", "--output-dir", str(tmp_path / "run")]
    )
    assert module.main() == 2
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("module", [query, mlx])
def test_legacy_cli_refuses_existing_output_before_provider_access(
    module: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = tmp_path / "result.json"
    original.write_bytes(b"HISTORICAL_RESULT")

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Output refusal must precede provider access")

    monkeypatch.setattr(module, "Settings", forbidden)
    if module is query:
        monkeypatch.setattr(module, "evaluate", forbidden)
    monkeypatch.setattr(sys, "argv", ["evaluate", "--output-dir", str(tmp_path)])
    assert module.main() == 2
    assert original.read_bytes() == b"HISTORICAL_RESULT"


@pytest.mark.parametrize("module", [query, mlx])
def test_legacy_cli_requires_explicit_new_output_directory(
    module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Missing output directory must precede settings/provider access")

    monkeypatch.setattr(module, "Settings", forbidden)
    monkeypatch.setattr(sys, "argv", ["evaluate"])
    assert module.main() == 2


def test_mlx_legacy_freeze_is_blocked_before_reading_historical_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Legacy profile freeze must not read historical metrics")

    monkeypatch.setattr(mlx, "Settings", forbidden)
    monkeypatch.setattr(sys, "argv", ["evaluate", "--freeze"])
    assert mlx.main() == 2


@pytest.mark.parametrize("module", [query, mlx])
def test_legacy_cli_refuses_symlink_output(
    module: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    link = tmp_path / "existing-link"
    destination = tmp_path / "private"
    destination.mkdir()
    link.symlink_to(destination, target_is_directory=True)
    monkeypatch.setattr(sys, "argv", ["evaluate", "--output-dir", str(link)])

    def forbidden(**_: object) -> None:
        pytest.fail("No provider access")

    monkeypatch.setattr(module, "Settings", forbidden)
    assert module.main() == 2
    assert list(destination.iterdir()) == []


def test_json_writer_never_overwrites_file_or_symlink(tmp_path: Path) -> None:
    original = tmp_path / "original.json"
    original.write_bytes(b"HISTORICAL")
    link = tmp_path / "linked.json"
    link.symlink_to(original)
    for destination in (original, link):
        with pytest.raises(FileExistsError):
            write_json_new(destination, {"replacement": True})
    assert original.read_bytes() == b"HISTORICAL"


def test_private_observations_do_not_copy_errors_quotes_or_model_output() -> None:
    row = {
        **_row(),
        "prediction": {"quote": "PRIVATE_QUOTE"},
        "error": "PRIVATE_ERROR",
        "url": "https://private.invalid/PRIVATE_PATH",
    }
    encoded = json.dumps(private_observation_summary([row]))
    for marker in ("PRIVATE_", "SYNTHETIC-CASE-1", "RULE", "EXCEPTION"):
        assert marker not in encoded


def test_query_provider_error_is_redacted_and_does_not_create_success_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*_: object) -> None:
        raise RuntimeError("PRIVATE_PROVIDER_ERROR")

    output = tmp_path / "failed-run"
    monkeypatch.setattr(query, "evaluate", fail)
    monkeypatch.setattr(sys, "argv", ["evaluate", "--output-dir", str(output)])
    assert query.main() == 2
    assert not (output / "result.json").exists()
    printed = capsys.readouterr()
    assert "PRIVATE_PROVIDER_ERROR" not in printed.out + printed.err
    assert json.loads(printed.out)["status"] == "FAIL"


def test_mlx_mock_dev_run_never_freezes_or_persists_predictions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "mlx-dev"
    settings = SimpleNamespace(
        llm_provider="mlx",
        llm_base_url_value="http://unused.invalid/v1",
        llm_model_revision="938d8919941c6e7efd3c7150eff7fe9d12afa631",
    )

    def fake_settings(**_: object) -> SimpleNamespace:
        return settings

    def fake_provider(_: object) -> object:
        return object()

    def fake_model_profile(_: object) -> dict[str, str]:
        return {"profile": "MOCK"}

    def fake_task_profile(_: str) -> tuple[object, Path]:
        return object(), tmp_path / "unused"

    def fake_prompt_profile(**kw: Any) -> dict[str, Any]:
        return {"frozen": kw["frozen"]}

    monkeypatch.setattr(mlx, "Settings", fake_settings)
    monkeypatch.setattr(mlx, "build_llm_provider", fake_provider)
    monkeypatch.setattr(mlx, "_model_profile", fake_model_profile)
    monkeypatch.setattr(mlx, "_profile_for_task", fake_task_profile)
    monkeypatch.setattr(mlx, "_prompt_profile", fake_prompt_profile)
    splits: list[str] = []

    def evaluate(*args: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        splits.append(args[-1])
        return {"record_count": 1}, [{**_row(), "prediction": "PRIVATE_PREDICTION"}]

    monkeypatch.setattr(mlx, "evaluate_extraction", evaluate)
    monkeypatch.setattr(
        sys, "argv", ["evaluate", "--task", "extraction", "--output-dir", str(output)]
    )
    assert mlx.main() == 0
    assert splits == ["dev"]
    result = json.loads((output / "extraction" / "result.json").read_text())
    assert result["release_eligible"] is False
    assert result["profile_frozen"] is False
    files = list(output.rglob("*.json"))
    encoded = "".join(path.read_text() for path in files) + capsys.readouterr().out
    assert "PRIVATE_PREDICTION" not in encoded
    assert "SYNTHETIC-CASE-1" not in encoded
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in files)


@pytest.mark.parametrize("target", ["evaluate-query-builder", "evaluate-local-llm-all"])
def test_make_requires_explicit_new_run_path_before_any_recipe(target: str) -> None:
    root = Path(__file__).resolve().parents[2]
    missing = subprocess.run(
        ["make", "-n", target, "EVALUATION_OUTPUT_DIR="],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0
    assert "Set EVALUATION_OUTPUT_DIR" in missing.stderr
    explicit = subprocess.run(
        ["make", "-n", target, "EVALUATION_OUTPUT_DIR=local-data/new-dev-run"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert explicit.returncode == 0
    assert '--output-dir "local-data/new-dev-run"' in explicit.stdout
