"""Bus de eventos en memoria compartido por los módulos de comunidad."""

from __future__ import annotations

from threading import RLock
from typing import Any, Mapping


class InMemoryEventBus:
    """Bus mínimo con el contrato ``publish(topic, payload)``.

    HU-18 publica ``review.created`` y HU-20 (notificaciones al productor)
    puede consumirlo sin acoplarse al servicio de reseñas.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._eventos: list[dict[str, Any]] = []

    def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        with self._lock:
            self._eventos.append({"topic": topic, "payload": dict(payload)})

    def events(self, topic: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if topic is None:
                return [dict(evento) for evento in self._eventos]
            return [
                dict(evento)
                for evento in self._eventos
                if evento["topic"] == topic
            ]
