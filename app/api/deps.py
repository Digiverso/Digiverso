"""Dependencias compartidas de la API de categorías."""

from __future__ import annotations

from fastapi import Header, Request

from app.core.config import Settings
from app.domain.actor import ADMIN_ROLE, Actor
from app.domain.exceptions import ForbiddenError
from app.services.categories import CategoryService


def get_category_service(request: Request) -> CategoryService:
    return request.app.state.category_service


def get_actor(
    request: Request,
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    x_actor_roles: str | None = Header(default=None, alias="X-Actor-Roles"),
) -> Actor:
    """Construye el actor de la operación.

    Hasta que el módulo de autenticación esté integrado, las cabeceras
    ``X-Actor-Id`` y ``X-Actor-Roles`` permiten simular al administrador. Si no
    se envían y el entorno no es productivo se usa un administrador por
    defecto, de modo que el flujo documentado de las HU siga siendo válido.
    """

    settings: Settings = request.app.state.settings
    if x_actor_id is None:
        if settings.require_explicit_actor:
            raise ForbiddenError("Se requiere un actor autenticado para esta operación.")
        return Actor(id=settings.default_actor_id, roles=(ADMIN_ROLE,))

    roles = tuple(
        role.strip() for role in (x_actor_roles or "").split(",") if role.strip()
    )
    return Actor(id=x_actor_id, roles=roles)
