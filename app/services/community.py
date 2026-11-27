"""Casos de uso FUN-58 a FUN-62 del módulo Comunidad (HU-19)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Protocol, Sequence

from app.cache.community_feed import CommunityFeedCache
from app.domain.community import (
    CommunitySettings,
    RecommendationScore,
    UserNotFoundError,
    normalize_interests,
    order_recommendations,
    score_recommendation,
    validate_follow,
    validate_pagination,
)
from app.domain.product import ESTADO_PUBLICADO, Product
from app.repository.categories import SQLiteCategoryRepository
from app.repository.community import SQLiteCommunityRepository
from app.repository.products import SQLiteProductRepository


class PurchaseGateway(Protocol):
    """Contrato mínimo para consultar a Comercio si el usuario compró un producto."""

    def tiene_compra(self, product_id: str, user_id: str) -> bool: ...


class LicensePurchaseGateway:
    """Adaptador local sobre las licencias vigentes de Catálogo.

    Cuando el módulo Comercio exponga su API interna basta con sustituir este
    adaptador; el servicio de recomendaciones no cambia.
    """

    def __init__(self, product_repository: SQLiteProductRepository) -> None:
        self.product_repository = product_repository

    def tiene_compra(self, product_id: str, user_id: str) -> bool:
        return self.product_repository.active_license_for(product_id, user_id) is not None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class CommunityService:
    """Orquesta seguimiento, feed, intereses y recomendaciones."""

    def __init__(
        self,
        repository: SQLiteCommunityRepository,
        product_repository: SQLiteProductRepository,
        category_repository: SQLiteCategoryRepository,
        account_provider: Callable[[str], Any],
        cache: CommunityFeedCache,
        settings: CommunitySettings,
        clock: Callable[[], datetime] | None = None,
        purchase_gateway: PurchaseGateway | None = None,
    ) -> None:
        self.repository = repository
        self.product_repository = product_repository
        self.category_repository = category_repository
        self.account_provider = account_provider
        self.cache = cache
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.purchase_gateway = purchase_gateway or LicensePurchaseGateway(
            product_repository
        )

    # --------------------------------------------------------------- helpers
    def _now(self) -> datetime:
        return self.clock()

    def _ensure_user(self, usuario_id: str) -> None:
        if self.account_provider(usuario_id) is None:
            raise UserNotFoundError(
                "El usuario indicado no existe.",
                details={"regla": "USER_NOT_FOUND", "usuarioId": usuario_id},
            )

    def _published(self) -> list[Product]:
        return [
            producto
            for producto in self.product_repository.list_showcase()
            if producto.estado == ESTADO_PUBLICADO and producto.activo
        ]

    @staticmethod
    def _product_signature(productos: Sequence[Product]) -> tuple[object, ...]:
        return tuple(
            (producto.id, producto.actualizado_en.isoformat()) for producto in productos
        )

    def _invalidate(self, *usuarios: str) -> None:
        for usuario in usuarios:
            self.cache.invalidate(usuario)

    # -------------------------------------------------- FUN-58 / FUN-59
    def follow(self, seguidor_id: str, seguido_id: str) -> dict[str, Any]:
        # El auto-seguimiento se rechaza en dominio antes de consultar la cuenta:
        # es una regla de negocio, no depende de que el actor esté registrado.
        validate_follow(
            seguidor_id,
            seguido_id,
            self.repository.count_following(seguidor_id),
            self.settings,
            ya_sigue=self.repository.is_following(seguidor_id, seguido_id),
        )
        self._ensure_user(seguido_id)
        fecha = self._now()
        self.repository.follow(seguidor_id, seguido_id, fecha)
        datos_seguidor = self.repository.recompute_stats(seguidor_id, fecha)
        datos_seguido = self.repository.recompute_stats(seguido_id, fecha)
        self._invalidate(seguidor_id, seguido_id)
        return {
            "seguidorId": seguidor_id,
            "seguidoId": seguido_id,
            "fecha": _iso(fecha),
            "totalSiguiendo": datos_seguidor["siguiendo"],
            "totalSeguidores": datos_seguido["seguidores"],
        }

    def unfollow(self, seguidor_id: str, seguido_id: str) -> dict[str, Any]:
        self._ensure_user(seguido_id)
        eliminado = self.repository.unfollow(seguidor_id, seguido_id)
        fecha = self._now()
        datos_seguidor = self.repository.recompute_stats(seguidor_id, fecha)
        datos_seguido = self.repository.recompute_stats(seguido_id, fecha)
        self._invalidate(seguidor_id, seguido_id)
        return {
            "seguidorId": seguidor_id,
            "seguidoId": seguido_id,
            "eliminado": eliminado,
            "totalSiguiendo": datos_seguidor["siguiendo"],
            "totalSeguidores": datos_seguido["seguidores"],
        }

    # --------------------------------------------------------- FUN-60
    def following_feed(
        self, usuario_id: str, pagina: int, tamanio_pagina: int
    ) -> dict[str, Any]:
        pagina, tamanio_pagina = validate_pagination(
            pagina, tamanio_pagina, self.settings
        )
        seguidos = self.repository.followed_ids(usuario_id)
        publicados = [
            producto
            for producto in self._published()
            if producto.autor_id in seguidos
        ]
        firma = (tuple(seguidos), self._product_signature(publicados))

        items = self.cache.get_feed(usuario_id, firma)
        if items is None:
            items = [self._feed_item(producto) for producto in publicados]
            self.cache.set_feed(usuario_id, firma, items)

        inicio = (pagina - 1) * tamanio_pagina
        return {
            "items": items[inicio : inicio + tamanio_pagina],
            "total": len(items),
            "pagina": pagina,
            "tamanioPagina": tamanio_pagina,
        }

    @staticmethod
    def _feed_item(producto: Product) -> dict[str, Any]:
        return {
            "productId": producto.id,
            "nombre": producto.nombre,
            "autor": producto.autor_nombre,
            "precio": producto.precio,
            "moneda": producto.moneda,
            "fecha": _iso(producto.estado_desde),
            "categoria": producto.categoria_id,
            "miniatura": next(
                (
                    medio.url
                    for medio in producto.medios
                    if medio.estado == "activo" and medio.tipo == "imagen"
                ),
                None,
            ),
        }

    # --------------------------------------------------------- FUN-61
    def set_interests(
        self, usuario_id: str, categorias: Sequence[str]
    ) -> dict[str, Any]:
        activas = {
            categoria.id
            for categoria in self.category_repository.list_active()
        }
        limpias = normalize_interests(categorias, activas, self.settings)
        self.repository.replace_interests(usuario_id, list(limpias))
        self._invalidate(usuario_id)
        return {
            "categorias": list(limpias),
            "total": len(limpias),
            "maximo": self.settings.max_interests,
        }

    # --------------------------------------------------------- FUN-62
    def recommendations(self, usuario_id: str) -> dict[str, Any]:
        intereses = self.repository.interests(usuario_id)
        comprados = set(self.repository.purchased_ids(usuario_id))
        publicados = self._published()
        firma = (
            tuple(intereses),
            tuple(comprados),
            self._product_signature(publicados),
        )

        items = self.cache.get_recommendations(usuario_id, firma)
        if items is None:
            nombres = {
                categoria.id: categoria.nombre
                for categoria in self.category_repository.list_active()
            }
            candidatos: list[RecommendationScore] = []
            for producto in publicados:
                if producto.autor_id == usuario_id or producto.id in comprados:
                    continue
                if self.purchase_gateway.tiene_compra(producto.id, usuario_id):
                    continue
                total_compras = sum(
                    1
                    for licencia in self.product_repository.list_licenses(producto.id)
                    if licencia["vigente"]
                )
                candidatos.append(
                    score_recommendation(
                        producto,
                        intereses,
                        total_compras,
                        ahora=self._now(),
                        settings=self.settings,
                        nombres_categorias=nombres,
                    )
                )
            items = [
                self._recommendation_item(candidato, nombres)
                for candidato in order_recommendations(candidatos)[
                    : self.settings.max_recommendations
                ]
            ]
            self.cache.set_recommendations(usuario_id, firma, items)

        return {
            "items": items,
            "total": len(items),
            "limite": self.settings.max_recommendations,
            "orden": "puntuacion_desc,fecha_desc,id_asc",
        }

    @staticmethod
    def _recommendation_item(
        candidato: RecommendationScore, nombres: dict[str, str]
    ) -> dict[str, Any]:
        producto = candidato.producto
        categoria = producto.categorias[0] if producto.categorias else producto.categoria_id
        return {
            "productId": producto.id,
            "nombre": producto.nombre,
            "autor": producto.autor_nombre,
            "precio": producto.precio,
            "moneda": producto.moneda,
            "categoria": nombres.get(categoria, categoria),
            "fecha": _iso(producto.estado_desde),
            "motivo": candidato.motivo,
            "puntuacion": candidato.puntuacion,
        }
