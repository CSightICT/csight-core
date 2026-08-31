#!/usr/bin/env python3
"""PII-free local webhook receiver used only by the observability qualification stack."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import ClassVar


class AlertReceiver(BaseHTTPRequestHandler):
    """Acknowledge Alertmanager webhooks and expose bounded in-memory evidence."""

    events: ClassVar[list[dict[str, object]]] = []
    events_lock: ClassVar[Lock] = Lock()
    max_body_bytes: ClassVar[int] = 256 * 1024

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json_response(200, {"status": "ok"})
            return
        if self.path == "/events":
            with self.events_lock:
                events = tuple(self.events)
            self._json_response(200, {"events": events})
            return
        self._json_response(404, {"status": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/alerts":
            self._json_response(404, {"status": "not_found"})
            return
        length = self._content_length()
        if length is None or length > self.max_body_bytes:
            self._json_response(413, {"status": "rejected"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            event = self._sanitize(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            self._json_response(400, {"status": "invalid"})
            return
        with self.events_lock:
            self.events.append(event)
            del self.events[:-20]
        self._json_response(200, {"status": "acknowledged"})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _content_length(self) -> int | None:
        value = self.headers.get("Content-Length")
        try:
            parsed = int(value) if value is not None else None
        except ValueError:
            return None
        return parsed if parsed is not None and parsed >= 0 else None

    @staticmethod
    def _sanitize(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise TypeError("alert payload must be an object")
        status = payload.get("status")
        alerts = payload.get("alerts")
        if status not in {"firing", "resolved"} or not isinstance(alerts, list):
            raise ValueError("alert payload is missing bounded status")
        sanitized_alerts: list[dict[str, str]] = []
        for alert in alerts[:10]:
            if not isinstance(alert, dict):
                continue
            labels = alert.get("labels")
            if not isinstance(labels, dict):
                continue
            name = labels.get("alertname")
            severity = labels.get("severity")
            receiver_scope = labels.get("receiver_scope")
            if not all(isinstance(value, str) for value in (name, severity, receiver_scope)):
                continue
            sanitized_alerts.append(
                {
                    "alertname": name,
                    "severity": severity,
                    "receiver_scope": receiver_scope,
                }
            )
        return {"status": status, "alerts": sanitized_alerts}

    def _json_response(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8080), AlertReceiver)
    server.serve_forever()


if __name__ == "__main__":
    main()
