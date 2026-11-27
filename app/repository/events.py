"""Bus de eventos en memoria para los eventos de dominio del catálogo.

Se mantiene en memoria, igual que la bandeja de notificaciones (HU-05):
los suscriptores pueden consultar los eventos emitidos y las pruebas pueden
verificar ``product.reviewed`` sin depender de un broker externo.
"""

from __future__ import annotations

import threading
from typing import Any, Mapping


from collections.abc import Callable


class InMemoryEventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._eventos: list[dict[str, Any]] = []
        self._subscriptores: dict[str, list[Callable[[dict[str, Any]], Any]]] = {}

    def subscribe(self, topic: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        with self._lock:
            self._subscriptores.setdefault(topic, []).append(handler)

    def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        with self._lock:
            evento = {"topic": topic, "payload": dict(payload)}
            self._eventos.append(evento)
            handlers = list(self._subscriptores.get(topic, ()))
        for handler in handlers:
            handler(dict(evento["payload"]))

    def events(self, topic: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if topic is None:
                return [dict(evento) for evento in self._eventos]
            return [
                dict(evento) for evento in self._eventos if evento["topic"] == topic
            ]

    def reset(self) -> None:
        with self._lock:
            self._eventos.clear()
