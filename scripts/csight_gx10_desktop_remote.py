"""Pinned, internal-only GX10 Q5 service. Run over SSH, never on the Mac.

No download, installation, Core routing, model fallback or foreign-job termination.
Output is a bounded operational summary, not model qualification evidence.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import platform
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

NAME = "csight-gx10-desktop-q5"
IMAGE = "sha256:b664e8d60f09f87d062319bdb94ca8e8cf04ceba69ed08a5f3b08fb8ba579ac4"
MODEL_SHA = "d709a46e48db256ac0bb3eee7fb2cdcfd087820eb4701b1af5dda84db41a2219"
MODEL_BYTES = 18_679_614_080
ALIAS = "csight-qwen3.8-27b-q5-k-s"
ROOT = Path("/home/aidi_lab/csight-gx10")
MODEL = ROOT / "models/sha256" / MODEL_SHA / "Qwen3.8-27B-CSight-Q5_K_S.gguf"
ENV = ROOT / "runtime/gx10-q5-bench-4k-c1-v2.env"
LABEL = "org.csight.desktop-contract"
VERSION = "q5-internal/1.0.1"
URL = "http://127.0.0.1:18003"
GIB = 1024**3
COMMAND = [
    "--model",
    "/models/model.gguf",
    "--alias",
    ALIAS,
    "--host",
    "0.0.0.0",
    "--port",
    "8080",
    "--ctx-size",
    "4096",
    "--parallel",
    "1",
    "--batch-size",
    "512",
    "--ubatch-size",
    "128",
    "--n-gpu-layers",
    "all",
    "--reasoning",
    "off",
    "--no-reasoning-preserve",
    "--flash-attn",
    "on",
    "--cache-type-k",
    "q8_0",
    "--cache-type-v",
    "q8_0",
    "--no-webui",
    "--log-disable",
]


class Blocked(RuntimeError):
    """Only fixed non-sensitive codes may cross this boundary."""


def run(args: list[str], *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
        env=env,
    )
    if result.returncode:
        raise Blocked("HOST_COMMAND_FAILED")
    return result.stdout


def available_memory() -> int:
    entries = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    return int(entries["MemAvailable"].split()[0]) * 1024


def read_key() -> str:
    metadata = ENV.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise Blocked("PRIVATE_RUNTIME_ENV_REQUIRED")
    values = dict(
        line.split("=", 1)
        for line in ENV.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    key = values.get("LLM_API_KEY", "")
    if len(key) < 32 or any(character.isspace() for character in key):
        raise Blocked("PRIVATE_API_KEY_INVALID")
    return key


def inspect_container() -> dict[str, Any] | None:
    ids = run(["docker", "ps", "-aq", "--filter", f"name=^/{NAME}$"]).split()
    if not ids:
        return None
    if len(ids) != 1:
        raise Blocked("AMBIGUOUS_CONTAINER")
    return json.loads(run(["docker", "inspect", ids[0]]))[0]


def validate_container(container: dict[str, Any], key: str) -> None:
    config, host = container["Config"], container["HostConfig"]
    mounts = container["Mounts"]
    valid = (
        container["Image"] == IMAGE
        and config.get("Labels", {}).get(LABEL) == VERSION
        and config["Cmd"] == COMMAND
        and config["Entrypoint"] == ["/app/llama-server"]
        and config["User"] == f"{os.getuid()}:{os.getgid()}"
        and f"LLAMA_API_KEY={key}" in config["Env"]
        and host["PortBindings"] == {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18003"}]}
        and host["NetworkMode"] == "bridge"
        and host["ReadonlyRootfs"] is True
        and host["Privileged"] is False
        and host["RestartPolicy"]["Name"] == "no"
        and host["Memory"] == 32 * GIB
        and len(mounts) == 1
        and mounts[0]["Source"] == str(MODEL)
        and mounts[0]["Destination"] == "/models/model.gguf"
        and mounts[0]["RW"] is False
    )
    if not valid:
        raise Blocked("CONTAINER_IDENTITY_MISMATCH")


def request(path: str, key: str, payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        URL + path,
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    # Ignore inherited proxy configuration; this service is loopback-only.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=30
    ) as response:
        body = response.read(262145)
    if len(body) > 262144:
        raise Blocked("RESPONSE_LIMIT")
    return json.loads(body)


def ready(key: str) -> bool:
    try:
        request("/health", key)
        models = request("/v1/models", key)
        return [item["id"] for item in models["data"]] == [ALIAS]
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return False


def preflight() -> None:
    if available_memory() < 40 * GIB:
        raise Blocked("INSUFFICIENT_SYSTEM_HEADROOM_NO_FOREIGN_JOBS_STOPPED")
    if MODEL.is_symlink() or MODEL.stat().st_size != MODEL_BYTES:
        raise Blocked("MODEL_SIZE_MISMATCH")
    with MODEL.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != MODEL_SHA:
            raise Blocked("MODEL_DIGEST_MISMATCH")
    if json.loads(run(["docker", "image", "inspect", IMAGE]))[0]["Id"] != IMAGE:
        raise Blocked("IMAGE_IDENTITY_MISMATCH")
    if available_memory() < 40 * GIB:
        raise Blocked("INSUFFICIENT_SYSTEM_HEADROOM_NO_FOREIGN_JOBS_STOPPED")


def create(key: str) -> str:
    # The key is inherited through the child environment, never argv or stdout.
    args = [
        "docker",
        "create",
        "--name",
        NAME,
        "--pull",
        "never",
        "--label",
        f"{LABEL}={VERSION}",
        "--label",
        "org.csight.primary-allowed=false",
        "--label",
        "org.csight.core-routing=false",
        "--restart",
        "no",
        "--network",
        "bridge",
        "--read-only",
        "--init",
        "--memory",
        "32g",
        "--memory-swap",
        "32g",
        "--pids-limit",
        "512",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--device",
        "nvidia.com/gpu=all",
        "--tmpfs",
        "/tmp:size=1g,mode=1777",
        "--mount",
        f"type=bind,source={MODEL},target=/models/model.gguf,readonly",
        "--publish",
        "127.0.0.1:18003:8080",
        "--env",
        "LLAMA_API_KEY",
        "--env",
        "HF_HUB_OFFLINE=1",
        "--env",
        "TRANSFORMERS_OFFLINE=1",
        "--log-opt",
        "max-size=5m",
        "--log-opt",
        "max-file=2",
        IMAGE,
        *COMMAND,
    ]
    return run(args, env={**os.environ, "LLAMA_API_KEY": key}).strip()


def execute(action: str) -> dict[str, Any]:
    if action not in {"start", "status", "stop"}:
        raise Blocked("INVALID_ACTION")
    if (
        socket.gethostname() != "gx10-ade1"
        or platform.machine() != "aarch64"
        or os.getuid() != 1000
    ):
        raise Blocked("WRONG_HOST_OR_OWNER")
    key = read_key()
    container = inspect_container()
    if container:
        validate_container(container, key)
    result: dict[str, Any] = {
        "schema": "csight_gx10_desktop/1.0.0",
        "phase": action,
        "status": "PASS",
        "model": ALIAS,
        "running": False,
        "ready": False,
        "core_routing": False,
        "primary_allowed": False,
        "foreign_jobs_stopped": 0,
        "memory_source": "PROC_MEMINFO_SYSTEM_AVAILABLE",
    }
    started_id = None
    try:
        if action == "stop":
            if container and container["State"]["Running"]:
                run(["docker", "stop", "--time", "20", container["Id"]])
            result["memory_available_bytes"] = available_memory()
            return result
        if action == "start":
            if not container or not container["State"]["Running"]:
                preflight()
                started_id = container["Id"] if container else create(key)
                run(["docker", "start", started_id])
            deadline = time.monotonic() + 240
            while not ready(key):
                if available_memory() < 16 * GIB:
                    raise Blocked("SYSTEM_HEADROOM_LOW")
                current = inspect_container()
                if not current or not current["State"]["Running"]:
                    raise Blocked("MODEL_START_EXITED")
                if time.monotonic() >= deadline:
                    raise Blocked("MODEL_READY_TIMEOUT")
                time.sleep(2)
            response = request(
                "/v1/chat/completions",
                key,
                {
                    "model": ALIAS,
                    "messages": [
                        {"role": "user", "content": 'Return exactly {"status":"ok"} as JSON.'}
                    ],
                    "temperature": 0,
                    "max_tokens": 32,
                    "response_format": {"type": "json_object"},
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )
            if response.get("model") != ALIAS or json.loads(
                response["choices"][0]["message"]["content"]
            ) != {"status": "ok"}:
                raise Blocked("CANARY_MISMATCH")
            if available_memory() < 16 * GIB:
                raise Blocked("SYSTEM_HEADROOM_LOW")
            result["synthetic_canary"] = "PASS"
        current = inspect_container()
        result["running"] = bool(current and current["State"]["Running"])
        result["ready"] = result["running"] and ready(key)
        result["status"] = "PASS" if result["ready"] else "FAIL"
        result["memory_available_bytes"] = available_memory()
        return result
    except BaseException:
        if started_id:
            run(["docker", "stop", "--time", "20", started_id])
        raise


def main() -> int:
    def interrupted(_signum: int, _frame: Any) -> None:
        raise Blocked("CONTROL_INTERRUPTED")

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        # Serialize this controller only. No broad process/container cleanup.
        lock_path = ROOT / "runtime/.desktop-q5.lock"
        with os.fdopen(
            os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "w"
        ) as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = execute(sys.argv[1] if len(sys.argv) == 2 else "status")
    except Blocked as error:
        result = {"status": "BLOCKED", "error": str(error), "foreign_jobs_stopped": 0}
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        result = {"status": "FAIL", "error": "GX10_CONTROL_FAILED", "foreign_jobs_stopped": 0}
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
