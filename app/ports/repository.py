"""Minimal persistence boundary; concrete ORM types stay in adapters."""

from typing import Protocol, TypeVar, runtime_checkable

EntityT = TypeVar("EntityT")
IdentifierT_contra = TypeVar("IdentifierT_contra", contravariant=True)


@runtime_checkable
class Repository(Protocol[EntityT, IdentifierT_contra]):
    def get(self, identifier: IdentifierT_contra) -> EntityT | None: ...

    def add(self, entity: EntityT) -> None: ...
