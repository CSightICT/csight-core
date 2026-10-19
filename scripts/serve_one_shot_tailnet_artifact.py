from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import shutil
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--bind-host", required=True)
    parser.add_argument("--allowed-client", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--expected-bytes", required=True, type=int)
    parser.add_argument("--expected-sha256", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source = args.source
    if (
        not source.is_absolute()
        or not source.is_file()
        or source.is_symlink()
        or source.stat().st_size != args.expected_bytes
        or not hmac.compare_digest(_sha256(source), args.expected_sha256)
    ):
        print(
            json.dumps(
                {"schema": "csight_tailnet_transfer/1.0.0", "status": "SOURCE_REJECTED"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )
        return 2

    route = f"/{args.token}/{source.name}"
    state = {"transferred": False}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *args: object) -> None:
            del args

        def do_GET(self) -> None:
            client_ip = self.client_address[0]
            if client_ip != args.allowed_client or not hmac.compare_digest(self.path, route):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(args.expected_bytes))
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                with source.open("rb") as artifact:
                    shutil.copyfileobj(artifact, self.wfile, length=8 * 1024 * 1024)
                state["transferred"] = True
            except (BrokenPipeError, ConnectionResetError):
                state["transferred"] = False

    server = HTTPServer((args.bind_host, 0), Handler)
    server.timeout = 900
    print(
        json.dumps(
            {
                "schema": "csight_tailnet_transfer/1.0.0",
                "status": "READY",
                "port": server.server_port,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        flush=True,
    )
    server.handle_request()
    server.server_close()
    status = "PASS" if state["transferred"] else "FAIL"
    print(
        json.dumps(
            {"schema": "csight_tailnet_transfer/1.0.0", "status": status},
            separators=(",", ":"),
            sort_keys=True,
        ),
        flush=True,
    )
    return 0 if state["transferred"] else 1


if __name__ == "__main__":
    sys.exit(main())
