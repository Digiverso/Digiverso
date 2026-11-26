"""Casos de uso FUN-35 a FUN-37 (SUB-13, reportes y sanciones).

El servicio valida las políticas CAT-14/CAT-15/CAT-16, evita reportes abiertos
duplicados, registra la auditoría de cada decisión y notifica a las partes
después de confirmar el cambio en persistencia.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from app.cache.showcase import ShowcaseCache
from app.core.config import Settings
from app.domain.actor import ADMIN_ROLE, Actor
from app.domain.audit import AuditEvent
from app.domain.auth import Account, Role
from app.domain.exceptions import (
    DuplicateReportError,
    InvalidSanctionError,
    ReportForbiddenError,
    ReportInvalidStateError,
    ReportNotFoundError,
)
from app.domain.notifications import NotificationType
from app.domain.product import ESTADO_ARCHIVADO
from app.domain.report import (
    CAT_14,
    CAT_15,
    CAT_16,
    DECISION_SANCION,
    ESTADO_ABIERTO,
    ESTADO_RESUELTO,
    ESTADOS_PENDIENTES,
    EVENTO_REPORTE_CREADO,
    EVENTO_REPORTE_RESUELTO,
    EVENTO_SANCION_APLICADA,
    TIPO_SUSPENSION,
    Reporte,
    Resolucion,
    Sancion,
    evidencia_hash,
    normalizar_accion_contenido,
    normalizar_decision,
    normalizar_duracion,
    normalizar_motivo,
    normalizar_tipo_contenido,
    normalizar_tipo_sancion,
    observacion_o_default,
    tiene_evidencia,
    validar_contenido_id,
    validar_evidencia,
)
from app.repository.audit import SQLiteAuditRepository
from app.repository.auth_repository import auth_repository
from app.repository.events import InMemoryEventBus
from app.repository.products import SQLiteProductRepository
from app.repository.reports import ReportRepository
from app.services.notifications import NotificationPublisher

Principal = Actor | Account

REPORT_SCOPE = "catalog.reports.write"


class ReportService:
    """Reportar contenido, gestionar reportes y aplicar sanciones."""

    def __init__(
        self,
        repository: ReportRepository,
        audit_repository: SQLiteAuditRepository,
        settings: Settings,
        event_bus: InMemoryEventBus,
        product_repository: SQLiteProductRepository | None = None,
        notifier: NotificationPublisher | None = None,
        clock: Callable[[], datetime] | None = None,
        showcase_cache: ShowcaseCache | None = None,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
        self.settings = settings
        self.event_bus = event_bus
        self.product_repository = product_repository
        self.notifier = notifier
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.showcase_cache = showcase_cache

    # --------------------------------------------------------------- helpers
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
            or REPORT_SCOPE in roles
        )

    @classmethod
    def _ensure_admin(cls, actor: Principal) -> None:
        if not cls._es_admin(actor):
            raise ReportForbiddenError(
                "Solo un administrador puede gestionar reportes y sanciones.",
                details={
                    "codigo": "REPORT_FORBIDDEN",
                    "permiso": REPORT_SCOPE,
                    "actorId": cls._actor_id(actor),
                    "actorRoles": list(cls._roles(actor)),
                },
            )

    @staticmethod
    def _nombre(cuenta_id: str) -> str:
        cuenta = auth_repository.obtener_cuenta_por_id(cuenta_id)
        return cuenta.nombre if cuenta else ""

    def _now(self) -> datetime:
        return self.clock()

    def _record(
        self,
        entidad: str,
        entidad_id: str,
        *,
        accion: str,
        actor: Principal,
        fecha: datetime,
        cambios: Mapping[str, Any],
    ) -> None:
        self.audit_repository.record(
            AuditEvent(
                entidad=entidad,
                entidad_id=entidad_id,
                accion=accion,
                actor_id=self._actor_id(actor),
                actor_roles=self._roles(actor),
                fecha=fecha,
                cambios=dict(cambios),
            )
        )

    def _notify(
        self,
        cuenta_id: str,
        *,
        tipo: NotificationType | str,
        detalle: str,
        clave: str,
    ) -> bool:
        if not cuenta_id or self.notifier is None:
            return False
        try:
            notificacion = self.notifier.notificar_evento(
                cuenta_id=cuenta_id,
                tipo=tipo,
                contexto={"detalle": detalle},
                clave_idempotencia=clave,
                nombre=self._nombre(cuenta_id),
            )
        except Exception:
            # Un fallo de entrega no revierte una decisión ya registrada.
            return False
        return notificacion is not None

    def _restrict_content(
        self,
        contenido_id: str,
        *,
        accion: str,
        fecha: datetime,
        actor: Principal,
        sancion_id: str,
    ) -> str | None:
        """Archiva o restringe el producto sancionado y lo retira de la vitrina."""

        if self.product_repository is None:
            return None
        producto = self.product_repository.get(contenido_id)
        if producto is None:
            return None
        estado_anterior = producto.estado
        if accion == "archivar":
            producto.estado = ESTADO_ARCHIVADO
        producto.activo = False
        producto.actualizado_en = fecha
        producto.estado_desde = fecha
        if accion == "archivar":
            producto.archivado_en = fecha
        self.product_repository.update(producto)
        if self.showcase_cache is not None:
            self.showcase_cache.invalidate()
        self._record(
            "producto",
            producto.id,
            accion="sancionar_contenido",
            actor=actor,
            fecha=fecha,
            cambios={
                "estadoAnterior": estado_anterior,
                "estado": producto.estado,
                "activo": producto.activo,
                "accion": accion,
                "sancionId": sancion_id,
                "politica": CAT_15,
            },
        )
        return producto.estado

    # --------------------------------------------------------------- FUN-35
    def create_report(
        self,
        actor: Principal,
        *,
        contenido_id: object,
        motivo: object,
        evidencia: Any,
        tipo_contenido: object = None,
        descripcion: object = None,
    ) -> Reporte:
        contenido = validar_contenido_id(contenido_id)
        motivo_normalizado = normalizar_motivo(motivo)
        prueba = validar_evidencia(evidencia)
        tipo = normalizar_tipo_contenido(tipo_contenido, contenido)

        if self.repository.has_open(self._actor_id(actor), contenido):
            raise DuplicateReportError(
                "Ya tienes un reporte abierto sobre este contenido.",
                details={
                    "codigo": "REPORT_DUPLICATE",
                    "contenidoId": contenido,
                },
            )

        ahora = self._now()
        reporte = Reporte(
            id="",
            contenido_id=contenido,
            motivo=motivo_normalizado,
            evidencia=prueba,
            reportante_id=self._actor_id(actor),
            fecha=ahora,
            tipo_contenido=tipo,
            estado=ESTADO_ABIERTO,
            evidencia_hash=evidencia_hash(prueba),
            metadatos={
                "descripcion": str(descripcion or "").strip(),
                "politica": CAT_14,
            },
        )
        reporte = self.repository.save(reporte)
        self._record(
            "reporte",
            reporte.id,
            accion="crear_reporte",
            actor=actor,
            fecha=ahora,
            cambios={
                "contenidoId": reporte.contenido_id,
                "tipoContenido": reporte.tipo_contenido,
                "motivo": reporte.motivo,
                "politica": CAT_14,
                "estado": reporte.estado,
                "evidencia": reporte.evidencia,
                "evidenciaHash": reporte.evidencia_hash,
            },
        )
        self.event_bus.publish(
            EVENTO_REPORTE_CREADO,
            {
                "reporteId": reporte.id,
                "reportId": reporte.id,
                "contenidoId": reporte.contenido_id,
                "motivo": reporte.motivo,
                "estado": reporte.estado,
                "fecha": ahora.isoformat(),
                "politica": CAT_14,
            },
        )
        self._notify(
            reporte.reportante_id,
            tipo=NotificationType.REPORTE_RECIBIDO,
            detalle=(
                f"Reporte {reporte.id} sobre {reporte.contenido_id}. "
                f"Motivo ({CAT_14}): {reporte.motivo}."
            ),
            clave=f"{EVENTO_REPORTE_CREADO}:{reporte.id}",
        )
        return reporte

    # --------------------------------------------------------------- FUN-36
    def list_reports(
        self,
        actor: Principal,
        *,
        estado: str | None = None,
        contenido_id: str | None = None,
        motivo: str | None = None,
        pagina: int = 1,
        tamanio: int = 20,
    ) -> tuple[list[Reporte], int]:
        self._ensure_admin(actor)
        return self.repository.list(
            estado=estado,
            contenido_id=contenido_id,
            motivo=motivo,
            limite=max(1, min(int(tamanio), 100)),
            offset=max(0, (max(1, int(pagina)) - 1) * max(1, min(int(tamanio), 100))),
        )

    def get_report(self, actor: Principal, reporte_id: str) -> Reporte:
        self._ensure_admin(actor)
        return self.repository.get_or_raise(reporte_id)

    def resolve_report(
        self,
        reporte_id: str,
        actor: Principal,
        *,
        decision: object,
        observacion: object = None,
        sancion: Mapping[str, Any] | None = None,
    ) -> tuple[Reporte, Sancion | None]:
        self._ensure_admin(actor)
        reporte = self.repository.get_or_raise(reporte_id)
        if reporte.estado not in ESTADOS_PENDIENTES:
            raise ReportInvalidStateError(
                "El reporte ya fue resuelto.",
                details={
                    "codigo": "REPORT_INVALID_STATE",
                    "id": reporte.id,
                    "estado": reporte.estado,
                },
            )
        decision_normalizada = normalizar_decision(decision)
        observacion_limpia = observacion_o_default(
            observacion, decision=decision_normalizada
        )
        ahora = self._now()
        sancion_aplicada: Sancion | None = None

        if decision_normalizada == DECISION_SANCION:
            datos = dict(sancion or {})
            sancion_aplicada = self._create_sanction(
                actor,
                reporte=reporte,
                tipo=datos.get("tipo") or datos.get("tipoSancion"),
                duracion_dias=datos.get("duracionDias") or datos.get("duracion_dias"),
                usuario_afectado=(
                    datos.get("usuarioAfectado") or datos.get("usuario_afectado")
                ),
                motivo=datos.get("motivo") or reporte.motivo,
                observacion=datos.get("observacion") or observacion_limpia,
                evidencia=datos.get("evidencia") or reporte.evidencia,
                accion_contenido=datos.get("accionContenido"),
                fecha=ahora,
            )

        reporte.estado = ESTADO_RESUELTO
        reporte.resolucion = Resolucion(
            decision=decision_normalizada,
            observacion=observacion_limpia,
            fecha=ahora,
            administrador_id=self._actor_id(actor),
            sancion_id=sancion_aplicada.id if sancion_aplicada else None,
        )
        self.repository.update(reporte)
        self._record(
            "reporte",
            reporte.id,
            accion="resolver_reporte",
            actor=actor,
            fecha=ahora,
            cambios={
                "decision": decision_normalizada,
                "sancion": sancion_aplicada.id if sancion_aplicada else None,
                "observacion": observacion_limpia,
                "estado": reporte.estado,
                "motivo": reporte.motivo,
                "politica": CAT_14,
            },
        )
        self.event_bus.publish(
            EVENTO_REPORTE_RESUELTO,
            {
                "reporteId": reporte.id,
                "reportId": reporte.id,
                "contenidoId": reporte.contenido_id,
                "decision": decision_normalizada,
                "sancionId": sancion_aplicada.id if sancion_aplicada else None,
                "observacion": observacion_limpia,
                "fecha": ahora.isoformat(),
                "administradorId": self._actor_id(actor),
            },
        )
        self._notify_reporter(reporte)
        if sancion_aplicada is not None:
            self._notify_affected(sancion_aplicada)
        return reporte, sancion_aplicada

    def _notify_reporter(self, reporte: Reporte) -> None:
        decision = reporte.resolucion.decision if reporte.resolucion else ""
        observacion = reporte.resolucion.observacion if reporte.resolucion else ""
        self._notify(
            reporte.reportante_id,
            tipo=NotificationType.REPORTE_RESUELTO,
            detalle=(
                f"Reporte {reporte.id}: decisión {decision}. "
                f"Motivo ({CAT_14}): {reporte.motivo}. Observación: {observacion}."
            ),
            clave=f"{EVENTO_REPORTE_RESUELTO}:{reporte.id}",
        )

    def _notify_affected(self, sancion: Sancion) -> bool:
        detalle = (
            f"Tipo: {sancion.tipo} ({CAT_15}). "
            f"Motivo ({CAT_14}): {sancion.motivo}. Observación: {sancion.observacion}."
        )
        if sancion.tipo == TIPO_SUSPENSION:
            detalle += (
                f" Duración: {sancion.duracion_dias} días ({CAT_16})."
            )
        if sancion.apelable:
            detalle += " Puedes apelar por el canal de soporte."
        return self._notify(
            sancion.usuario_afectado,
            tipo=NotificationType.SANCION_APLICADA,
            detalle=detalle,
            clave=f"{EVENTO_SANCION_APLICADA}:{sancion.id}",
        )

    # --------------------------------------------------------------- FUN-37
    def _create_sanction(
        self,
        actor: Principal,
        *,
        reporte: Reporte | None,
        contenido_id: str | None = None,
        tipo: object = None,
        duracion_dias: object = None,
        usuario_afectado: object = None,
        motivo: object = None,
        observacion: object = None,
        evidencia: Any = None,
        accion_contenido: object = None,
        fecha: datetime | None = None,
    ) -> Sancion:
        fecha = fecha or self._now()
        tipo_normalizado = normalizar_tipo_sancion(tipo or TIPO_RESTRICCION)
        contenido_id = contenido_id or (reporte.contenido_id if reporte else "")
        prueba = evidencia if tiene_evidencia(evidencia) else (
            reporte.evidencia if reporte else None
        )
        validar_evidencia(prueba)

        afectado = str(usuario_afectado or "").strip()
        if not afectado and contenido_id.startswith("usr_"):
            afectado = contenido_id
        if not afectado and self.product_repository is not None:
            producto = self.product_repository.get(contenido_id)
            if producto is not None:
                afectado = producto.autor_id
        if not afectado:
            raise InvalidSanctionError(
                "El usuario afectado por la sanción es obligatorio.",
                details={"codigo": "SANCTION_USER_REQUIRED", "campo": "usuarioAfectado"},
            )

        if tipo_normalizado == TIPO_SUSPENSION:
            duracion = normalizar_duracion(
                duracion_dias,
                por_defecto=getattr(self.settings, "report_suspension_days", 7),
            )
        else:
            duracion = int(duracion_dias) if str(duracion_dias or "").isdigit() else 0
        accion = normalizar_accion_contenido(
            accion_contenido, tipo_sancion=tipo_normalizado
        )
        sancion = Sancion(
            id="",
            reporte_id=reporte.id if reporte else None,
            contenido_id=contenido_id,
            tipo=tipo_normalizado,
            duracion_dias=duracion,
            usuario_afectado=afectado,
            fecha=fecha,
            motivo=str(motivo or (reporte.motivo if reporte else "")).strip(),
            observacion=str(observacion or "").strip(),
            evidencia=prueba,
            evidencia_hash=evidencia_hash(prueba),
            accion_contenido=accion,
        )
        sancion = self.repository.save_sanction(sancion)
        sancion.estado_contenido = self._restrict_content(
            sancion.contenido_id,
            accion=sancion.accion_contenido,
            fecha=fecha,
            actor=actor,
            sancion_id=sancion.id,
        )
        self.repository.update_sanction(sancion)
        sancion.notificado = self._notify_affected(sancion)
        self.repository.update_sanction(sancion)

        self._record(
            "sancion",
            sancion.id,
            accion="aplicar_sancion",
            actor=actor,
            fecha=fecha,
            cambios={
                "reporteId": sancion.reporte_id,
                "contenidoId": sancion.contenido_id,
                "tipo": sancion.tipo,
                "politica": CAT_15,
                "duracionDias": sancion.duracion_dias,
                "duracionPolitica": CAT_16 if sancion.tipo == TIPO_SUSPENSION else None,
                "usuarioAfectado": sancion.usuario_afectado,
                "motivo": sancion.motivo,
                "observacion": sancion.observacion,
                "accionContenido": sancion.accion_contenido,
                "evidencia": sancion.evidencia,
                "evidenciaHash": sancion.evidencia_hash,
                "apelable": sancion.apelable,
                "notificado": sancion.notificado,
            },
        )
        self.event_bus.publish(
            EVENTO_SANCION_APLICADA,
            {
                "sancionId": sancion.id,
                "reporteId": sancion.reporte_id,
                "contenidoId": sancion.contenido_id,
                "tipo": sancion.tipo,
                "duracionDias": sancion.duracion_dias,
                "usuarioAfectado": sancion.usuario_afectado,
                "accionContenido": sancion.accion_contenido,
                "estadoContenido": sancion.estado_contenido,
                "fecha": fecha.isoformat(),
                "politica": CAT_15,
            },
        )
        return sancion

    def apply_sanction(
        self,
        actor: Principal,
        *,
        reporte_id: object = None,
        contenido_id: object = None,
        tipo: object = None,
        duracion_dias: object = None,
        usuario_afectado: object = None,
        motivo: object = None,
        evidencia: Any = None,
        observacion: object = None,
        accion_contenido: object = None,
    ) -> Sancion:
        self._ensure_admin(actor)
        reporte = None
        if reporte_id and str(reporte_id).strip():
            reporte = self.repository.get_or_raise(str(reporte_id).strip())
        contenido = str(contenido_id or "").strip() or (
            reporte.contenido_id if reporte else ""
        )
        if not contenido:
            raise InvalidSanctionError(
                "El contenido sancionado es obligatorio.",
                details={"codigo": "SANCTION_CONTENT_REQUIRED", "campo": "contenidoId"},
            )
        if reporte is None:
            # Se admite sancionar sin reporte previo siempre que haya evidencia.
            reporte = Reporte(
                id="",
                contenido_id=contenido,
                motivo=str(motivo or "").strip() or "otro",
                evidencia=evidencia,
                reportante_id=self._actor_id(actor),
                fecha=self._now(),
                estado=ESTADO_ABIERTO,
            )
        sancion = self._create_sanction(
            actor,
            reporte=reporte if reporte.id else None,
            contenido_id=contenido,
            tipo=tipo,
            duracion_dias=duracion_dias,
            usuario_afectado=usuario_afectado,
            motivo=motivo or reporte.motivo,
            observacion=observacion,
            evidencia=evidencia if tiene_evidencia(evidencia) else reporte.evidencia,
            accion_contenido=accion_contenido,
            fecha=self._now(),
        )
        if reporte.id and reporte.estado in ESTADOS_PENDIENTES:
            reporte.estado = ESTADO_RESUELTO
            reporte.resolucion = Resolucion(
                decision=DECISION_SANCION,
                observacion=str(observacion or sancion.observacion),
                fecha=sancion.fecha,
                administrador_id=self._actor_id(actor),
                sancion_id=sancion.id,
            )
            self.repository.update(reporte)
            self._record(
                "reporte",
                reporte.id,
                accion="resolver_reporte",
                actor=actor,
                fecha=sancion.fecha,
                cambios={
                    "decision": DECISION_SANCION,
                    "sancion": sancion.id,
                    "observacion": reporte.resolucion.observacion,
                    "estado": reporte.estado,
                },
            )
            self.event_bus.publish(
                EVENTO_REPORTE_RESUELTO,
                {
                    "reporteId": reporte.id,
                    "contenidoId": reporte.contenido_id,
                    "decision": DECISION_SANCION,
                    "sancionId": sancion.id,
                    "fecha": sancion.fecha.isoformat(),
                },
            )
            self._notify_reporter(reporte)
        return sancion

    # ------------------------------------------------------------ consultas
    def list_sanctions(
        self,
        actor: Principal,
        *,
        reporte_id: str | None = None,
        usuario_afectado: str | None = None,
    ) -> list[Sancion]:
        self._ensure_admin(actor)
        return self.repository.list_sanctions(
            reporte_id=reporte_id, usuario_afectado=usuario_afectado
        )

    def get_sanction(self, actor: Principal, sancion_id: str) -> Sancion:
        self._ensure_admin(actor)
        sancion = self.repository.get_sanction(sancion_id)
        if sancion is None:
            raise ReportNotFoundError(
                "No existe la sanción solicitada.",
                details={"codigo": "SANCTION_NOT_FOUND", "id": sancion_id},
            )
        return sancion
