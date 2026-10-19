"""Offline tests only: Docker, SSH and inference are never invoked."""

from pathlib import Path
from typing import Any

import pytest

from scripts import csight_gx10_desktop_remote as control

pytestmark = pytest.mark.unit


def host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control.socket, "gethostname", lambda: "gx10-ade1")
    monkeypatch.setattr(control.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(control.os, "getuid", lambda: 1000)
    monkeypatch.setattr(control, "read_key", lambda: "x" * 48)
    monkeypatch.setattr(control, "available_memory", lambda: 60 * control.GIB)


def test_low_memory_refuses_before_hash_or_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control, "available_memory", lambda: 39 * control.GIB)
    with pytest.raises(control.Blocked, match="INSUFFICIENT_SYSTEM_HEADROOM"):
        control.preflight()


def test_wrong_host_never_reads_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control.socket, "gethostname", lambda: "different-host")
    with pytest.raises(control.Blocked, match="WRONG_HOST"):
        control.execute("start")


def test_private_env_and_symlink_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / "runtime.env"
    env.write_text("LLM_API_KEY=" + "x" * 48)
    env.chmod(0o644)
    monkeypatch.setattr(control, "ENV", env)
    with pytest.raises(control.Blocked, match="PRIVATE_RUNTIME_ENV_REQUIRED"):
        control.read_key()
    env.chmod(0o600)
    assert control.read_key() == "x" * 48
    link = tmp_path / "link"
    link.symlink_to(env)
    monkeypatch.setattr(control, "ENV", link)
    with pytest.raises(control.Blocked, match="PRIVATE_RUNTIME_ENV_REQUIRED"):
        control.read_key()


def test_create_is_pinned_private_and_key_is_not_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, Any] = {}

    def fake_run(args: list[str], *, env: dict[str, str] | None = None) -> str:
        observed.update(args=args, env=env)
        return "owned-id"

    monkeypatch.setattr(control, "run", fake_run)
    key = "private-api-key-not-a-password" * 2
    assert control.create(key) == "owned-id"
    args = observed["args"]
    assert key not in " ".join(args)
    assert observed["env"]["LLAMA_API_KEY"] == key
    assert "127.0.0.1:18003:8080" in args
    assert control.IMAGE in args and args[args.index("--pull") + 1] == "never"
    assert args[args.index("--memory") + 1] == "32g"
    assert "--no-webui" in args and "--log-disable" in args
    assert args[args.index("--reasoning") + 1] == "off"
    assert "--privileged" not in args and "--network=host" not in args


def test_status_does_not_start_or_infer(monkeypatch: pytest.MonkeyPatch) -> None:
    host(monkeypatch)
    monkeypatch.setattr(control, "inspect_container", lambda: None)
    result = control.execute("status")
    assert result["status"] == "FAIL" and result["running"] is False
    assert "synthetic_canary" not in result


def test_start_canary_failure_stops_only_new_owned_id(monkeypatch: pytest.MonkeyPatch) -> None:
    host(monkeypatch)
    stopped: list[list[str]] = []

    def create(_key: str) -> str:
        return "new-owned-id"

    def record(args: list[str]) -> str:
        stopped.append(args)
        return ""

    monkeypatch.setattr(control, "inspect_container", lambda: None)
    monkeypatch.setattr(control, "preflight", lambda: None)
    monkeypatch.setattr(control, "create", create)
    monkeypatch.setattr(control, "run", record)
    monkeypatch.setattr(control, "ready", ready)
    monkeypatch.setattr(control, "request", wrong_response)
    with pytest.raises(control.Blocked, match="CANARY_MISMATCH"):
        control.execute("start")
    assert stopped == [
        ["docker", "start", "new-owned-id"],
        ["docker", "stop", "--time", "20", "new-owned-id"],
    ]


def ready(_key: str) -> bool:
    return True


def wrong_response(*_args: Any) -> dict[str, Any]:
    return {"model": "wrong-model"}


def valid(*_args: Any) -> None:
    pass


def test_existing_running_container_is_not_stopped_on_canary_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host(monkeypatch)
    monkeypatch.setattr(
        control, "inspect_container", lambda: {"Id": "existing-id", "State": {"Running": True}}
    )
    monkeypatch.setattr(control, "validate_container", valid)
    monkeypatch.setattr(control, "ready", ready)
    monkeypatch.setattr(control, "request", wrong_response)
    with pytest.raises(control.Blocked, match="CANARY_MISMATCH"):
        control.execute("start")


def test_stop_requires_exact_identity_before_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    host(monkeypatch)
    foreign: dict[str, Any] = {
        "Config": {"Labels": {}},
        "HostConfig": {},
        "Mounts": [],
        "Image": "foreign",
    }
    monkeypatch.setattr(
        control,
        "inspect_container",
        lambda: foreign,
    )
    with pytest.raises(control.Blocked, match="CONTAINER_IDENTITY_MISMATCH"):
        control.execute("stop")


def test_app_has_bounded_notifications_and_auto_closing_result() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "scripts/csight_server_control.applescript").read_text()
    assert "with timeout of 3600 seconds" in source
    assert "with timeout of 3 seconds" in source
    assert source.count("giving up after 60") == 2
    assert source.count("\n        activate\n") == 2
    wrapper = (root / "scripts/csight_gx10_desktop.sh").read_text()
    assert "StrictHostKeyChecking=yes" in wrapper and "BatchMode=yes" in wrapper
    assert "PasswordAuthentication=no" in wrapper
