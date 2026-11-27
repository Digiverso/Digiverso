"""Dependencias compartidas de la API de catálogo."""

from __future__ import annotations

from fastapi import Header, Request

from app.core.config import Settings
from app.core.security import ActorTokenManager
from app.domain.actor import ADMIN_ROLE, Actor
from app.domain.exceptions import ForbiddenError
from app.services.auth_parameters import AuthParametersService
from app.services.categories import CategoryService
from app.services.media import MediaService
from app.services.products import ProductService
from app.services.reviews import ReviewService


def get_auth_parameters_service(request: Request) -> AuthParametersService:
    return request.app.state.auth_parameters_service


def get_category_service(request: Request) -> CategoryService:
    return request.app.state.category_service


def get_product_service(request: Request) -> ProductService:
    return request.app.state.product_service


def get_media_service(request: Request) -> MediaService:
    return request.app.state.media_service


def get_review_service(request: Request) -> ReviewService:
    return request.app.state.review_service


def get_actor(
    request: Request,
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    x_actor_roles: str | None = Header(default=None, alias="X-Actor-Roles"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Actor:
    """Construye el actor de la operación.

    Si llega ``Authorization: Bearer <token>`` se verifica la firma del token y
    el autor sale de ``sub``. Hasta que HU-01/HU-04 emitan tokens de acceso, las
    cabeceras ``X-Actor-Id`` y ``X-Actor-Roles`` permiten simular al productor.
    Sin ninguna de ellas y fuera de producción se usa el administrador por
    defecto, de modo que el flujo documentado de las HU siga siendo válido.
    """

    settings: Settings = request.app.state.settings
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(None, 1)[1]
        manager = ActorTokenManager(
            settings.secret_key, ttl_seconds=settings.actor_token_ttl_seconds
        )
        actor = manager.parse(token)
        if actor is None:
            raise ForbiddenError("El token de actor es inválido o expiró.")
        return actor

    if x_actor_id is None:
        if settings.require_explicit_actor:
            raise ForbiddenError("Se requiere un actor autenticado para esta operación.")
        return Actor(id=settings.default_actor_id, roles=(ADMIN_ROLE,))

    roles = tuple(
        role.strip() for role in (x_actor_roles or "").split(",") if role.strip()
    )
    return Actor(id=x_actor_id, roles=roles)
