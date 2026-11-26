"""Servicio de notificaciones (HU-05, FUN-12/13/14/15)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol

from app.core.config import Settings
from app.domain.auth import Account
from app.domain.notifications import (
    CANALES_CRITICOS,
    CANALES_DEFAULT,
    CANALES_PERMITIDOS,
    TIPOS_CRITICOS,
    TIPOS_DEFAULT,
    InvalidNotificationChannelError,
    Notification,
    NotificationChannel,
    NotificationNotFoundError,
    NotificationPreferences,
    NotificationType,
    es_critico,
    normalizar_canal,
    normalizar_tipo,
    plantilla_para,
)
from app.repository.email_repository import EmailDelivery, NotificationSender
from app.repository.notifications import NotificationRepository


class NotificationPublisher(Protocol):
    """Contrato usado por otras HU para emitir eventos de cuenta."""

    def notificar_evento(
        self,
        *,
        cuenta_id: str,
        tipo: str | NotificationType,
        contexto: Mapping[str, Any] | None = None,
        clave_idempotencia: str | None = None,
        nombre: str = "",
        correo: str = "",
    ) -> Notification | None: ...


class NotificationService:
    def __init__(
        self,
        repo: NotificationRepository,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
        sender: NotificationSender | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sender = sender

    # ------------------------------------------------------------ PRC-13
    def preferencias_de(self, cuenta: Account) -> NotificationPreferences:
        guardadas = self.repo.obtener_preferencias(cuenta.id)
        if guardadas is not None:
            return guardadas
        return NotificationPreferences(
            cuenta_id=cuenta.id,
            canales=CANALES_DEFAULT,
            tipos=TIPOS_DEFAULT,
            actualizado_en=self.clock(),
        )

    def configurar_preferencias(
        self,
        cuenta: Account,
        *,
        canales: Iterable[str | NotificationChannel],
        tipos: Iterable[str | NotificationType],
        ip: str = "",
    ) -> NotificationPreferences:
        canales_normalizados = tuple(
            dict.fromkeys(normalizar_canal(canal) for canal in canales)
        )
        tipos_normalizados = tuple(
            dict.fromkeys(normalizar_tipo(tipo) for tipo in tipos)
        )
        if not canales_normalizados:
            raise InvalidNotificationChannelError(
                "Debe habilitar al menos un canal de notificación.",
                {"codigo": "canal_no_permitido"},
            )
        return self.repo.guardar_preferencias(
            cuenta.id,
            canales=canales_normalizados,
            tipos=tipos_normalizados,
            actualizado_en=self.clock(),
        )

    # ------------------------------------------------------------ PRC-12
    def notificar_evento(
        self,
        *,
        cuenta_id: str,
        tipo: str | NotificationType,
        contexto: Mapping[str, Any] | None = None,
        clave_idempotencia: str | None = None,
        nombre: str = "",
        correo: str = "",
    ) -> Notification | None:
        tipo_normalizado = normalizar_tipo(tipo)

        if clave_idempotencia:
            existente = self.repo.obtener_por_clave(clave_idempotencia)
            if existente is not None:
                return existente

        ahora = self.clock()
        preferencias = self.repo.obtener_preferencias(cuenta_id)
        canales = preferencias.canales if preferencias else CANALES_DEFAULT
        tipos = preferencias.tipos if preferencias else TIPOS_DEFAULT

        critico = es_critico(tipo_normalizado)
        if not critico and tipo_normalizado not in tipos:
            return None

        canales_destino = (
            CANALES_CRITICOS
            if critico
            else tuple(canal for canal in canales if canal in CANALES_PERMITIDOS)
        )
        if not canales_destino:
            canales_destino = (NotificationChannel.IN_APP,)

        canal_bandeja = (
            NotificationChannel.IN_APP
            if NotificationChannel.IN_APP in canales_destino
            else canales_destino[0]
        )
        mensaje_bandeja, _ = plantilla_para(
            tipo_normalizado, canal_bandeja
        ).renderizar(contexto)

        notificacion = self.repo.crear_notificacion(
            cuenta_id=cuenta_id,
            tipo=tipo_normalizado,
            mensaje=mensaje_bandeja,
            canal=canal_bandeja,
            creado_en=ahora,
            clave_idempotencia=clave_idempotencia,
        )

        for canal in canales_destino:
            mensaje, _ = plantilla_para(tipo_normalizado, canal).renderizar(contexto)
            self._entregar(
                notificacion=notificacion,
                canal=canal,
                mensaje=mensaje,
                tipo=tipo_normalizado,
                correo=correo,
                nombre=nombre,
            )
        return notificacion

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
                    asunto=f"Notificación de cuenta: {tipo.value}",
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

    # ------------------------------------------------------------ PRC-14
    def bandeja(
        self, cuenta: Account, *, pagina: int = 1, tamano: int = 20
    ) -> tuple[list[Notification], int]:
        ahora = self.clock()
        self.repo.limpiar_expiradas(ahora, self.settings.notification_retention_days)
        return self.repo.listar(
            cuenta.id,
            ahora=ahora,
            limite=tamano,
            offset=(pagina - 1) * tamano,
        )

    # ------------------------------------------------------------ PRC-15
    def marcar_leida(
        self, cuenta: Account, notificacion_id: str
    ) -> Notification:
        notificacion = self.repo.obtener_por_id(notificacion_id)
        # 404 para ajena y desconocida: no se revela la existencia de recursos.
        if notificacion is None or notificacion.cuenta_id != cuenta.id:
            raise NotificationNotFoundError(
                "No existe la notificación solicitada.",
                {"codigo": "notificacion_no_encontrada"},
            )
        actualizada = self.repo.marcar_leida(notificacion_id, self.clock())
        if actualizada is None:
            raise NotificationNotFoundError(
                "No existe la notificación solicitada.",
                {"codigo": "notificacion_no_encontrada"},
            )
        return actualizada
