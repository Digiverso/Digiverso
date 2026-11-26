"""Caché de parámetros con invalidación automática por número de versión."""

from __future__ import annotations

from threading import Lock
from typing import Protocol

from app.domain.auth_parameters import AuthParameterSnapshot


class AuthParametersCache(Protocol):
    def get(self, version: int) -> AuthParameterSnapshot | None: ...

    def set(self, snapshot: AuthParameterSnapshot) -> None: ...

    def invalidate(self) -> None: ...


class InMemoryAuthParametersCache:
    """Guarda una única instantánea y solo la sirve si coincide la versión."""

    def __init__(self) -> None:
        self._snapshot: AuthParameterSnapshot | None = None
        self._lock = Lock()

    def get(self, version: int) -> AuthParameterSnapshot | None:
        with self._lock:
            if self._snapshot is None or self._snapshot.version != version:
                return None
            return self._snapshot

    def set(self, snapshot: AuthParameterSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None
