"""Reglas puras de las notificaciones de comunidad (HU-20, FUN-63).

Consume los eventos ``user.followed`` y ``review.created`` publicados por
HU-19 y HU-18. COMU-11 habilita o silencia estas interacciones; AUT-10 fija
los canales y los tipos de la bandeja (HU-05).

Este módulo no modifica el dominio compartido de notificaciones para no
solapar los cambios de otras historias de comunidad.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from app.domain.notifications import NotificationType

COMU_11 = "COMU-11"

EVENTO_USER_FOLLOWED = "user.followed"
EVENTO_REVIEW_CREATED = "review.created"
EVENTOS_COMUNIDAD: frozenset[str] = frozenset(
    {EVENTO_USER_FOLLOWED, EVENTO_REVIEW_CREATED}
)

TIPOS_COMUNIDAD: dict[str, NotificationType] = {
    EVENTO_USER_FOLLOWED: NotificationType.NUEVO_SEGUIDOR,
    EVENTO_REVIEW_CREATED: NotificationType.NUEVA_RESENA,
}

# Plantillas versionadas: el mensaje se construye solo con el nombre público
# del emisor y un detalle acotado (nunca con correos, identificadores ni el
# texto de una reseña).
PLANTILLA_VERSION_ACTUAL = 1
PLANTILLAS_VERSIONADAS: dict[tuple[str, int], str] = {
    (EVENTO_USER_FOLLOWED, 1): "{emisor} comenzó a seguirte.",
    (EVENTO_REVIEW_CREATED, 1): "{emisor} calificó tu producto con {detalle}.",
}
MAX_LONGITUD_EMISOR = 80
MAX_LONGITUD_DETALLE = 40
EMISOR_ANONIMO = "Un usuario"

_CORREO = re.compile(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_ETIQUETA = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class CommunityInteraction:
    """Evento de comunidad normalizado, listo para notificar."""

    topic: str
    actor_id: str
    destinatario_id: str
    tipo: NotificationType
    emisor: str
    detalle: str
    clave_idempotencia: str


def sanitizar_texto(valor: object, limite: int = MAX_LONGITUD_DETALLE) -> str:
    """Elimina markup, correos, URLs y caracteres de control antes de mostrar."""

    texto = html.unescape(str(valor if valor is not None else ""))
    texto = _ETIQUETA.sub(" ", texto)
    texto = _CORREO.sub(" ", texto)
    texto = _URL.sub(" ", texto)
    texto = _CONTROL.sub(" ", texto)
    return " ".join(texto.split())[:limite]


def emisor_publico(nombre: object) -> str:
    return sanitizar_texto(nombre, MAX_LONGITUD_EMISOR) or EMISOR_ANONIMO


def detalle_calificacion(valor: object) -> str:
    """Convierte la calificación en texto público y acotado."""

    try:
        numero = int(float(str(valor)))
    except (TypeError, ValueError):
        return ""
    if numero < 1:
        return ""
    return f"{numero} {'estrella' if numero == 1 else 'estrellas'}"


def clave_evento(payload: Mapping[str, Any]) -> str:
    """Identificador estable del evento, con hash si el productor no envía id."""

    for clave in ("id", "eventId", "event_id"):
        valor = payload.get(clave)
        if valor not in (None, ""):
            return sanitizar_texto(valor, 120) or "sin-id"
    canonico = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()[:16]


def clave_idempotencia(
    topic: str, payload: Mapping[str, Any], destinatario_id: str
) -> str:
    """Una clave por evento y usuario: permite reintentos sin duplicados."""

    return f"hu20:{topic}:{destinatario_id}:{clave_evento(payload)}"


def comu11_activo(settings: object | None = None) -> bool:
    """COMU-11: interruptores globales de notificaciones de comunidad."""

    valor: object = getattr(settings, "community_notifications_enabled", None)
    if valor is None:
        valor = os.getenv("COMU_11_ENABLED", "true")
    if isinstance(valor, str):
        return valor.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(valor)


def renderizar_mensaje(
    topic: str, emisor: str, detalle: str = "", version: int = PLANTILLA_VERSION_ACTUAL
) -> str:
    plantilla = PLANTILLAS_VERSIONADAS.get((topic, version))
    if plantilla is None:
        plantilla = PLANTILLAS_VERSIONADAS[(topic, PLANTILLA_VERSION_ACTUAL)]
    return plantilla.format(
        emisor=emisor_publico(emisor), detalle=sanitizar_texto(detalle)
    ).strip()


def _primer_valor(payload: Mapping[str, Any], claves: tuple[str, ...]) -> str:
    for clave in claves:
        valor = payload.get(clave)
        if valor not in (None, ""):
            return str(valor).strip()
    return ""


def parsear_evento(
    topic: str,
    payload: Mapping[str, Any],
    *,
    account_provider: Callable[[str], Any] | None = None,
    product_author_provider: Callable[[str], str | None] | None = None,
) -> CommunityInteraction | None:
    """Admite los esquemas publicados por HU-18 y HU-19.

    Devuelve ``None`` para eventos desconocidos, incompletos o propios
    (auto-notificación), de modo que el consumidor nunca moleste al emisor.
    """

    if topic not in EVENTOS_COMUNIDAD or not isinstance(payload, Mapping):
        return None

    if topic == EVENTO_USER_FOLLOWED:
        actor_id = _primer_valor(
            payload, ("seguidorId", "actorId", "userId", "seguidor_id", "actor_id")
        )
        destinatario_id = _primer_valor(
            payload,
            ("seguidoId", "destinatarioId", "receptorId", "usuarioId", "seguido_id"),
        )
        tipo = TIPOS_COMUNIDAD[EVENTO_USER_FOLLOWED]
        nombre = _primer_valor(
            payload, ("seguidorNombre", "actorNombre", "nombre", "emisor")
        )
        detalle = ""
    else:
        actor_id = _primer_valor(
            payload, ("userId", "autorId", "actorId", "user_id", "actor_id")
        )
        producto_id = _primer_valor(payload, ("productId", "productoId"))
        destinatario_id = _primer_valor(
            payload, ("productorId", "autorProductoId", "destinatarioId", "receptorId")
        )
        if not destinatario_id and producto_id and product_author_provider:
            destinatario_id = str(product_author_provider(producto_id) or "").strip()
        tipo = TIPOS_COMUNIDAD[EVENTO_REVIEW_CREATED]
        nombre = _primer_valor(
            payload, ("usuarioNombre", "actorNombre", "nombre", "emisor")
        )
        detalle = detalle_calificacion(
            payload.get("calificacion", payload.get("rating", ""))
        )

    if not actor_id or not destinatario_id or actor_id == destinatario_id:
        return None

    if not nombre and account_provider:
        cuenta = account_provider(actor_id)
        nombre = str(getattr(cuenta, "nombre", "") or "") if cuenta else ""

    return CommunityInteraction(
        topic=topic,
        actor_id=actor_id,
        destinatario_id=destinatario_id,
        tipo=tipo,
        emisor=emisor_publico(nombre),
        detalle=detalle,
        clave_idempotencia=clave_idempotencia(topic, payload, destinatario_id),
    )


__all__ = [
    "COMU_11",
    "EVENTOS_COMUNIDAD",
    "EVENTO_REVIEW_CREATED",
    "EVENTO_USER_FOLLOWED",
    "PLANTILLAS_VERSIONADAS",
    "PLANTILLA_VERSION_ACTUAL",
    "TIPOS_COMUNIDAD",
    "CommunityInteraction",
    "clave_idempotencia",
    "comu11_activo",
    "emisor_publico",
    "parsear_evento",
    "renderizar_mensaje",
    "sanitizar_texto",
]
