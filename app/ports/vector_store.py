"""Minimal vector search boundary for a later policy retrieval sprint."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class VectorMatch:
    document_id: str
    score: float
    content: str
    metadata: dict[str, str]


@runtime_checkable
class VectorStore(Protocol):
    def search(
        self,
        *,
        embedding: tuple[float, ...],
        limit: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[VectorMatch, ...]: ...
