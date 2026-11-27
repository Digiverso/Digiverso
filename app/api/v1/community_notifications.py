"""Bandeja de notificaciones de comunidad (HU-20).

El router se registra desde ``app.api.v1.notifications`` para no modificar el
ensamblaje compartido de ``main.py`` que también cambia en HU-18 y HU-19.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.community_notification_schemas import (
    CommunityNotificationItem,
    CommunityNotificationListData,
)
from app.api.dependencies import get_current_account
from app.core.responses import ApiResponse, ok
from app.domain.auth import Account
from app.repository.auth_repository import auth_repository
from app.repository.community_notifications import (
    CommunityNotificationStore,
    community_notification_store,
)
from app.repository.database import Database
from app.repository.email_repository import build_notification_sender
from app.repository.notifications import notification_repository
from app.repository.products import SQLiteProductRepository
from app.services.community_notifications import (
    CommunityNotificationConsumer,
)

router = APIRouter(tags=["Usuarios · Notificaciones de comunidad"])


def _store(request: Request) -> CommunityNotificationStore:
    actual = getattr(request.app.state, "community_notification_store", None)
    if not isinstance(actual, CommunityNotificationStore):
        actual = community_notification_store
        request.app.state.community_notification_store = actual
    return actual


def get_community_notifications_service(
    request: Request,
) -> CommunityNotificationConsumer:
    """Construye el consumidor con las dependencias ya creadas por la app."""

    existente = getattr(request.app.state, "community_notification_service", None)
    if isinstance(existente, CommunityNotificationConsumer):
        return existente

    settings = request.app.state.settings
    auth_service = getattr(request.app.state, "auth_service", None)
    accounts_repo = getattr(auth_service, "repo", auth_repository)
    product_service = getattr(request.app.state, "product_service", None)
    product_repo = getattr(product_service, "repository", None)
    if product_repo is None:
        product_repo = SQLiteProductRepository(Database(settings.database_path))

    def autor_de(producto_id: str) -> str | None:
        producto = product_repo.get(producto_id)
        return producto.autor_id if producto is not None else None

    servicio = CommunityNotificationConsumer(
        repo=notification_repository,
        settings=settings,
        store=_store(request),
        clock=getattr(auth_service, "clock", None),
        sender=build_notification_sender(settings),
        account_provider=lambda cuenta_id: accounts_repo.obtener_cuenta_por_id(
            cuenta_id
        ),
        product_author_provider=autor_de,
    )
    request.app.state.community_notification_service = servicio
    return servicio


@router.get(
    "/notifications/comunidad",
    response_model=ApiResponse[CommunityNotificationListData],
    status_code=status.HTTP_200_OK,
    summary="Consultar notificaciones de comunidad (FUN-63 / PRC-63)",
    description=(
        "Devuelve las notificaciones de comunidad del usuario autenticado con "
        "emisor, paginación y retención AUT-11. Los canales se validan con AUT-10."
    ),
    responses={
        401: {"description": "Token de acceso ausente, inválido o sin sesión activa."}
    },
)
def consultar_notificaciones_comunidad(
    pagina: int = Query(default=1, ge=1, description="Página (1-based)."),
    tamano: int = Query(default=20, ge=1, le=100, description="Elementos por página."),
    cuenta: Account = Depends(get_current_account),
    service: CommunityNotificationConsumer = Depends(
        get_community_notifications_service
    ),
) -> ApiResponse[CommunityNotificationListData]:
    items, total = service.bandeja(cuenta, pagina=pagina, tamano=tamano)
    return ok(
        "Notificaciones de comunidad consultadas correctamente.",
        CommunityNotificationListData(
            items=[CommunityNotificationItem.from_data(item) for item in items],
            pagina=pagina,
            total=total,
        ),
    )


__all__ = ["get_community_notifications_service", "router"]
