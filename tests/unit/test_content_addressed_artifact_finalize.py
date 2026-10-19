from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
FINALIZER = ROOT / "scripts/finalize_content_addressed_artifact.py"
TRANSFER = ROOT / "scripts/transfer_q5_khrin_to_gx10.sh"


def test_finalizer_prepares_and_atomically_finalizes(tmp_path: Path) -> None:
    root = tmp_path / "gx10"
    root.mkdir(mode=0o700)
    incoming = root / ".incoming" / "run"
    incoming.parent.mkdir(mode=0o700)
    final = root / "models" / "sha256" / "digest" / "artifact.gguf"
    partial = incoming / "artifact.gguf.partial"
    payload = b"synthetic-artifact"
    digest = hashlib.sha256(payload).hexdigest()
    common = [
        "--allowed-root",
        str(root),
        "--incoming",
        str(incoming),
        "--partial",
        str(partial),
        "--final",
        str(final),
        "--expected-bytes",
        str(len(payload)),
        "--expected-sha256",
        digest,
    ]

    subprocess.run(["python3", str(FINALIZER), "prepare", *common], check=True)
    partial.write_bytes(payload)
    subprocess.run(["python3", str(FINALIZER), "finalize", *common], check=True)

    assert final.read_bytes() == payload
    assert not incoming.exists()
    assert final.stat().st_mode & 0o777 == 0o600


def test_transfer_is_gated_and_never_routes_payload_through_mac() -> None:
    source = TRANSFER.read_text(encoding="utf-8")

    assert "ALLOW_GX10_MUTATION" in source
    assert "serve_one_shot_tailnet_artifact.py" in source
    assert "finalize_content_addressed_artifact.py" in source
    assert "receive_one_shot_artifact.sh" in source
    assert "Q5_TRANSFER_FAILED_PARTIAL_PRESERVED" in source
    assert "scp -3" not in source
    assert "rm " not in source
