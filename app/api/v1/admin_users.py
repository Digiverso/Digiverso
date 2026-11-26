"""Endpoints documentados de la HU-04: asignación de roles (FUN-09)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    get_admin_principal,
    get_client_ip,
    get_roles_permissions_service,
)
from app.api.schemas import RoleAssignmentData, RoleAssignmentRequest
from app.core.responses import ApiResponse, ok
from app.services.roles_permissions import Principal, RolesPermissionsService

router = APIRouter(
    prefix="/api/v1/admin/users",
    tags=["Administración · Usuarios y roles"],
)

_ERROR_RESPONSES = {
    400: {"description": "El rol no está permitido por AUT-09."},
    401: {"description": "Falta una credencial válida."},
    403: {"description": "El principal no tiene permiso admin.users.roles.write."},
    404: {"description": "No existe la cuenta indicada."},
    409: {"description": "No se puede degradar al último administrador."},
}


@router.post(
    "/{id}/roles",
    response_model=ApiResponse[RoleAssignmentData],
    status_code=status.HTTP_200_OK,
    summary="Asignar rol a un usuario (FUN-09 / PRC-09)",
    description=(
        "Solo un administrador puede asignar roles. El rol debe estar permitido por "
        "AUT-09, no se puede degradar al último administrador, la operación es "
        "idempotente y cada cambio queda auditado."
    ),
    responses=_ERROR_RESPONSES,
)
def asignar_rol(
    id: str,
    payload: RoleAssignmentRequest,
    service: RolesPermissionsService = Depends(get_roles_permissions_service),
    principal: Principal = Depends(get_admin_principal),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[RoleAssignmentData]:
    asignacion = service.asignar_rol(
        cuenta_id=id,
        rol=payload.rol,
        actor=principal,
        ip=ip,
    )
    return ok(
        "Rol asignado correctamente.",
        RoleAssignmentData(
            usuario_id=asignacion.usuario_id,
            rol_anterior=asignacion.rol_anterior,
            rol_nuevo=asignacion.rol_nuevo,
        ),
    )
