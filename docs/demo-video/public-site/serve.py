"""Loopback-only, range-aware server for the public CSight demo video."""

from __future__ import annotations

import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VIDEO = ROOT / "final_v2_highres.mp4"
INDEX = ROOT / "index.html"
PORT = 8098
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)\Z")


class VideoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._serve(send_body=True)

    def do_HEAD(self) -> None:
        self._serve(send_body=False)

    def _serve(self, *, send_body: bool) -> None:
        path = self.path.split("?", 1)[0]
        if path in {"/", "/login", "/login/"}:
            asset, content_type = INDEX, "text/html; charset=utf-8"
        elif path == "/video.mp4":
            asset, content_type = VIDEO, "video/mp4"
        else:
            self.send_error(404)
            return

        size = asset.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get("Range") if asset == VIDEO else None
        if range_header:
            match = RANGE_RE.fullmatch(range_header)
            if match is None or not any(match.groups()):
                self._range_unsatisfiable(size)
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                length = int(last)
                if length == 0:
                    self._range_unsatisfiable(size)
                    return
                start = max(size - length, 0)
            if start >= size or end < start:
                self._range_unsatisfiable(size)
                return

        partial = range_header is not None
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if asset == INDEX:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'unsafe-inline'; "
                "media-src 'self'; object-src 'none'",
            )
        else:
            self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        if send_body:
            with asset.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = source.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    def _range_unsatisfiable(self, size: int) -> None:
        self.send_response(416)
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Content-Length", "0")
        self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), VideoHandler).serve_forever()
