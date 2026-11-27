"""Caché de parámetros de comunidad con invalidación por versión (HU-21)."""

from __future__ import annotations

from threading import Lock
from typing import Protocol

from app.domain.community_parameters import CommunityParameterSnapshot


class CommunityParametersCache(Protocol):
    def get(self, version: int) -> CommunityParameterSnapshot | None: ...

    def set(self, snapshot: CommunityParameterSnapshot) -> None: ...

    def invalidate(self) -> None: ...


class InMemoryCommunityParametersCache:
    """Guarda una instantánea y solo la sirve si coincide con la versión vigente."""

    def __init__(self) -> None:
        self._snapshot: CommunityParameterSnapshot | None = None
        self._lock = Lock()

    def get(self, version: int) -> CommunityParameterSnapshot | None:
        with self._lock:
            if self._snapshot is None or self._snapshot.version != version:
                return None
            return self._snapshot

    def set(self, snapshot: CommunityParameterSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None
