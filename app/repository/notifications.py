"""Repositorio en memoria de preferencias, bandeja y entregas (HU-05)."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

from app.domain.notifications import (
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationPreferences,
    NotificationType,
)


class NotificationRepository:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reset()

    def _reset(self) -> None:
        self._preferencias: dict[str, NotificationPreferences] = {}
        self._notificaciones: dict[str, Notification] = {}
        self._entregas: dict[str, list[NotificationDelivery]] = {}
        self._idempotencia: dict[str, str] = {}
        self._next_notificacion = 100
        self._next_entrega = 1

    def reset(self) -> None:
        with self._lock:
            self._reset()

    # ------------------------------------------------------------ preferencias
    def guardar_preferencias(
        self,
        cuenta_id: str,
        *,
        canales: tuple[NotificationChannel, ...],
        tipos: tuple[NotificationType, ...],
        actualizado_en: datetime,
    ) -> NotificationPreferences:
        with self._lock:
            preferencias = NotificationPreferences(
                cuenta_id=cuenta_id,
                canales=canales,
                tipos=tipos,
                actualizado_en=actualizado_en,
            )
            self._preferencias[cuenta_id] = preferencias
            return preferencias

    def obtener_preferencias(self, cuenta_id: str) -> NotificationPreferences | None:
        with self._lock:
            return self._preferencias.get(cuenta_id)

    # ------------------------------------------------------------ bandeja
    def crear_notificacion(
        self,
        *,
        cuenta_id: str,
        tipo: NotificationType,
        mensaje: str,
        canal: NotificationChannel,
        creado_en: datetime,
        clave_idempotencia: str | None = None,
    ) -> Notification:
        with self._lock:
            if clave_idempotencia and clave_idempotencia in self._idempotencia:
                existente = self._idempotencia[clave_idempotencia]
                return self._notificaciones[existente]

            notificacion = Notification(
                id=f"ntf_{self._next_notificacion}",
                cuenta_id=cuenta_id,
                tipo=tipo,
                mensaje=mensaje,
                canal=canal,
                creado_en=creado_en,
            )
            self._notificaciones[notificacion.id] = notificacion
            self._entregas[notificacion.id] = []
            if clave_idempotencia:
                self._idempotencia[clave_idempotencia] = notificacion.id
            self._next_notificacion += 1
            return notificacion

    def obtener_por_id(self, notificacion_id: str) -> Notification | None:
        with self._lock:
            return self._notificaciones.get(notificacion_id)

    def obtener_por_clave(self, clave_idempotencia: str) -> Notification | None:
        with self._lock:
            notificacion_id = self._idempotencia.get(clave_idempotencia)
            return self._notificaciones.get(notificacion_id) if notificacion_id else None

    def listar(
        self,
        cuenta_id: str,
        *,
        ahora: datetime,
        limite: int,
        offset: int,
    ) -> tuple[list[Notification], int]:
        with self._lock:
            propias = [
                notificacion
                for notificacion in self._notificaciones.values()
                if notificacion.cuenta_id == cuenta_id
                and notificacion.creado_en <= ahora
            ]
            propias.sort(key=lambda n: (n.creado_en, n.id), reverse=True)
            return propias[offset : offset + limite], len(propias)

    def marcar_leida(
        self, notificacion_id: str, ahora: datetime
    ) -> Notification | None:
        with self._lock:
            notificacion = self._notificaciones.get(notificacion_id)
            if notificacion is None:
                return None
            notificacion.marcar_leida(ahora)
            return notificacion

    def limpiar_expiradas(self, ahora: datetime, dias: int) -> int:
        """Retención AUT-11: elimina notificaciones anteriores al corte."""

        corte = ahora - timedelta(days=dias)
        with self._lock:
            expiradas = [
                identificador
                for identificador, notificacion in self._notificaciones.items()
                if notificacion.creado_en < corte
            ]
            for identificador in expiradas:
                del self._notificaciones[identificador]
                self._entregas.pop(identificador, None)
            for clave, identificador in list(self._idempotencia.items()):
                if identificador in expiradas:
                    del self._idempotencia[clave]
            return len(expiradas)

    # ------------------------------------------------------------ entregas/cola
    def registrar_entrega(
        self,
        *,
        notificacion_id: str,
        canal: NotificationChannel,
        estado: str,
        intentos: int,
        registrado_en: datetime,
        detalle: str = "",
    ) -> NotificationDelivery:
        with self._lock:
            entrega = NotificationDelivery(
                id=f"ent_{self._next_entrega}",
                notificacion_id=notificacion_id,
                canal=canal,
                estado=estado,
                intentos=intentos,
                registrado_en=registrado_en,
                detalle=detalle,
            )
            self._entregas.setdefault(notificacion_id, []).append(entrega)
            self._next_entrega += 1
            return entrega

    def entregas_de(self, notificacion_id: str) -> tuple[NotificationDelivery, ...]:
        with self._lock:
            return tuple(self._entregas.get(notificacion_id, ()))


notification_repository = NotificationRepository()
