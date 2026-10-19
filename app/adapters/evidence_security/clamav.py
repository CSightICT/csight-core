"""Bounded ClamAV INSTREAM malware-scanning adapter."""

from __future__ import annotations

import socket
import struct
from math import isfinite
from time import monotonic

from app.ports.evidence_security import MalwareDetectedError, MalwareScannerUnavailableError

_MAX_REPLY_BYTES = 4096


class ClamAVInstreamScanner:
    """Send bytes to clamd without persisting a temporary copy on disk."""

    def __init__(
        self,
        *,
        host: str,
        port: int = 3310,
        timeout_seconds: float = 10.0,
        chunk_bytes: int = 64 * 1024,
    ) -> None:
        if not host.strip():
            raise ValueError("ClamAV host must not be blank")
        if not 1 <= port <= 65535:
            raise ValueError("ClamAV port is invalid")
        if not isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("ClamAV timeout must be finite and positive")
        if not 1 <= chunk_bytes <= 1024 * 1024:
            raise ValueError("ClamAV chunk size is invalid")
        self._host = host.strip()
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._chunk_bytes = chunk_bytes

    def scan(self, content: bytes) -> None:
        deadline = monotonic() + self._timeout_seconds
        try:
            with socket.create_connection(
                (self._host, self._port),
                timeout=_remaining_seconds(deadline),
            ) as connection:
                _send(connection, b"zINSTREAM\0", deadline=deadline)
                for offset in range(0, len(content), self._chunk_bytes):
                    chunk = content[offset : offset + self._chunk_bytes]
                    _send(connection, struct.pack("!I", len(chunk)), deadline=deadline)
                    _send(connection, chunk, deadline=deadline)
                _send(connection, struct.pack("!I", 0), deadline=deadline)
                response = _read_reply(connection, deadline=deadline)
        except OSError:
            raise MalwareScannerUnavailableError(
                "The malware scanner did not return a verdict."
            ) from None

        if response == b"stream: OK\0":
            return
        if response.startswith(b"stream: ") and response.endswith(b" FOUND\0"):
            signature = response[len(b"stream: ") : -len(b" FOUND\0")]
            if signature.strip() and all(32 <= byte <= 126 for byte in signature):
                raise MalwareDetectedError("The uploaded content was rejected by malware scanning.")
        raise MalwareScannerUnavailableError("The malware scanner returned an invalid verdict.")


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("The malware-scanning deadline elapsed.")
    return remaining


def _send(connection: socket.socket, content: bytes, *, deadline: float) -> None:
    connection.settimeout(_remaining_seconds(deadline))
    connection.sendall(content)
    _remaining_seconds(deadline)


def _read_reply(connection: socket.socket, *, deadline: float) -> bytes:
    """Read one bounded NUL record and peer EOF for a non-session INSTREAM command."""
    response = bytearray()
    while True:
        connection.settimeout(_remaining_seconds(deadline))
        chunk = connection.recv(_MAX_REPLY_BYTES + 1 - len(response))
        _remaining_seconds(deadline)
        if not chunk:
            return bytes(response)
        response.extend(chunk)
        if len(response) > _MAX_REPLY_BYTES or (
            b"\0" in response and response.index(0) != len(response) - 1
        ):
            raise MalwareScannerUnavailableError("The malware scanner returned an invalid verdict.")


__all__ = ["ClamAVInstreamScanner"]
