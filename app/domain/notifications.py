"""Dominio de notificaciones y preferencias (HU-05, SUB-06).

AUT-10 fija los canales y tipos aceptados; AUT-11 la retención de la bandeja.
Se mantienen fuera del catálogo entero de HU-06 porque no son parámetros
numéricos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from app.domain.auth import DomainError

AUT_10 = "AUT-10"
AUT_11 = "AUT-11"
RETENCION_DIAS = 30
MAX_REINTENTOS = 3


class NotificationChannel(StrEnum):
    EMAIL = "email"
    IN_APP = "in_app"
    PUSH = "push"


class NotificationType(StrEnum):
    CUENTA_VERIFICADA = "cuenta_verificada"
    PERFIL_ACTUALIZADO = "perfil_actualizado"
    PRODUCTO_PUBLICADO = "producto_publicado"
    NUEVO_SEGUIDOR = "nuevo_seguidor"
    NUEVA_RESENA = "nueva_resena"
    PASSWORD_RESET = "password_reset"
    CUENTA_BLOQUEADA = "cuenta_bloqueada"
    ROL_ASIGNADO = "rol_asignado"
    LOGIN_SOSPECHOSO = "login_sospechoso"
    # HU-12: reportes y sanciones se comunican con lenguaje claro y motivo.
    REPORTE_RECIBIDO = "reporte_recibido"
    REPORTE_RESUELTO = "reporte_resuelto"
    SANCION_APLICADA = "sancion_aplicada"


CANALES_PERMITIDOS: tuple[NotificationChannel, ...] = tuple(NotificationChannel)
TIPOS_PERMITIDOS: tuple[NotificationType, ...] = tuple(NotificationType)

# Seguridad: estos tipos no se silencian aunque el usuario desactive canales.
TIPOS_CRITICOS: frozenset[NotificationType] = frozenset(
    {
        NotificationType.PASSWORD_RESET,
        NotificationType.CUENTA_BLOQUEADA,
        NotificationType.ROL_ASIGNADO,
        NotificationType.LOGIN_SOSPECHOSO,
    }
)
CANALES_CRITICOS: tuple[NotificationChannel, ...] = (
    NotificationChannel.EMAIL,
    NotificationChannel.IN_APP,
)

CANALES_DEFAULT: tuple[NotificationChannel, ...] = (
    NotificationChannel.IN_APP,
    NotificationChannel.EMAIL,
)
TIPOS_DEFAULT: tuple[NotificationType, ...] = TIPOS_PERMITIDOS

MENSAJES_BASE: dict[NotificationType, str] = {
    NotificationType.CUENTA_VERIFICADA: "Tu cuenta fue verificada.",
    NotificationType.PERFIL_ACTUALIZADO: "Tu perfil fue actualizado.",
    NotificationType.PRODUCTO_PUBLICADO: "Tu producto fue publicado.",
    NotificationType.NUEVO_SEGUIDOR: "Tienes un nuevo seguidor.",
    NotificationType.NUEVA_RESENA: "Recibiste una nueva reseña.",
    NotificationType.PASSWORD_RESET: "Tu contraseña fue restablecida.",
    NotificationType.CUENTA_BLOQUEADA: "Tu cuenta fue bloqueada temporalmente.",
    NotificationType.ROL_ASIGNADO: "Se actualizó el rol de tu cuenta.",
    NotificationType.LOGIN_SOSPECHOSO: "Detectamos un acceso inusual a tu cuenta.",
    NotificationType.REPORTE_RECIBIDO: "Recibimos tu reporte y lo enviamos a revisión.",
    NotificationType.REPORTE_RESUELTO: "Tu reporte fue resuelto.",
    NotificationType.SANCION_APLICADA: "Se aplicó una sanción a tu cuenta o contenido.",
}


class InvalidNotificationChannelError(DomainError):
    status_code = 400
    codigo = "canal_no_permitido"


class InvalidNotificationTypeError(DomainError):
    status_code = 400
    codigo = "tipo_no_permitido"


class NotificationNotFoundError(DomainError):
    status_code = 404
    codigo = "notificacion_no_encontrada"


class NotificationDeliveryError(DomainError):
    status_code = 502
    codigo = "envio_notificacion_fallido"


def normalizar_canal(valor: str | NotificationChannel) -> NotificationChannel:
    candidato = str(valor).strip().lower() if not isinstance(valor, NotificationChannel) else valor
    try:
        canal = NotificationChannel(candidato)
    except ValueError as exc:
        raise InvalidNotificationChannelError(
            f"El canal '{valor}' no está permitido por {AUT_10}.",
            {
                "codigo": "canal_no_permitido",
                "canalesPermitidos": [c.value for c in CANALES_PERMITIDOS],
            },
        ) from exc
    return canal


def normalizar_tipo(valor: str | NotificationType) -> NotificationType:
    candidato = str(valor).strip().lower() if not isinstance(valor, NotificationType) else valor
    try:
        tipo = NotificationType(candidato)
    except ValueError as exc:
        raise InvalidNotificationTypeError(
            f"El tipo '{valor}' no está permitido por {AUT_10}.",
            {
                "codigo": "tipo_no_permitido",
                "tiposPermitidos": [t.value for t in TIPOS_PERMITIDOS],
            },
        ) from exc
    return tipo


def es_critico(tipo: NotificationType) -> bool:
    return tipo in TIPOS_CRITICOS


@dataclass(frozen=True)
class NotificationTemplate:
    """Plantilla versionada por tipo y canal (notas técnicas de HU-05)."""

    tipo: NotificationType
    canal: NotificationChannel
    version: int = 1

    def renderizar(
        self, contexto: Mapping[str, Any] | None = None
    ) -> tuple[str, int]:
        base = MENSAJES_BASE[self.tipo]
        seguro = {
            clave: str(valor)
            for clave, valor in (contexto or {}).items()
            if clave in {"nombre", "detalle"}
        }
        mensaje = base.format(**seguro) if seguro else base
        # Las decisiones (HU-11/HU-12) explican el motivo en el texto.
        detalle = seguro.get("detalle", "").strip()
        if detalle:
            mensaje = f"{mensaje} {detalle}"
        if self.canal is NotificationChannel.EMAIL:
            nombre = seguro.get("nombre", "")
            prefijo = f"Hola {nombre}: " if nombre else ""
            mensaje = f"{prefijo}{mensaje} — Digiverso"
        return mensaje, self.version


def plantilla_para(
    tipo: NotificationType, canal: NotificationChannel
) -> NotificationTemplate:
    return NotificationTemplate(tipo=tipo, canal=canal)


@dataclass
class NotificationPreferences:
    cuenta_id: str
    canales: tuple[NotificationChannel, ...]
    tipos: tuple[NotificationType, ...]
    actualizado_en: datetime


@dataclass
class Notification:
    id: str
    cuenta_id: str
    tipo: NotificationType
    mensaje: str
    canal: NotificationChannel
    creado_en: datetime
    leida: bool = False
    leida_en: datetime | None = None

    def marcar_leida(self, ahora: datetime) -> None:
        if not self.leida:
            self.leida = True
            self.leida_en = ahora


@dataclass
class NotificationDelivery:
    id: str
    notificacion_id: str
    canal: NotificationChannel
    estado: str
    intentos: int
    registrado_en: datetime
    detalle: str = ""
