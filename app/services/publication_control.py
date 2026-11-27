"""Casos de uso FUN-32 a FUN-34 y FUN-38 (SUB-13, control de publicaciones)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from app.cache.showcase import ShowcaseCache
from app.core.config import Settings
from app.domain.actor import ADMIN_ROLE, Actor
from app.domain.audit import AuditEvent
from app.domain.auth import Account, Role
from app.domain.exceptions import ProductNotFoundError, ReviewForbiddenError
from app.domain.notifications import NotificationType
from app.domain.product import (
    ESTADO_EN_REVISION,
    ESTADO_PUBLICADO,
    ESTADO_RECHAZADO,
    Product,
    ensure_transition,
)
from app.domain.publication_review import (
    CAT_14,
    DECISION_APROBADA,
    DECISION_RECHAZADA,
    EVENTO_PRODUCT_REVIEWED,
    POLITICAS_PUBLICACION,
    ProductReviewedEvent,
    normalizar_checklist,
    normalizar_motivo,
    validar_observacion,
)
from app.repository.audit import SQLiteAuditRepository
from app.repository.events import InMemoryEventBus
from app.repository.products import SQLiteProductRepository
from app.services.notifications import NotificationPublisher

Principal = Actor | Account

REVIEW_SCOPE = "catalog.product.review.write"


@dataclass(frozen=True)
class QueueEntry:
    """Producto en revisión junto con la fecha de envío que lo ordena."""

    producto: Product
    fecha_envio: datetime


class PublicationControlService:
    """Consulta la cola, decide la publicación y notifica al productor."""

    def __init__(
        self,
        repository: SQLiteProductRepository,
        audit_repository: SQLiteAuditRepository,
        settings: Settings,
        event_bus: InMemoryEventBus,
        notifier: NotificationPublisher | None = None,
        clock: Callable[[], datetime] | None = None,
        showcase_cache: ShowcaseCache | None = None,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
        self.settings = settings
        self.event_bus = event_bus
        self.notifier = notifier
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.showcase_cache = showcase_cache

    # --------------------------------------------------------------- helpers
    def _now(self) -> datetime:
        return self.clock()

    @staticmethod
    def _actor_id(actor: Principal) -> str:
        return actor.id

    @staticmethod
    def _roles(actor: Principal) -> tuple[str, ...]:
        if isinstance(actor, Account):
            return (actor.rol.value,)
        return actor.roles

    @classmethod
    def _es_admin(cls, actor: Principal) -> bool:
        roles = cls._roles(actor)
        return (
            ADMIN_ROLE in roles
            or Role.ADMINISTRADOR.value in roles
            or REVIEW_SCOPE in roles
        )

    @classmethod
    def _ensure_admin(cls, actor: Principal) -> None:
        if not cls._es_admin(actor):
            raise ReviewForbiddenError(
                "Solo un administrador puede revisar publicaciones.",
                details={
                    "codigo": "REVIEW_FORBIDDEN",
                    "permiso": REVIEW_SCOPE,
                    "actorId": cls._actor_id(actor),
                    "actorRoles": list(cls._roles(actor)),
                },
            )

    @classmethod
    def _ensure_separacion_funciones(cls, product: Product, actor: Principal) -> None:
        """Quien autorizó el contenido no puede certificarlo (HU-11)."""

        if product.autor_id == cls._actor_id(actor):
            raise ReviewForbiddenError(
                "Un administrador no puede revisar un producto de su autoría.",
                details={
                    "codigo": "REVIEW_SEPARATION_OF_DUTIES",
                    "productoId": product.id,
                    "autorId": product.autor_id,
                    "actorId": cls._actor_id(actor),
                },
            )

    def _get(self, product_id: str) -> Product:
        product = self.repository.get(product_id)
        if product is None:
            raise ProductNotFoundError(
                "El producto no existe.", details={"id": product_id}
            )
        return product

    def _invalidate_showcase(self) -> None:
        if self.showcase_cache is not None:
            self.showcase_cache.invalidate()

    @staticmethod
    def politicas() -> list[dict[str, str]]:
        return [
            {"codigo": politica.codigo, "descripcion": politica.descripcion}
            for politica in POLITICAS_PUBLICACION
        ]

    def _record(
        self,
        product: Product,
        *,
        accion: str,
        actor: Principal,
        fecha: datetime,
        cambios: Mapping[str, Any],
    ) -> None:
        self.audit_repository.record(
            AuditEvent(
                entidad="producto",
                entidad_id=product.id,
                accion=accion,
                actor_id=self._actor_id(actor),
                actor_roles=self._roles(actor),
                fecha=fecha,
                cambios=dict(cambios),
            )
        )

    # --------------------------------------------------------------- FUN-32
    def queue(self, *, actor: Principal) -> list[QueueEntry]:
        """Solo productos ``en_revision``, ordenados por antigüedad."""

        self._ensure_admin(actor)
        return [
            QueueEntry(producto=product, fecha_envio=product.estado_desde)
            for product in self.repository.list_review_queue()
        ]

    # ------------------------------------------------------- FUN-33 / FUN-34
    def approve(
        self,
        product_id: str,
        *,
        actor: Principal,
        checklist: object,
    ) -> tuple[Product, bool]:
        self._ensure_admin(actor)
        product = self._get(product_id)
        self._ensure_separacion_funciones(product, actor)
        ensure_transition(
            product.estado, frozenset({ESTADO_EN_REVISION}), "aprobar"
        )
        evidencia = normalizar_checklist(checklist)
        return self._decide(
            product,
            actor=actor,
            decision=DECISION_APROBADA,
            nuevo_estado=ESTADO_PUBLICADO,
            accion="aprobar_publicacion",
            evidencia={"checklist": evidencia},
        )

    def reject(
        self,
        product_id: str,
        *,
        actor: Principal,
        motivo: object,
        observacion: object,
    ) -> tuple[Product, bool]:
        self._ensure_admin(actor)
        product = self._get(product_id)
        self._ensure_separacion_funciones(product, actor)
        ensure_transition(
            product.estado, frozenset({ESTADO_EN_REVISION}), "rechazar"
        )
        motivo_limpio = normalizar_motivo(motivo)
        observacion_limpia = validar_observacion(observacion)
        return self._decide(
            product,
            actor=actor,
            decision=DECISION_RECHAZADA,
            nuevo_estado=ESTADO_RECHAZADO,
            accion="rechazar_publicacion",
            evidencia={
                "motivo": motivo_limpio,
                "observacion": observacion_limpia,
                "codigo": CAT_14,
            },
        )

    def _decide(
        self,
        product: Product,
        *,
        actor: Principal,
        decision: str,
        nuevo_estado: str,
        accion: str,
        evidencia: dict[str, Any],
    ) -> tuple[Product, bool]:
        estado_anterior = product.estado
        fecha_envio = product.estado_desde
        ahora = self._now()

        product.estado = nuevo_estado
        product.activo = nuevo_estado == ESTADO_PUBLICADO
        product.estado_desde = ahora
        product.actualizado_en = ahora
        product.cambios_pendientes = False

        # 1) El cambio de estado se confirma antes de publicar el evento o
        #    enviar la notificación (notas técnicas de HU-11).
        self.repository.update(product)
        self._invalidate_showcase()
        self._record(
            product,
            accion=accion,
            actor=actor,
            fecha=ahora,
            cambios={
                "estadoAnterior": estado_anterior,
                "estado": nuevo_estado,
                "decision": decision,
                "fecha": ahora.astimezone(timezone.utc).isoformat(),
                "fechaEnvio": fecha_envio.astimezone(timezone.utc).isoformat(),
                "evidencia": {
                    **evidencia,
                    "contenido": product.content(),
                    "hashContenido": product.content_hash(),
                    "autorId": product.autor_id,
                },
            },
        )

        # 2) Evento y notificación después del commit.
        evento = ProductReviewedEvent(
            producto_id=product.id,
            decision=decision,
            administrador_id=self._actor_id(actor),
            fecha=ahora,
            checklist=dict(evidencia.get("checklist") or {})
            if decision == DECISION_APROBADA
            else None,
            motivo=evidencia.get("motivo") if decision == DECISION_RECHAZADA else None,
            observacion=(
                evidencia.get("observacion") if decision == DECISION_RECHAZADA else None
            ),
        )
        self.event_bus.publish(EVENTO_PRODUCT_REVIEWED, evento.to_payload())
        notificado = self._notificar(product, evento=evento)
        return product, notificado

    def _notificar(self, product: Product, *, evento: ProductReviewedEvent) -> bool:
        if self.notifier is None:
            return False
        aprobado = evento.decision == DECISION_APROBADA
        tipo = (
            NotificationType.PRODUCTO_PUBLICADO
            if aprobado
            else NotificationType.PRODUCTO_RECHAZADO
        )
        detalle = (
            f"Decisión: {evento.decision}. "
            f"Fecha de publicación: {evento.fecha.astimezone(timezone.utc).isoformat()}."
            if aprobado
            else (
                f"Decisión: {evento.decision}. Motivo ({CAT_14}): {evento.motivo}. "
                f"Observación: {evento.observacion}."
            )
        )
        try:
            notificacion = self.notifier.notificar_evento(
                cuenta_id=product.autor_id,
                tipo=tipo,
                contexto={"detalle": detalle},
                clave_idempotencia=(
                    f"{EVENTO_PRODUCT_REVIEWED}:{product.id}:"
                    f"{evento.fecha.astimezone(timezone.utc).isoformat()}:{evento.decision}"
                ),
                nombre=product.autor_nombre,
            )
        except Exception:
            # Igual que HU-01: un fallo de entrega no revierte la decisión.
            return False
        return notificacion is not None
