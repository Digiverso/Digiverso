"""Caché de parámetros del catálogo con invalidación por número de versión."""

from __future__ import annotations

from threading import Lock
from typing import Protocol

from app.domain.catalog_parameters import CatalogParameterSnapshot


class CatalogParametersCache(Protocol):
    def get(self, version: int) -> CatalogParameterSnapshot | None: ...

    def set(self, snapshot: CatalogParameterSnapshot) -> None: ...

    def invalidate(self) -> None: ...


class InMemoryCatalogParametersCache:
    """Guarda una única instantánea y solo la sirve si coincide la versión."""

    def __init__(self) -> None:
        self._snapshot: CatalogParameterSnapshot | None = None
        self._lock = Lock()

    def get(self, version: int) -> CatalogParameterSnapshot | None:
        with self._lock:
            if self._snapshot is None or self._snapshot.version != version:
                return None
            return self._snapshot

    def set(self, snapshot: CatalogParameterSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None
