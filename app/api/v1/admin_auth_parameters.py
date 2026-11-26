"""Endpoints documentados del submódulo SUB-07: Parametrización (FUN-16)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_actor, get_auth_parameters_service
from app.api.schemas import (
    AuthParameterDetail,
    AuthParametersData,
    AuthParametersHistoryData,
    AuthParametersUpdateRequest,
    AuthParameterVersionItem,
)
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.domain.auth_parameters import PARAMETROS_AUTENTICACION
from app.services.auth_parameters import AuthParametersService

router = APIRouter(
    prefix="/api/v1/admin/auth/parameters",
    tags=["Administración · Parámetros de autenticación"],
)

_ERROR_RESPONSES = {
    400: {
        "description": (
            "Parámetro desconocido, valor fuera de rango/tipo, dependencia incumplida "
            "o módulo distinto de autenticación."
        )
    },
    403: {"description": "El actor no tiene permiso admin.auth.parameters.write."},
    404: {"description": "No existe la versión solicitada en el historial."},
}


def _definiciones(snapshot) -> list[AuthParameterDetail]:
    return [
        AuthParameterDetail(
            **definicion.as_dict(snapshot.value(definicion.codigo))
        )
        for definicion in PARAMETROS_AUTENTICACION
    ]


@router.get(
    "",
    response_model=ApiResponse[AuthParametersData],
    summary="Parámetros vigentes de autenticación (FUN-16 / PRC-16)",
    description=(
        "Devuelve la versión vigente, la fecha de vigencia, el mapa código/valor y el "
        "detalle de cada parámetro con tipo y validación. Requiere rol administrador."
    ),
    responses=_ERROR_RESPONSES,
)
def get_parameters(
    service: AuthParametersService = Depends(get_auth_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[AuthParametersData]:
    service.ensure_admin(actor)
    version = service.current()
    snapshot = service.snapshot()
    return ok(
        "Parámetros de autenticación consultados correctamente.",
        AuthParametersData.from_version(version, _definiciones(snapshot)),
    )


@router.put(
    "",
    response_model=ApiResponse[AuthParametersData],
    summary="Actualizar parámetros de autenticación (FUN-16 / PRC-16)",
    description=(
        "Valida tipo, rango y dependencias antes de escribir. Cada cambio válido crea "
        "una versión inmutable con actor, fecha y valores anteriores, registra auditoría "
        "e invalida la caché por versión. Un valor inválido responde 400 sin modificar "
        "la configuración."
    ),
    responses=_ERROR_RESPONSES,
)
def update_parameters(
    payload: AuthParametersUpdateRequest,
    service: AuthParametersService = Depends(get_auth_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[AuthParametersData]:
    version = service.update(
        actor,
        parametros=payload.parametros,
        modulo=payload.modulo,
        motivo=payload.motivo,
    )
    return ok(
        "Parámetros de autenticación actualizados.",
        AuthParametersData.from_version(version, _definiciones(service.snapshot())),
    )


@router.get(
    "/history",
    response_model=ApiResponse[AuthParametersHistoryData],
    summary="Historial de versiones de autenticación",
    description=(
        "Lista las versiones almacenadas de más reciente a más antigua, con los valores "
        "anteriores y el actor que realizó cada cambio."
    ),
    responses=_ERROR_RESPONSES,
)
def get_history(
    limit: int = Query(default=50, ge=1, le=200, description="Máximo de versiones."),
    service: AuthParametersService = Depends(get_auth_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[AuthParametersHistoryData]:
    service.ensure_admin(actor)
    actual = service.current()
    versiones = service.history(limit=limit)
    return ok(
        "Historial de parámetros consultado correctamente.",
        AuthParametersHistoryData(
            version_actual=actual.version,
            total=len(versiones),
            versiones=[
                AuthParameterVersionItem.from_version(
                    version, actual=version.version == actual.version
                )
                for version in versiones
            ],
        ),
    )


@router.get(
    "/history/{version}",
    response_model=ApiResponse[AuthParameterVersionItem],
    summary="Detalle de una versión del historial",
    responses=_ERROR_RESPONSES,
)
def get_historical_version(
    version: int,
    service: AuthParametersService = Depends(get_auth_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[AuthParameterVersionItem]:
    service.ensure_admin(actor)
    encontrada = service.get_version(version)
    return ok(
        f"Versión {version} de los parámetros consultada correctamente.",
        AuthParameterVersionItem.from_version(
            encontrada, actual=encontrada.version == service.current().version
        ),
    )
