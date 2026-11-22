"""Caché en memoria del árbol de categorías activas."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any, Protocol


class CategoryTreeCache(Protocol):
    def get(self) -> list[dict[str, Any]] | None: ...

    def set(self, tree: list[dict[str, Any]]) -> None: ...

    def invalidate(self) -> None: ...


class InMemoryCategoryTreeCache:
    """Caché simple; se invalida en cada escritura del servicio."""

    def __init__(self) -> None:
        self._tree: list[dict[str, Any]] | None = None
        self._lock = Lock()

    def get(self) -> list[dict[str, Any]] | None:
        with self._lock:
            return deepcopy(self._tree)

    def set(self, tree: list[dict[str, Any]]) -> None:
        with self._lock:
            self._tree = deepcopy(tree)

    def invalidate(self) -> None:
        with self._lock:
            self._tree = None
