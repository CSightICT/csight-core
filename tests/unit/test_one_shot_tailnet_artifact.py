from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/serve_one_shot_tailnet_artifact.py"


def test_one_shot_server_binds_exact_source_client_token_and_digest() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "HTTPServer((args.bind_host, 0), Handler)" in source
    assert "client_ip != args.allowed_client" in source
    assert "hmac.compare_digest(self.path, route)" in source
    assert "source.is_symlink()" in source
    assert "source.stat().st_size != args.expected_bytes" in source
    assert "hmac.compare_digest(_sha256(source), args.expected_sha256)" in source
    assert "server.handle_request()" in source
    assert "server.timeout = 900" in source
    assert "Connection: close" not in source
    assert 'self.send_header("Connection", "close")' in source


def test_one_shot_server_module_loads_without_starting() -> None:
    spec = importlib.util.spec_from_file_location("one_shot_tailnet", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
