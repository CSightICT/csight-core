"""Standard-library bounded SHA-256 file hashing adapter."""

import hashlib
from typing import BinaryIO, Final

from app.ports.hashing import (
    EmptyHashInputError,
    FileDigest,
    HashingError,
    HashInputTooLargeError,
    UnreadableHashInputError,
)

_CHUNK_SIZE: Final = 64 * 1024


class BoundedSha256Hasher:
    def __init__(self, *, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._max_bytes = max_bytes

    def calculate(self, content: BinaryIO) -> FileDigest:
        self._rewind(content)
        digest = hashlib.sha256()
        total = 0
        try:
            while chunk := content.read(_CHUNK_SIZE):
                total += len(chunk)
                if total > self._max_bytes:
                    raise HashInputTooLargeError(
                        f"File exceeds the configured {self._max_bytes}-byte limit"
                    )
                digest.update(chunk)
        except HashingError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise UnreadableHashInputError("File could not be read") from exc
        finally:
            self._rewind(content)
        if total == 0:
            raise EmptyHashInputError("File is empty")
        return FileDigest(size_bytes=total, sha256=digest.hexdigest())

    @staticmethod
    def _rewind(content: BinaryIO) -> None:
        try:
            content.seek(0)
        except (OSError, ValueError) as exc:
            raise UnreadableHashInputError("File must be seekable") from exc
