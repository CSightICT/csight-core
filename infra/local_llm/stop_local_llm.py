"""Stop only the PID recorded by the CSight Local MLX foreground launcher."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

PID_FILE = Path(__file__).with_name(".server.pid")


def main() -> int:
    if not PID_FILE.exists():
        print("LOCAL_LLM_NOT_RUNNING")
        return 0
    raw_pid = PID_FILE.read_text(encoding="utf-8").strip()
    if not raw_pid.isdigit():
        raise SystemExit("Refusing to use an invalid Local LLM PID file")
    pid = int(raw_pid)
    result = subprocess.run(
        ("ps", "-p", str(pid), "-o", "command="),
        check=False,
        capture_output=True,
        text=True,
    )
    command = result.stdout.strip()
    if result.returncode != 0:
        PID_FILE.unlink(missing_ok=True)
        print("LOCAL_LLM_STALE_PID_REMOVED")
        return 0
    if "mlx_vlm.server" not in command:
        raise SystemExit("Refusing to stop a PID that is not an MLX-VLM server")
    os.kill(pid, signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    print(f"LOCAL_LLM_STOP_REQUESTED pid={pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
