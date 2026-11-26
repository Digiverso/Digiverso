"""Endpoints documentados de la HU-05: preferencias, bandeja y lectura."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import (
    get_client_ip,
    get_current_account,
    get_notifications_service,
)
from app.api.schemas import (
    NotificationItem,
    NotificationListData,
    NotificationPreferencesData,
    NotificationPreferencesRequest,
    NotificationReadData,
)
from app.core.responses import ApiResponse, ok
from app.domain.auth import Account
from app.services.notifications import NotificationService

router = APIRouter(
    prefix="/api/v1/users/me",
    tags=["Usuarios · Notificaciones"],
)

_ERROR_RESPONSES = {
    400: {"description": "Canal o tipo no permitido por AUT-10."},
    401: {"description": "Token de acceso ausente, inválido o sin sesión activa."},
    404: {"description": "No existe la notificación solicitada para este usuario."},
}


@router.put(
    "/notification-preferences",
    response_model=ApiResponse[NotificationPreferencesData],
    status_code=status.HTTP_200_OK,
    summary="Configurar preferencias de notificación (FUN-13 / PRC-13)",
    description=(
        "Guarda los canales y tipos activos validados contra AUT-10. Las "
        "notificaciones críticas de seguridad no se silencian."
    ),
    responses=_ERROR_RESPONSES,
)
def configurar_preferencias(
    payload: NotificationPreferencesRequest,
    cuenta: Account = Depends(get_current_account),
    service: NotificationService = Depends(get_notifications_service),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[NotificationPreferencesData]:
    preferencias = service.configurar_preferencias(
        cuenta,
        canales=payload.canales,
        tipos=payload.tipos,
        ip=ip,
    )
    return ok(
        "Preferencias de notificación actualizadas.",
        NotificationPreferencesData(
            canales=[canal.value for canal in preferencias.canales],
            tipos=[tipo.value for tipo in preferencias.tipos],
        ),
    )


@router.get(
    "/notifications",
    response_model=ApiResponse[NotificationListData],
    status_code=status.HTTP_200_OK,
    summary="Consultar bandeja de notificaciones (FUN-14 / PRC-14)",
    description=(
        "Devuelve solo las notificaciones del usuario autenticado, ordenadas por "
        "fecha descendente y paginadas. Aplica retención AUT-11."
    ),
    responses=_ERROR_RESPONSES,
)
def consultar_notificaciones(
    pagina: int = Query(default=1, ge=1, description="Página (1-based)."),
    tamano: int = Query(default=20, ge=1, le=100, description="Elementos por página."),
    cuenta: Account = Depends(get_current_account),
    service: NotificationService = Depends(get_notifications_service),
) -> ApiResponse[NotificationListData]:
    items, total = service.bandeja(cuenta, pagina=pagina, tamano=tamano)
    return ok(
        "Notificaciones consultadas correctamente.",
        NotificationListData(
            items=[NotificationItem.from_notification(item) for item in items],
            pagina=pagina,
            total=total,
        ),
    )


@router.patch(
    "/notifications/{id}/read",
    response_model=ApiResponse[NotificationReadData],
    status_code=status.HTTP_200_OK,
    summary="Marcar notificación como leída (FUN-15 / PRC-15)",
    description=(
        "Valida la pertenencia de la notificación al usuario autenticado y es "
        "idempotente. Una notificación ajena responde 404 sin revelar datos."
    ),
    responses=_ERROR_RESPONSES,
)
def marcar_como_leida(
    id: str,
    cuenta: Account = Depends(get_current_account),
    service: NotificationService = Depends(get_notifications_service),
) -> ApiResponse[NotificationReadData]:
    notificacion = service.marcar_leida(cuenta, id)
    return ok(
        "Notificación marcada como leída.",
        NotificationReadData(id=notificacion.id, leida=notificacion.leida),
    )
