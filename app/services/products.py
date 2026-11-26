"""Casos de uso FUN-21 a FUN-25 del submódulo SUB-09 (productos)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Final

from app.cache.showcase import ShowcaseCache
from app.core.config import Settings
from app.domain.actor import Actor
from app.domain.catalog_search import ProductQuery, validate_query
from app.domain.audit import AuditEvent
from app.domain.exceptions import ForbiddenError, InvalidProductError, ProductNotFoundError
from app.domain.product import (
    ESTADO_ARCHIVADO,
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADO_PUBLICADO,
    ESTADOS_ARCHIVABLES,
    ESTADOS_EDITABLES,
    ESTADOS_ENVIABLES_A_REVISION,
    MONEDA_POR_DEFECTO,
    Product,
    ensure_min_images,
    ensure_transition,
    validate_categorias,
    validate_descripcion,
    validate_edades,
    validate_medios,
    validate_nombre,
    validate_precio,
)
from app.repository.audit import SQLiteAuditRepository
from app.repository.categories import SQLiteCategoryRepository
from app.repository.products import SQLiteProductRepository

_UNSET: Final = object()


class ProductService:
    """Orquesta validación de dominio, persistencia y auditoría del producto."""

    def __init__(
        self,
        repository: SQLiteProductRepository,
        category_repository: SQLiteCategoryRepository,
        audit_repository: SQLiteAuditRepository,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
        showcase_cache: ShowcaseCache | None = None,
        author_name_provider: Callable[[str], str | None] | None = None,
    ) -> None:
        self.repository = repository
        self.category_repository = category_repository
        self.audit_repository = audit_repository
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.showcase_cache = showcase_cache
        self.author_name_provider = author_name_provider

    # --------------------------------------------------------------- helpers
    def _now(self) -> datetime:
        return self.clock()

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
                "Solo el autor del producto puede realizar esta operación.",
                details={
                    "productoId": product.id,
                    "autorId": product.autor_id,
                    "actorId": actor.id,
                },
            )

    def _invalidate_showcase(self) -> None:
        if self.showcase_cache is not None:
            self.showcase_cache.invalidate()

    def _ensure_known_categories(self, categorias: list[str]) -> None:
        for category_id in categorias:
            category = self.category_repository.get(category_id)
            if category is None or not category.activa:
                raise InvalidProductError(
                    "Las categorías deben existir y estar activas (CAT-13).",
                    details={"categoriaId": category_id, "codigo": "CAT-13"},
                )

    def _validate_all(
        self,
        *,
        nombre: object,
        descripcion: object,
        precio: object,
        moneda: object,
        edad_minima: object,
        edad_maxima: object,
        categorias: object,
        medios: object,
    ) -> dict[str, Any]:
        limpio_nombre = validate_nombre(
            nombre,
            minimo=self.settings.product_name_min_length,
            maximo=self.settings.product_name_max_length,
        )
        limpia_descripcion = validate_descripcion(
            descripcion,
            minimo=self.settings.product_description_min_length,
            maximo=self.settings.product_description_max_length,
        )
        limpio_precio = validate_precio(
            precio,
            minimo=self.settings.product_min_price,
            moneda=str(moneda),
        )
        edad_minima_limpia, edad_maxima_limpia = validate_edades(
            edad_minima, edad_maxima, maximo=self.settings.product_max_age
        )
        limpias_categorias = validate_categorias(
            categorias, maximo=self.settings.product_max_categories
        )
        self._ensure_known_categories(limpias_categorias)
        return {
            "nombre": limpio_nombre,
            "descripcion": limpia_descripcion,
            "precio": limpio_precio,
            "moneda": MONEDA_POR_DEFECTO,
            "edad_minima": edad_minima_limpia,
            "edad_maxima": edad_maxima_limpia,
            "categorias": limpias_categorias,
            "medios": validate_medios(medios),
        }

    def _record(
        self,
        product: Product,
        *,
        accion: str,
        actor: Actor,
        cambios: dict[str, Any],
        fecha: datetime | None = None,
    ) -> None:
        self.audit_repository.record(
            AuditEvent(
                entidad="producto",
                entidad_id=product.id,
                accion=accion,
                actor_id=actor.id,
                actor_roles=actor.roles,
                fecha=fecha or self._now(),
                cambios=cambios,
            )
        )

    @staticmethod
    def _snapshot(product: Product) -> dict[str, Any]:
        return {
            **product.content(),
            "estado": product.estado,
            "activo": product.activo,
            "cambiosPendientes": product.cambios_pendientes,
        }

    def _transition(
        self,
        product: Product,
        *,
        nuevo_estado: str,
        actor: Actor,
        accion: str,
        cambios_extra: dict[str, Any] | None = None,
    ) -> Product:
        estado_anterior = product.estado
        ahora = self._now()
        product.estado = nuevo_estado
        product.activo = nuevo_estado == ESTADO_PUBLICADO
        product.estado_desde = ahora
        product.actualizado_en = ahora
        product.archivo_hash = (
            product.content_hash() if nuevo_estado == ESTADO_ARCHIVADO else None
        )
        product.cambios_pendientes = False
        if nuevo_estado == ESTADO_ARCHIVADO:
            product.archivado_en = ahora
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
                "fecha": ahora.astimezone(timezone.utc).isoformat(),
                **(cambios_extra or {}),
            },
        )
        return product

    # --------------------------------------------------------------- FUN-21
    def create(
        self,
        *,
        actor: Actor,
        nombre: str,
        descripcion: str,
        precio: int,
        moneda: str = MONEDA_POR_DEFECTO,
        edad_minima: int = 0,
        edad_maxima: int = 99,
        categorias: list[str] | None = None,
        medios: list[object] | None = None,
        autor_id: object = _UNSET,
    ) -> Product:
        """Crea el producto en borrador; ``autor_id`` del cuerpo se ignora."""

        del autor_id
        limpio = self._validate_all(
            nombre=nombre,
            descripcion=descripcion,
            precio=precio,
            moneda=moneda,
            edad_minima=edad_minima,
            edad_maxima=edad_maxima,
            categorias=categorias or [],
            medios=medios or [],
        )
        ahora = self._now()
        nombre_autor = (
            self.author_name_provider(actor.id) if self.author_name_provider else None
        )
        product = Product(
            id=self.repository.next_id(),
            nombre=limpio["nombre"],
            descripcion=limpio["descripcion"],
            autor_nombre=(nombre_autor or "Autor Digiverso").strip(),
            precio=limpio["precio"],
            moneda=limpio["moneda"],
            edad_minima=limpio["edad_minima"],
            edad_maxima=limpio["edad_maxima"],
            categorias=limpio["categorias"],
            medios=limpio["medios"],
            estado=ESTADO_BORRADOR,
            autor_id=actor.id,
            activo=False,
            creado_en=ahora,
            actualizado_en=ahora,
            estado_desde=ahora,
        )
        self.repository.save(product)
        self._invalidate_showcase()
        self._record(
            product,
            accion="crear",
            actor=actor,
            fecha=ahora,
            cambios={"despues": self._snapshot(product)},
        )
        return product

    # --------------------------------------------------------------- FUN-22
    def update(
        self,
        product_id: str,
        *,
        actor: Actor,
        nombre: object = _UNSET,
        descripcion: object = _UNSET,
        precio: object = _UNSET,
        moneda: object = _UNSET,
        edad_minima: object = _UNSET,
        edad_maxima: object = _UNSET,
        categorias: object = _UNSET,
        medios: object = _UNSET,
        autor_id: object = _UNSET,
    ) -> Product:
        """Edita solo los campos enviados; el autor nunca se puede cambiar."""

        del autor_id
        product = self._get(product_id)
        self._ensure_owner(product, actor)
        ensure_transition(product.estado, ESTADOS_EDITABLES, "editar")

        before = self._snapshot(product)
        hash_antes = product.content_hash()
        values: dict[str, Any] = {
            "nombre": product.nombre,
            "descripcion": product.descripcion,
            "precio": product.precio,
            "moneda": product.moneda,
            "edad_minima": product.edad_minima,
            "edad_maxima": product.edad_maxima,
            "categorias": list(product.categorias),
            "medios": list(product.medios),
        }
        provided = {
            "nombre": nombre,
            "descripcion": descripcion,
            "precio": precio,
            "moneda": moneda,
            "edad_minima": edad_minima,
            "edad_maxima": edad_maxima,
            "categorias": categorias,
            "medios": medios,
        }
        for field, value in provided.items():
            if value is not _UNSET:
                values[field] = value

        limpio = self._validate_all(**values)
        for field, value in limpio.items():
            setattr(product, field, value)

        if product.content_hash() != hash_antes and product.estado == ESTADO_ARCHIVADO:
            product.cambios_pendientes = True
        product.actualizado_en = self._now()
        self.repository.update(product)
        self._invalidate_showcase()
        after = self._snapshot(product)
        self._record(
            product,
            accion="editar",
            actor=actor,
            cambios={
                "campos": [key for key in before if before[key] != after[key]],
                "antes": before,
                "despues": after,
            },
        )
        return product

    # --------------------------------------------------------------- FUN-23
    def submit_review(self, product_id: str, *, actor: Actor) -> Product:
        product = self._get(product_id)
        self._ensure_owner(product, actor)
        ensure_transition(
            product.estado, ESTADOS_ENVIABLES_A_REVISION, "enviar a revisión"
        )
        ensure_min_images(product.medios, minimo=self.settings.product_min_images)
        return self._transition(
            product,
            nuevo_estado=ESTADO_EN_REVISION,
            actor=actor,
            accion="enviar_revision",
        )

    # --------------------------------------------------------------- FUN-24
    def archive(self, product_id: str, *, actor: Actor) -> Product:
        product = self._get(product_id)
        self._ensure_owner(product, actor)
        ensure_transition(product.estado, ESTADOS_ARCHIVABLES, "archivar")
        return self._transition(
            product,
            nuevo_estado=ESTADO_ARCHIVADO,
            actor=actor,
            accion="archivar",
            cambios_extra={
                "licenciasVigentes": self.repository.count_active_licenses(product.id)
            },
        )

    # --------------------------------------------------------------- FUN-25
    def reactivate(self, product_id: str, *, actor: Actor) -> Product:
        product = self._get(product_id)
        self._ensure_owner(product, actor)
        ensure_transition(product.estado, frozenset({ESTADO_ARCHIVADO}), "reactivar")

        hubo_cambios = product.cambios_pendientes or (
            product.archivo_hash is not None
            and product.content_hash() != product.archivo_hash
        )
        destino = ESTADO_EN_REVISION if hubo_cambios else ESTADO_PUBLICADO
        return self._transition(
            product,
            nuevo_estado=destino,
            actor=actor,
            accion="reactivar",
            cambios_extra={"huboCambios": hubo_cambios},
        )

    # ------------------------------------------------------------- consulta
    def list_showcase(self) -> list[Product]:
        return self.repository.list_showcase()

    def get(self, product_id: str) -> Product:
        return self._get(product_id)

    def category_name(self, category_id: str | None) -> str | None:
        if not category_id:
            return None
        category = self.category_repository.get(category_id)
        return category.nombre if category else category_id

    # ------------------------------------------------------ HU-10 (FUN-28/29)
    def search(
        self,
        *,
        q: str | None = None,
        categoria: str | None = None,
        edad: int | None = None,
        precio_min: int | None = None,
        precio_max: int | None = None,
        orden: str | None = None,
        pagina: int = 1,
        tamanio_pagina: int | None = None,
    ) -> tuple[list[Product], int, ProductQuery]:
        """Busca publicados; devuelve página, total y la consulta normalizada."""

        active_categories = frozenset(
            category.id for category in self.category_repository.list_active()
        )
        consulta = validate_query(
            q=q,
            categoria=categoria,
            edad=edad,
            precio_min=precio_min,
            precio_max=precio_max,
            orden=orden,
            pagina=pagina,
            tamanio_pagina=(
                self.settings.catalog_default_page_size
                if tamanio_pagina is None
                else tamanio_pagina
            ),
            max_age=self.settings.product_max_age,
            min_price=self.settings.product_min_price,
            max_page_size=self.settings.catalog_max_page_size,
            known_categories=active_categories,
        )
        items, total = self.repository.search_products(consulta)
        return items, total, consulta

    # ------------------------------------------------------ HU-10 (FUN-30)
    def showcase(self) -> tuple[list[tuple[str, str, list[Product]]], int]:
        """Vitrina agrupada por categoría, con caché por categoría."""

        productos = self.repository.list_showcase()
        por_categoria: dict[str, list[Product]] = {}
        for product in productos:
            category_id = product.categoria_id or (
                product.categorias[0] if product.categorias else ""
            )
            por_categoria.setdefault(category_id, []).append(product)

        categorias = {
            category.id: category for category in self.category_repository.list_active()
        }
        grupos: list[tuple[str, str, list[Product]]] = []
        total = 0
        for category_id, items in por_categoria.items():
            cached = (
                self.showcase_cache.get(category_id) if self.showcase_cache else None
            )
            if cached is not None:
                visibles = cached
            else:
                visibles = items
                if self.showcase_cache:
                    self.showcase_cache.set(category_id, visibles)
            category = categorias.get(category_id)
            nombre = category.nombre if category else (category_id or "Sin categoría")
            grupos.append((category_id, nombre, visibles))
            total += len(visibles)

        grupos.sort(key=lambda grupo: (-grupo[2][0].creado_en.timestamp(), grupo[0]))
        return grupos, total

    # ------------------------------------------------------ HU-10 (FUN-31)
    def get_detail(
        self, product_id: str, *, actor: Actor
    ) -> tuple[Product, dict[str, Any] | None, bool]:
        """Publicado para todos; no publicado solo para autor, admin o licenciado."""

        product = self._get(product_id)
        licencia = self.repository.active_license_for(product.id, actor.id)
        privilegiado = actor.is_admin or actor.id == product.autor_id
        if not product.publicado and not privilegiado and licencia is None:
            raise ProductNotFoundError(
                "El producto no existe o no está publicado.",
                details={"id": product_id},
            )
        return product, licencia, privilegiado

    def active_licenses(self, product_id: str) -> int:
        return self.repository.count_active_licenses(product_id)

    def attach_license(
        self,
        product_id: str,
        *,
        tipo: str = "estandar",
        license_id: str | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Utilidad de integración para otros submódulos (p. ej. HU-15)."""

        self._get(product_id)
        return self.repository.add_license(
            product_id,
            tipo=tipo,
            license_id=license_id,
            actor_id=actor_id,
        )
