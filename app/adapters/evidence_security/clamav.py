"""Bounded ClamAV INSTREAM malware-scanning adapter."""

from __future__ import annotations

import socket
import struct

from app.ports.evidence_security import MalwareDetectedError, MalwareScannerUnavailableError


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
        if timeout_seconds <= 0:
            raise ValueError("ClamAV timeout must be positive")
        if not 1 <= chunk_bytes <= 1024 * 1024:
            raise ValueError("ClamAV chunk size is invalid")
        self._host = host.strip()
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._chunk_bytes = chunk_bytes

    def scan(self, content: bytes) -> None:
        try:
            with socket.create_connection(
                (self._host, self._port),
                timeout=self._timeout_seconds,
            ) as connection:
                connection.settimeout(self._timeout_seconds)
                connection.sendall(b"zINSTREAM\0")
                for offset in range(0, len(content), self._chunk_bytes):
                    chunk = content[offset : offset + self._chunk_bytes]
                    connection.sendall(struct.pack("!I", len(chunk)))
                    connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                response = connection.recv(4096)
        except (OSError, TimeoutError) as error:
            raise MalwareScannerUnavailableError(
                "The malware scanner did not return a verdict."
            ) from error

        verdict = response.rstrip(b"\0\r\n")
        if verdict.endswith(b" OK"):
            return
        if b" FOUND" in verdict:
            raise MalwareDetectedError("The uploaded content was rejected by malware scanning.")
        raise MalwareScannerUnavailableError("The malware scanner returned an invalid verdict.")


__all__ = ["ClamAVInstreamScanner"]
