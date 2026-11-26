"""Casos de uso FUN-26 (cargar medio) y FUN-27 (eliminar medio) del SUB-10."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.cache.showcase import ShowcaseCache
from app.core.config import Settings
from app.domain.actor import Actor
from app.domain.audit import AuditEvent
from app.domain.exceptions import (
    ForbiddenError,
    MediaNotFoundError,
    MediaScanError,
    ProductNotFoundError,
)
from app.domain.media import (
    ArchivoMedio,
    detectar_formato,
    ensure_cantidad,
    formatos_permitidos,
    marcar_eliminado,
    medios_activos,
    reordenar_medios,
    siguiente_orden,
    validate_tamano,
)
from app.domain.product import (
    ESTADOS_EDITABLES,
    MEDIO_ACTIVO,
    Medio,
    Product,
    ensure_transition,
)
from app.repository.audit import SQLiteAuditRepository
from app.repository.products import SQLiteProductRepository
from app.services.media_processing import BestEffortMediaProcessor, MediaProcessor
from app.services.media_scan import FileScanner, SignatureFileScanner
from app.services.media_storage import LocalMediaStorage, MediaStorage


class MediaService:
    """Orquesta validación, escaneo, almacenamiento y auditoría de medios."""

    def __init__(
        self,
        repository: SQLiteProductRepository,
        audit_repository: SQLiteAuditRepository,
        settings: Settings,
        *,
        scanner: FileScanner | None = None,
        processor: MediaProcessor | None = None,
        storage: MediaStorage | None = None,
        clock: Callable[[], datetime] | None = None,
        showcase_cache: ShowcaseCache | None = None,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
        self.settings = settings
        self.showcase_cache = showcase_cache
        self.scanner = scanner or SignatureFileScanner()
        self.processor = processor or BestEffortMediaProcessor()
        self.storage = storage or LocalMediaStorage(settings)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.formatos = formatos_permitidos(
            settings.media_image_formats, settings.media_video_formats
        )

    # --------------------------------------------------------------- helpers
    def _now(self) -> datetime:
        return self.clock()

    def _formatos_permitidos(self):
        """Relee CAT-05/CAT-07: un cambio de parámetros aplica sin recrear el servicio."""

        return formatos_permitidos(
            self.settings.media_image_formats, self.settings.media_video_formats
        )

    def _get(self, product_id: str) -> Product:
        product = self.repository.get(product_id)
        if product is None:
            raise ProductNotFoundError(
                "El producto no existe.", details={"id": product_id}
            )
        return product

    @staticmethod
    def _ensure_owner(product: Product, actor: Actor) -> None:
        if product.autor_id != actor.id:
            raise ForbiddenError(
                "Solo el autor del producto puede gestionar sus medios.",
                details={
                    "productoId": product.id,
                    "autorId": product.autor_id,
                    "actorId": actor.id,
                },
            )

    @staticmethod
    def _ensure_editable(product: Product) -> None:
        ensure_transition(product.estado, ESTADOS_EDITABLES, "editar los medios de")

    def _record(
        self,
        product: Product,
        *,
        accion: str,
        actor: Actor,
        cambios: dict[str, Any],
    ) -> None:
        self.audit_repository.record(
            AuditEvent(
                entidad="producto",
                entidad_id=product.id,
                accion=accion,
                actor_id=actor.id,
                actor_roles=actor.roles,
                fecha=self._now(),
                cambios=cambios,
            )
        )

    def _invalidate_showcase(self) -> None:
        """La miniatura de la vitrina (HU-10) depende de los medios visibles."""
        if self.showcase_cache is not None:
            self.showcase_cache.invalidate()

    @staticmethod
    def _detalle(medio: Medio) -> dict[str, Any]:
        return {
            "id": medio.id,
            "tipo": medio.tipo,
            "url": medio.url,
            "orden": medio.orden,
            "estado": medio.estado,
        }

    # --------------------------------------------------------------- FUN-26
    def upload(
        self, product_id: str, *, archivo: ArchivoMedio, actor: Actor
    ) -> Medio:
        """Valida, escanea, almacena y asocia un medio al producto."""

        product = self._get(product_id)
        self._ensure_owner(product, actor)
        self._ensure_editable(product)

        activos = medios_activos(product.medios)
        ensure_cantidad(len(activos), maximo=self.settings.media_max_per_product)

        detectado = detectar_formato(archivo, formatos=self._formatos_permitidos())
        es_imagen = detectado.formato.tipo == "imagen"
        validate_tamano(
            archivo,
            maximo=(
                self.settings.media_max_image_bytes
                if es_imagen
                else self.settings.media_max_video_bytes
            ),
            codigo="CAT-06" if es_imagen else "CAT-08",
        )

        # CAT: ningún medio se publica sin pasar el escaneo.
        resultado = self.scanner.scan(archivo.contenido, nombre=archivo.nombre)
        if not resultado.seguro:
            raise MediaScanError(
                "El archivo no superó el escaneo de seguridad.",
                details={
                    "campo": "archivo",
                    "motivo": resultado.motivo,
                    "nombre": archivo.nombre,
                },
            )

        procesado = self.processor.process(
            archivo.contenido,
            tipo=detectado.formato.tipo,
            extension=detectado.extension,
            formato=detectado.formato.clave,
        )

        medio_id = self.repository.next_media_id()
        url = self.storage.save(
            product_id, medio_id, procesado.contenido, procesado.extension
        )
        medio = Medio(
            id=medio_id,
            tipo=detectado.formato.tipo,
            url=url,
            orden=siguiente_orden(product.medios),
            estado=MEDIO_ACTIVO,
        )
        product.medios.append(medio)
        product.actualizado_en = self._now()
        self.repository.update(product)
        self._invalidate_showcase()
        self._record(
            product,
            accion="cargar_medio",
            actor=actor,
            cambios={
                "medio": self._detalle(medio),
                "totalMedios": len(medios_activos(product.medios)),
            },
        )
        return medio

    # --------------------------------------------------------------- FUN-27
    def delete(
        self, product_id: str, media_id: str, *, actor: Actor
    ) -> tuple[Medio, list[Medio]]:
        """Elimina lógicamente un medio propio y reordena los restantes."""

        product = self._get(product_id)
        self._ensure_owner(product, actor)
        self._ensure_editable(product)

        objetivo = next(
            (
                medio
                for medio in product.medios
                if medio.id == media_id and medio.visible
            ),
            None,
        )
        if objetivo is None:
            raise MediaNotFoundError(
                "El medio no existe o ya fue eliminado.",
                details={"productoId": product_id, "mediaId": media_id},
            )

        product.medios = reordenar_medios(
            [marcar_eliminado(medio) if medio.id == media_id else medio for medio in product.medios]
        )
        product.actualizado_en = self._now()
        self.repository.update(product)
        self._invalidate_showcase()
        restantes = medios_activos(product.medios)
        self._record(
            product,
            accion="eliminar_medio",
            actor=actor,
            cambios={
                "medioId": media_id,
                "estado": "eliminado",
                "totalMedios": len(restantes),
                "medios": [self._detalle(medio) for medio in restantes],
            },
        )
        return objetivo, restantes

    def list_medios(self, product_id: str) -> list[Medio]:
        return medios_activos(self._get(product_id).medios)
