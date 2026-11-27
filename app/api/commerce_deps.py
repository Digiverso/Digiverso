"""Dependencias de Comercio: comprador autenticado, IP y servicio (HU-15)."""

from __future__ import annotations

from fastapi import Header, Request

from app.api.dependencies import get_current_account
from app.core.config import Settings
from app.core.security import ActorTokenManager
from app.domain.actor import Actor
from app.domain.auth import DomainError
from app.domain.exceptions import ConsumerRequiredError, SalesForbiddenError
from app.services.commerce import CommerceService


def get_commerce_service(request: Request) -> CommerceService:
    return request.app.state.commerce_service


def get_commerce_actor(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    x_actor_roles: str | None = Header(default=None, alias="X-Actor-Roles"),
) -> Actor:
    """Resuelve al comprador, sin caer al administrador por defecto.

    Acepta la sesión RS256 de HU-01, el token de actor de HU-03 y, mientras se
    integra la autenticación, `X-Actor-Id` / `X-Actor-Roles`. Sin credencial
    alguna responde `401 CONSUMER_REQUIRED`.
    """

    settings: Settings = request.app.state.settings
    if authorization:
        if not authorization.lower().startswith("bearer "):
            raise ConsumerRequiredError("Se requiere un token de acceso válido.")
        token = authorization.split(None, 1)[1]
        try:
            cuenta = get_current_account(request, authorization)
            return Actor(id=cuenta.id, roles=(cuenta.rol.value,))
        except DomainError:
            actor = ActorTokenManager(
                settings.secret_key, ttl_seconds=settings.actor_token_ttl_seconds
            ).parse(token)
            if actor is None:
                raise ConsumerRequiredError(
                    "El token de acceso no es válido o expiró."
                ) from None
            return actor

    if not x_actor_id or not x_actor_id.strip():
        raise ConsumerRequiredError("Se requiere un comprador autenticado.")
    roles = tuple(
        role.strip() for role in (x_actor_roles or "").split(",") if role.strip()
    )
    return Actor(id=x_actor_id.strip(), roles=roles)


def get_commerce_client_ip(
    request: Request,
    x_forwarded_for: str | None = Header(default=None, alias="X-Forwarded-For"),
) -> str:
    """IP auditada: la del proxy cuando existe, si no la conexión directa."""

    if x_forwarded_for:
        primera = x_forwarded_for.split(",", 1)[0].strip()
        if primera:
            return primera
    return request.client.host if request.client else "desconocida"


def get_producer_actor(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    x_actor_roles: str | None = Header(default=None, alias="X-Actor-Roles"),
) -> Actor:
    actor = get_commerce_actor(
        request,
        authorization=authorization,
        x_actor_id=x_actor_id,
        x_actor_roles=x_actor_roles,
    )
    roles = {str(role).strip().lower() for role in actor.roles}
    if roles.intersection({"productor", "administrador", "commerce.sales.read"}):
        return actor
    raise SalesForbiddenError(
        "No tienes permisos para consultar ventas o liquidaciones.",
        details={"codigo": "SALES_FORBIDDEN", "actorId": actor.id, "roles": list(actor.roles)},
    )
