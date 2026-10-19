"""Network-free framing, deadline, and fail-closed scanner regression tests."""

from __future__ import annotations

import struct
from collections.abc import Sequence
from types import TracebackType
from typing import Self

import pytest

from app.adapters.evidence_security import clamav
from app.ports.evidence_security import MalwareDetectedError, MalwareScannerUnavailableError

pytestmark = pytest.mark.unit


class _Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


class _Socket:
    def __init__(self, responses: Sequence[bytes | OSError]) -> None:
        self.responses = list(responses)
        self.sent: list[bytes] = []
        self.timeouts: list[float] = []
        self.recv_sizes: list[int] = []
        self.received_bytes = 0
        self.closed = False
        self.clock = _Clock()
        self.send_seconds = 0.0
        self.recv_seconds = 0.0
        self.connect_seconds = 0.0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del error_type, error, traceback
        self.closed = True

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)

    def sendall(self, content: bytes) -> None:
        self.clock.now += self.send_seconds
        self.sent.append(content)

    def recv(self, size: int) -> bytes:
        self.clock.now += self.recv_seconds
        self.recv_sizes.append(size)
        response = self.responses.pop(0) if self.responses else b""
        if isinstance(response, OSError):
            raise response
        if len(response) > size:
            self.responses.insert(0, response[size:])
        self.received_bytes += len(response[:size])
        return response[:size]


def _scanner(monkeypatch: pytest.MonkeyPatch, connection: _Socket) -> clamav.ClamAVInstreamScanner:
    def create_connection(address: tuple[str, int], *, timeout: float) -> _Socket:
        assert address == ("synthetic.invalid", 3310)
        assert timeout > 0
        connection.clock.now += connection.connect_seconds
        return connection

    monkeypatch.setattr(clamav.socket, "create_connection", create_connection)
    monkeypatch.setattr(clamav, "monotonic", connection.clock)
    return clamav.ClamAVInstreamScanner(
        host="synthetic.invalid", timeout_seconds=1.0, chunk_bytes=2
    )


@pytest.mark.parametrize(
    "responses",
    [[b"stream: OK\0"], [b"stream: O", b"K", b"\0"], [bytes([b]) for b in b"stream: OK\0"]],
)
def test_clean_reply_requires_complete_frame_and_eof(
    monkeypatch: pytest.MonkeyPatch, responses: list[bytes]
) -> None:
    connection = _Socket(list(responses))

    _scanner(monkeypatch, connection).scan(b"abc")

    assert connection.closed
    assert not connection.responses
    assert len(connection.recv_sizes) >= 2  # one or more chunks and peer EOF
    assert connection.sent == [
        b"zINSTREAM\0",
        struct.pack("!I", 2),
        b"ab",
        struct.pack("!I", 1),
        b"c",
        struct.pack("!I", 0),
    ]


@pytest.mark.parametrize(
    "responses",
    [
        [b"stream: Synthetic-Signature FOUND\0"],
        [b"stream: Synthetic-Signature F", b"OUND\0"],
    ],
)
def test_found_reply_is_rejected_without_exposing_signature(
    monkeypatch: pytest.MonkeyPatch, responses: list[bytes]
) -> None:
    connection = _Socket(list(responses))
    with pytest.raises(MalwareDetectedError) as failure:
        _scanner(monkeypatch, connection).scan(b"synthetic")
    assert "Synthetic-Signature" not in str(failure.value)
    assert connection.closed


@pytest.mark.parametrize(
    "responses",
    [
        [],
        [b"stream: OK"],
        [b"stream: OK\n"],
        [b"garbage OK\0"],
        [b" OK\0"],
        [b"stream: FAILED ERROR OK\0"],
        [b"stream: Synthetic FOUND OK\0"],
        [b"stream: Synthetic ERROR\0"],
        [b"INSTREAM size limit exceeded. ERROR\0"],
        [b"\0"],
        [b"stream: OK\0extra"],
        [b"stream: OK\0", b"stream: Synthetic FOUND\0"],
        [b"stream: OK\0\0"],
        [b"stream: \nFOUND\0"],
        [b"stream:  FOUND\0"],
        [b"stream: OK\0", TimeoutError("SYNTHETIC_PRIVATE_FAILURE")],
        [OSError("SYNTHETIC_PRIVATE_FAILURE")],
    ],
)
def test_invalid_truncated_or_conflicting_reply_fails_closed(
    monkeypatch: pytest.MonkeyPatch, responses: list[bytes | OSError]
) -> None:
    connection = _Socket(responses)
    with pytest.raises(MalwareScannerUnavailableError) as failure:
        _scanner(monkeypatch, connection).scan(b"synthetic")
    assert "SYNTHETIC_PRIVATE_FAILURE" not in str(failure.value)
    assert connection.closed


def test_verdict_limit_is_enforced_across_fragments(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Socket([b"s" * 4096, b"stream: OK\0"])
    with pytest.raises(MalwareScannerUnavailableError):
        _scanner(monkeypatch, connection).scan(b"synthetic")
    assert connection.received_bytes == 4097
    assert connection.recv_sizes[-1] == 1
    assert connection.closed


@pytest.mark.parametrize("phase", ["connect", "send", "receive", "eof"])
def test_one_deadline_bounds_upload_reply_and_eof(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    responses = [b"stream: O", b"K\0"] if phase == "receive" else [b"stream: OK\0"]
    connection = _Socket(responses)
    if phase == "connect":
        connection.connect_seconds = 1.1
    elif phase == "send":
        connection.send_seconds = 0.3
    else:
        connection.recv_seconds = 0.6
    with pytest.raises(MalwareScannerUnavailableError):
        _scanner(monkeypatch, connection).scan(b"abc")
    assert connection.closed
    assert all(0 < value <= 1.0 for value in connection.timeouts)
    assert connection.timeouts == sorted(connection.timeouts, reverse=True)
    if phase == "connect":
        assert connection.sent == []


def test_maximum_sized_found_reply_is_bounded_and_recognized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = b"stream: " + b"S" * (4096 - len(b"stream:  FOUND\0")) + b" FOUND\0"
    connection = _Socket([response])
    with pytest.raises(MalwareDetectedError):
        _scanner(monkeypatch, connection).scan(b"synthetic")
    assert connection.received_bytes == 4096
    assert connection.recv_sizes[-1] == 1
    assert connection.closed


def test_connect_failure_has_only_safe_public_error(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Socket([])
    scanner = _scanner(monkeypatch, connection)

    def unavailable(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("SYNTHETIC_PRIVATE_FAILURE")

    monkeypatch.setattr(clamav.socket, "create_connection", unavailable)
    with pytest.raises(MalwareScannerUnavailableError) as failure:
        scanner.scan(b"synthetic")
    assert "SYNTHETIC_PRIVATE_FAILURE" not in str(failure.value)
    assert failure.value.__suppress_context__


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("inf"), float("-inf"), float("nan")])
def test_scanner_rejects_unbounded_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        clamav.ClamAVInstreamScanner(host="synthetic.invalid", timeout_seconds=timeout)
