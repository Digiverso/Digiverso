"""Caché en memoria de la vitrina agrupada por categoría (HU-10)."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any, Protocol


class ShowcaseCache(Protocol):
    def get(self, categoria_id: str) -> list[dict[str, Any]] | None: ...

    def set(self, categoria_id: str, productos: list[dict[str, Any]]) -> None: ...

    def invalidate(self, categoria_id: str | None = None) -> None: ...


class InMemoryShowcaseCache:
    """Entrada por categoría; se invalida en cada escritura del catálogo."""

    def __init__(self) -> None:
        self._por_categoria: dict[str, list[dict[str, Any]]] = {}
        self._lock = Lock()

    def get(self, categoria_id: str) -> list[dict[str, Any]] | None:
        with self._lock:
            productos = self._por_categoria.get(categoria_id)
            return deepcopy(productos) if productos is not None else None

    def set(self, categoria_id: str, productos: list[dict[str, Any]]) -> None:
        with self._lock:
            self._por_categoria[categoria_id] = deepcopy(productos)

    def invalidate(self, categoria_id: str | None = None) -> None:
        with self._lock:
            if categoria_id is None:
                self._por_categoria.clear()
            else:
                self._por_categoria.pop(categoria_id, None)
