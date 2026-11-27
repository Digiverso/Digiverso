"""Adaptador de compras para HU-18 sin dependencia del módulo Comercio.

El contrato de HU-18 indica que la compra se valida contra Comercio por API
interna. Como todavía no existe ese módulo en el repositorio, este adaptador
resuelve la titularidad desde las licencias vigentes que ya registra Catálogo.
Para conectar el microservicio real basta con otra implementación del mismo
método ``tiene_compra``.
"""

from __future__ import annotations

from typing import Protocol

from app.repository.products import SQLiteProductRepository


class PurchaseGateway(Protocol):
    """Comprobación de compra/licencia del consumidor sobre un producto."""

    def tiene_compra(self, product_id: str, user_id: str) -> bool: ...


class LicensePurchaseGateway:
    """Implementación local basada en ``licencias.vigente = 1``."""

    def __init__(self, product_repository: SQLiteProductRepository) -> None:
        self.product_repository = product_repository

    def tiene_compra(self, product_id: str, user_id: str) -> bool:
        return self.product_repository.active_license_for(product_id, user_id) is not None
