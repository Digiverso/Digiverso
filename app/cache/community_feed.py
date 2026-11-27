"""Caché en memoria del feed y las recomendaciones de la comunidad (HU-19)."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any, Protocol


class CommunityFeedCache(Protocol):
    def get_feed(self, usuario_id: str, firma: tuple[object, ...]) -> list[dict[str, Any]] | None: ...

    def set_feed(
        self, usuario_id: str, firma: tuple[object, ...], items: list[dict[str, Any]]
    ) -> None: ...

    def get_recommendations(
        self, usuario_id: str, firma: tuple[object, ...]
    ) -> list[dict[str, Any]] | None: ...

    def set_recommendations(
        self, usuario_id: str, firma: tuple[object, ...], items: list[dict[str, Any]]
    ) -> None: ...

    def invalidate(self, usuario_id: str | None = None) -> None: ...


class InMemoryCommunityFeedCache:
    """Fan-out lectura: entrada materializada por usuario y tipo de respuesta.

    La ``firma`` incluye los seguidos/intereses y el estado de los productos, de
    modo que una publicación nueva se refleja sin necesidad de acoplar HU-19 al
    servicio de catálogo. Seguir, dejar de seguir y cambiar intereses invalidan
    explícitamente las entradas del usuario.
    """

    def __init__(self) -> None:
        self._feeds: dict[str, tuple[tuple[object, ...], list[dict[str, Any]]]] = {}
        self._recomendaciones: dict[
            str, tuple[tuple[object, ...], list[dict[str, Any]]]
        ] = {}
        self._lock = Lock()

    @staticmethod
    def _value(
        entries: dict[str, tuple[tuple[object, ...], list[dict[str, Any]]]],
        usuario_id: str,
        firma: tuple[object, ...],
    ) -> list[dict[str, Any]] | None:
        entrada = entries.get(usuario_id)
        if entrada is None or entrada[0] != firma:
            return None
        return deepcopy(entrada[1])

    @staticmethod
    def _store(
        entries: dict[str, tuple[tuple[object, ...], list[dict[str, Any]]]],
        usuario_id: str,
        firma: tuple[object, ...],
        items: list[dict[str, Any]],
    ) -> None:
        entries[usuario_id] = (firma, deepcopy(items))

    def get_feed(
        self, usuario_id: str, firma: tuple[object, ...]
    ) -> list[dict[str, Any]] | None:
        with self._lock:
            return self._value(self._feeds, usuario_id, firma)

    def set_feed(
        self, usuario_id: str, firma: tuple[object, ...], items: list[dict[str, Any]]
    ) -> None:
        with self._lock:
            self._store(self._feeds, usuario_id, firma, items)

    def get_recommendations(
        self, usuario_id: str, firma: tuple[object, ...]
    ) -> list[dict[str, Any]] | None:
        with self._lock:
            return self._value(self._recomendaciones, usuario_id, firma)

    def set_recommendations(
        self, usuario_id: str, firma: tuple[object, ...], items: list[dict[str, Any]]
    ) -> None:
        with self._lock:
            self._store(self._recomendaciones, usuario_id, firma, items)

    def invalidate(self, usuario_id: str | None = None) -> None:
        with self._lock:
            if usuario_id is None:
                self._feeds.clear()
                self._recomendaciones.clear()
            else:
                self._feeds.pop(usuario_id, None)
                self._recomendaciones.pop(usuario_id, None)
