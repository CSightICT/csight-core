"""Static safety contracts for the macOS CSight server controller."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / "scripts" / "csight_server_control.sh"
APP_SOURCE = ROOT / "scripts" / "csight_server_control.applescript"
EMBEDDING_RUNNER = ROOT / "scripts" / "csight_embedding_runtime.sh"


def test_server_controller_stop_preserves_named_volumes() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")

    assert 'compose_command "${docker_bin}" stop' in source
    assert " down" not in source
    assert "volume rm" not in source
    assert "--volumes" not in source
    assert CONTROLLER.stat().st_mode & 0o100


def test_server_controller_has_health_gated_start_and_safe_rebuild() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")

    assert "up --detach --wait --remove-orphans" in source
    assert "run --rm migrator" in source
    assert "API_READY_URL" in source
    assert "WEB_READY_URL" in source
    assert "EMBEDDING_READY_URL" in source
    assert "EMBEDDING_MODELS_URL" in source
    assert "PUBLIC_READY_URL" in source
    assert "start_embedding_if_needed" in source
    assert "ensure_public_tunnel" in source
    assert "정책 검색 엔진: 정상" in source
    assert 'case "${1:-status}" in' in source


def test_server_controller_manages_embedding_without_forcing_unknown_processes() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")

    assert "embedding_screen_session_exists" in source
    assert 'screen -dmS "${EMBEDDING_SCREEN_SESSION}"' in source
    assert 'screen -S "${EMBEDDING_SCREEN_SESSION}" -X quit' in source
    assert "legacy_managed_embedding_pid" in source
    assert '[[ "${command_line}" == *"infra.embedding.server:app"* ]]' in source
    assert 'kill -TERM "${pid}"' in source
    assert "kill -KILL" not in source
    assert "이 앱이 시작한 프로세스가 아니어서 종료하지 않았습니다" in source
    assert 'compose_command "${docker_bin}" stop' in source
    assert 'launchctl bootout "${USER_GUI_DOMAIN}/${TUNNEL_LAUNCH_LABEL}"' in source


def test_embedding_runtime_is_an_executable_bounded_uvicorn_entrypoint() -> None:
    source = EMBEDDING_RUNNER.read_text(encoding="utf-8")

    assert EMBEDDING_RUNNER.stat().st_mode & 0o100
    assert "infra.embedding.server:app" in source
    assert "--host 127.0.0.1" in source
    assert "--no-access-log" in source
    assert 'print -- "$$" > "${EMBEDDING_PID_FILE}"' in source


def test_macos_app_exposes_only_the_bounded_controller_actions() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")

    for label in (
        "서버 켜기 (빠른 시작)",
        "코드 반영 후 켜기",
        "서버 상태 확인",
        "상담원 화면 열기",
        "서버 끄기",
    ):
        assert label in source
    for action in ("start", "rebuild", "status", "open", "stop"):
        assert f'set actionName to "{action}"' in source
