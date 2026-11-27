"""Estado auxiliar de HU-20: emisores de la bandeja de comunidad.

La bandeja y las entregas siguen viviendo en ``notification_repository``
(HU-05). Aquí solo se guarda el emisor público que la estructura de HU-20
exhibe junto a cada notificación, sin tocar el modelo compartido.
"""

from __future__ import annotations

import threading


class CommunityNotificationStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._emisores: dict[str, str] = {}

    def registrar_emisor(self, notificacion_id: str, emisor: str) -> None:
        with self._lock:
            self._emisores[notificacion_id] = emisor

    def emisor_de(self, notificacion_id: str) -> str:
        with self._lock:
            return self._emisores.get(notificacion_id, "")

    def reset(self) -> None:
        with self._lock:
            self._emisores.clear()


community_notification_store = CommunityNotificationStore()
