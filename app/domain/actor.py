"""Actor que ejecuta una operación de catálogo.

Este módulo es un puente temporal: cuando el módulo de autenticación/autorización
(HU-01, HU-02, HU-04) esté disponible, ``Actor`` debe construirse desde el token
verificado en lugar de las cabeceras HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

ADMIN_ROLE = "administrador"
ADMIN_SCOPE = "catalog.category.write"
PRODUCTOR_ROLE = "productor"
PRODUCT_SCOPE = "catalog.product.write"


@dataclass(frozen=True)
class Actor:
    id: str
    roles: tuple[str, ...] = ()

    @property
    def is_admin(self) -> bool:
        return ADMIN_ROLE in self.roles or ADMIN_SCOPE in self.roles

    @property
    def is_producer(self) -> bool:
        return self.is_admin or PRODUCTOR_ROLE in self.roles or PRODUCT_SCOPE in self.roles
