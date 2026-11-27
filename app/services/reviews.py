"""Casos de uso FUN-54 a FUN-57 del módulo Comunidad (HU-18)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol

from app.cache.ratings import InMemoryRatingCache
from app.core.config import Settings
from app.domain.exceptions import (
    DuplicateReviewError,
    InvalidCatalogQueryError,
    ProductNotFoundError,
    PurchaseRequiredError,
)
from app.domain.product import Product
from app.domain.reviews import (
    Rating,
    Review,
    rating_desde_conteo,
    validar_calificacion,
    validar_texto,
)
from app.repository.products import SQLiteProductRepository
from app.repository.reviews import SQLiteReviewRepository
from app.services.commerce import PurchaseGateway

EVENTO_REVIEW_CREATED = "review.created"


class EventBus(Protocol):
    """Contrato mínimo para publicar eventos de dominio."""

    def publish(self, topic: str, payload: Mapping[str, Any]) -> None: ...


class ShowcaseCache(Protocol):
    def invalidate(self) -> None: ...


class ReviewService:
    """Publica reseñas verificadas y mantiene el promedio cacheado."""

    def __init__(
        self,
        repository: SQLiteReviewRepository,
        product_repository: SQLiteProductRepository,
        purchase_gateway: PurchaseGateway,
        cache: InMemoryRatingCache,
        event_bus: EventBus,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
        showcase_cache: ShowcaseCache | None = None,
    ) -> None:
        self.repository = repository
        self.product_repository = product_repository
        self.purchase_gateway = purchase_gateway
        self.cache = cache
        self.event_bus = event_bus
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.showcase_cache = showcase_cache

    def _product(self, product_id: str) -> Product:
        product = self.product_repository.get(product_id)
        if product is None:
            raise ProductNotFoundError(
                "El producto no existe.", details={"id": product_id}
            )
        return product

    def publish(
        self,
        product_id: str,
        *,
        user_id: str,
        calificacion: object,
        texto: object,
    ) -> Review:
        """FUN-54 / PRC-54: guarda la reseña y publica ``review.created``."""

        self._product(product_id)

        if (
            self.settings.community_require_purchase
            and not self.purchase_gateway.tiene_compra(product_id, user_id)
        ):
            raise PurchaseRequiredError(
                "Debes comprar o tener licencia del producto para reseñarlo (COMU-04).",
                details={
                    "regla": "COMU-04",
                    "productoId": product_id,
                    "usuarioId": user_id,
                },
            )

        if self.settings.community_unique_review and self.repository.exists_for(
            product_id, user_id
        ):
            raise DuplicateReviewError(
                "Ya publicaste una reseña para este producto (COMU-03).",
                details={
                    "regla": "COMU-03",
                    "productoId": product_id,
                    "usuarioId": user_id,
                },
            )

        valor = validar_calificacion(
            calificacion,
            minimo=self.settings.community_rating_min,
            maximo=self.settings.community_rating_max,
        )
        limpio = validar_texto(
            texto,
            minimo=self.settings.community_text_min_length,
            maximo=self.settings.community_text_max_length,
        )
        ahora = self.clock()
        review = Review(
            id="",
            product_id=product_id,
            user_id=user_id,
            calificacion=valor,
            texto=limpio,
            fecha=ahora,
        )
        guardada = self.repository.create(review)
        promedio = self._refresh(product_id, ahora)
        self.event_bus.publish(
            EVENTO_REVIEW_CREATED,
            {
                "id": guardada.id,
                "productId": product_id,
                "userId": user_id,
                "calificacion": valor,
                "texto": limpio,
                "fecha": ahora.astimezone(timezone.utc).isoformat(),
                "promedio": promedio.promedio,
                "total": promedio.total,
            },
        )
        return guardada

    def list_reviews(
        self, product_id: str, *, pagina: int = 1, tamanio_pagina: int | None = None
    ) -> tuple[list[Review], int, int]:
        """FUN-55 / PRC-55: reseñas visibles paginadas."""

        self._product(product_id)
        page = pagina if pagina is not None and pagina >= 1 else 1
        size = (
            self.settings.community_default_page_size
            if tamanio_pagina is None
            else tamanio_pagina
        )
        if size < 1 or size > self.settings.community_max_page_size:
            raise InvalidCatalogQueryError(
                "El tamaño de página está fuera de rango.",
                details={"tamanioPagina": tamanio_pagina or size},
            )
        reviews, total = self.repository.list_visible(
            product_id, page=page, page_size=size
        )
        return reviews, total, size

    def hide_review(self, product_id: str, review_id: str) -> None:
        """Integración con Control de publicaciones: retiro lógico y recálculo."""

        self.repository.hide(review_id)
        self._refresh(product_id, self.clock())

    def rating(self, product_id: str) -> Rating:
        """FUN-56/57: promedio, total y distribución con caché por producto."""

        self._product(product_id)
        cached = self.cache.get(product_id)
        if cached is not None:
            return cached
        conteo = self.repository.aggregate(product_id)
        calculado = rating_desde_conteo(
            conteo,
            minimo=self.settings.community_rating_min,
            maximo=self.settings.community_rating_max,
        )
        self.cache.set(product_id, calculado)
        return calculado

    def _refresh(self, product_id: str, fecha: datetime) -> Rating:
        """Recalcula la agregación y la propaga al producto y la vitrina."""

        self.cache.invalidate(product_id)
        calculado = self.rating(product_id)
        product = self._product(product_id)
        if product.calificacion != calculado.promedio:
            self.product_repository.update(
                replace(
                    product,
                    calificacion=calculado.promedio,
                    actualizado_en=fecha,
                )
            )
        if self.showcase_cache is not None:
            self.showcase_cache.invalidate()
        return calculado
