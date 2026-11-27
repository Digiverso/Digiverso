"""Consumidor de eventos de comunidad (HU-20, FUN-63 / PRC-63).

Se invoca después de que el productor haya hecho commit del evento. Reutiliza
la bandeja, los canales AUT-10, la retención AUT-11 y la cola de entregas de
HU-05; por eso no duplica la infraestructura de notificaciones.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from app.core.config import Settings
from app.domain.auth import Account
from app.domain.community_notifications import (
    EVENTOS_COMUNIDAD,
    PLANTILLA_VERSION_ACTUAL,
    CommunityInteraction,
    TIPOS_COMUNIDAD,
    comu11_activo,
    parsear_evento,
    renderizar_mensaje,
)
from app.domain.notifications import (
    CANALES_DEFAULT,
    CANALES_PERMITIDOS,
    Notification,
    NotificationChannel,
    NotificationNotFoundError,
    NotificationType,
    TIPOS_DEFAULT,
)
from app.repository.community_notifications import CommunityNotificationStore
from app.repository.email_repository import EmailDelivery, NotificationSender
from app.repository.notifications import NotificationRepository


@dataclass(frozen=True)
class CommunityNotificationData:
    """Estructura pública de HU-20: id, tipo, emisor, mensaje, leida y fecha."""

    id: str
    tipo: str
    emisor: str
    mensaje: str
    leida: bool
    fecha: datetime

    @classmethod
    def from_notification(
        cls, notification: Notification, emisor: str
    ) -> CommunityNotificationData:
        return cls(
            id=notification.id,
            tipo=notification.tipo.value,
            emisor=emisor,
            mensaje=notification.mensaje,
            leida=notification.leida,
            fecha=notification.creado_en,
        )


class CommunityNotificationConsumer:
    """Consume ``user.followed`` y ``review.created`` y entrega notificaciones."""

    def __init__(
        self,
        *,
        repo: NotificationRepository,
        settings: Settings,
        store: CommunityNotificationStore,
        clock: Callable[[], datetime] | None = None,
        sender: NotificationSender | None = None,
        account_provider: Callable[[str], Any] | None = None,
        product_author_provider: Callable[[str], str | None] | None = None,
        comu11_enabled: bool | None = None,
        plantilla_version: int = PLANTILLA_VERSION_ACTUAL,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sender = sender
        self.account_provider = account_provider
        self.product_author_provider = product_author_provider
        # ``None`` significa "leer COMU-11 del entorno/settings"; ``False``
        # permite a las pruebas simular la preferencia desactivada.
        self.comu11_enabled = (
            comu11_activo(settings) if comu11_enabled is None else comu11_enabled
        )
        self.plantilla_version = plantilla_version

    # ------------------------------------------------------------ PRC-63
    def procesar_evento(
        self, topic: str, payload: Mapping[str, Any]
    ) -> CommunityNotificationData | None:
        """Genera (una sola vez) la notificación de una interacción."""

        if not self.comu11_enabled:
            return None

        interaccion = parsear_evento(
            topic,
            payload,
            account_provider=self.account_provider,
            product_author_provider=self.product_author_provider,
        )
        if interaccion is None:
            return None

        preferencias = self.repo.obtener_preferencias(interaccion.destinatario_id)
        tipos = preferencias.tipos if preferencias else TIPOS_DEFAULT
        canales = preferencias.canales if preferencias else CANALES_DEFAULT

        # AUT-10 y COMU-11 se consultan antes de cualquier entrega.
        if interaccion.tipo not in tipos:
            return None
        canales_destino = tuple(
            canal for canal in canales if canal in CANALES_PERMITIDOS
        ) or (NotificationChannel.IN_APP,)

        existente = self.repo.obtener_por_clave(interaccion.clave_idempotencia)
        if existente is not None:
            self._asegurar_emisor(existente, interaccion)
            return self._datos(existente)

        canal_bandeja = (
            NotificationChannel.IN_APP
            if NotificationChannel.IN_APP in canales_destino
            else canales_destino[0]
        )
        mensaje = renderizar_mensaje(
            interaccion.topic,
            interaccion.emisor,
            interaccion.detalle,
            self.plantilla_version,
        )
        notificacion = self.repo.crear_notificacion(
            cuenta_id=interaccion.destinatario_id,
            tipo=interaccion.tipo,
            mensaje=mensaje,
            canal=canal_bandeja,
            creado_en=self.clock(),
            clave_idempotencia=interaccion.clave_idempotencia,
        )
        self.store.registrar_emisor(notificacion.id, interaccion.emisor)

        cuenta = self._cuenta(interaccion.destinatario_id)
        nombre = str(getattr(cuenta, "nombre", "") or "") if cuenta else ""
        correo = str(getattr(cuenta, "correo", "") or "") if cuenta else ""
        for canal in canales_destino:
            texto = renderizar_mensaje(
                interaccion.topic,
                interaccion.emisor,
                interaccion.detalle,
                self.plantilla_version,
            )
            if canal is NotificationChannel.EMAIL:
                texto = f"Hola {nombre}: {texto} — Digiverso" if nombre else texto
            self._entregar(
                notificacion=notificacion,
                canal=canal,
                mensaje=texto,
                tipo=interaccion.tipo,
                correo=correo,
                nombre=nombre,
            )
        return self._datos(notificacion)

    def consumir_lote(
        self, eventos: list[dict[str, Any]]
    ) -> list[CommunityNotificationData]:
        """Consume eventos ya publicados en el bus (topic + payload)."""

        generadas: list[CommunityNotificationData] = []
        for evento in eventos:
            topic = str(evento.get("topic", ""))
            payload = evento.get("payload", {})
            if topic not in EVENTOS_COMUNIDAD or not isinstance(payload, Mapping):
                continue
            resultado = self.procesar_evento(topic, payload)
            if resultado is not None:
                generadas.append(resultado)
        return generadas

    # ------------------------------------------------------------ bandeja
    def bandeja(
        self, cuenta: Account, *, pagina: int = 1, tamano: int = 20
    ) -> tuple[list[CommunityNotificationData], int]:
        ahora = self.clock()
        self.repo.limpiar_expiradas(ahora, self.settings.notification_retention_days)
        items, _ = self.repo.listar(
            cuenta.id, ahora=ahora, limite=10000, offset=0
        )
        tipos = set(TIPOS_COMUNIDAD.values())
        propios = [item for item in items if item.tipo in tipos]
        inicio = (pagina - 1) * tamano
        return (
            [
                self._datos(item)
                for item in propios[inicio : inicio + tamano]
            ],
            len(propios),
        )

    def marcar_leida(
        self, cuenta: Account, notificacion_id: str
    ) -> CommunityNotificationData:
        notificacion = self.repo.obtener_por_id(notificacion_id)
        if (
            notificacion is None
            or notificacion.cuenta_id != cuenta.id
            or notificacion.tipo not in TIPOS_COMUNIDAD.values()
        ):
            raise NotificationNotFoundError(
                "No existe la notificación de comunidad solicitada.",
                {"codigo": "notificacion_no_encontrada"},
            )
        actualizada = self.repo.marcar_leida(notificacion_id, self.clock())
        if actualizada is None:
            raise NotificationNotFoundError(
                "No existe la notificación de comunidad solicitada.",
                {"codigo": "notificacion_no_encontrada"},
            )
        return self._datos(actualizada)

    # ------------------------------------------------------------ helpers
    def _cuenta(self, cuenta_id: str) -> Any:
        if self.account_provider is None:
            return None
        return self.account_provider(cuenta_id)

    def _asegurar_emisor(
        self, notificacion: Notification, interaccion: CommunityInteraction
    ) -> None:
        if not self.store.emisor_de(notificacion.id):
            self.store.registrar_emisor(notificacion.id, interaccion.emisor)

    def _datos(self, notificacion: Notification) -> CommunityNotificationData:
        return CommunityNotificationData.from_notification(
            notificacion, self.store.emisor_de(notificacion.id)
        )

    def _entregar(
        self,
        *,
        notificacion: Notification,
        canal: NotificationChannel,
        mensaje: str,
        tipo: NotificationType,
        correo: str,
        nombre: str,
    ) -> EmailDelivery | None:
        if canal is not NotificationChannel.EMAIL:
            self.repo.registrar_entrega(
                notificacion_id=notificacion.id,
                canal=canal,
                estado="enviado",
                intentos=1,
                registrado_en=self.clock(),
            )
            return None

        if self.sender is None:
            self.repo.registrar_entrega(
                notificacion_id=notificacion.id,
                canal=canal,
                estado="enviado",
                intentos=1,
                registrado_en=self.clock(),
                detalle="sin-proveedor",
            )
            return None

        ultimo_error = ""
        for intento in range(1, self.settings.notification_max_retries + 1):
            try:
                entrega = self.sender.send(
                    correo=correo,
                    nombre=nombre,
                    asunto=f"Notificación de comunidad: {tipo.value}",
                    mensaje=mensaje,
                )
                self.repo.registrar_entrega(
                    notificacion_id=notificacion.id,
                    canal=canal,
                    estado="enviado",
                    intentos=intento,
                    registrado_en=self.clock(),
                )
                return entrega
            except Exception as exc:
                ultimo_error = str(exc)

        self.repo.registrar_entrega(
            notificacion_id=notificacion.id,
            canal=canal,
            estado="fallido",
            intentos=self.settings.notification_max_retries,
            registrado_en=self.clock(),
            detalle=ultimo_error,
        )
        return None


__all__ = ["CommunityNotificationConsumer", "CommunityNotificationData"]
