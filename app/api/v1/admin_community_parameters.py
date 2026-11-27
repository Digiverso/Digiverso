"""Endpoints documentados del SUB-28: Parametrización de comunidad (FUN-64)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.api.community_parameter_schemas import (
    CommunityParameterDetail,
    CommunityParametersData,
    CommunityParametersHistoryData,
    CommunityParametersUpdateRequest,
    CommunityParameterVersionItem,
)
from app.api.deps import get_actor
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.domain.community_parameters import PARAMETROS_COMUNIDAD
from app.services.community_parameters import CommunityParametersService

router = APIRouter(
    prefix="/api/v1/admin/community/parameters",
    tags=["Administración · Parámetros de comunidad"],
)

_ERROR_RESPONSES = {
    400: {
        "description": (
            "Parámetro desconocido, valor fuera de rango/tipo, dependencia incumplida "
            "o módulo distinto de comunidad."
        )
    },
    403: {"description": "El actor no tiene permiso admin.community.parameters.write."},
    404: {"description": "No existe la versión solicitada en el historial."},
}


def get_community_parameters_service(request: Request) -> CommunityParametersService:
    """Dependencia local: evita tocar el módulo compartido de dependencias."""

    return request.app.state.community_parameters_service


def _definiciones(service: CommunityParametersService) -> list[CommunityParameterDetail]:
    snapshot = service.snapshot()
    return [
        CommunityParameterDetail(**definicion.as_dict(snapshot.value(definicion.codigo)))
        for definicion in PARAMETROS_COMUNIDAD
    ]


@router.get(
    "",
    response_model=ApiResponse[CommunityParametersData],
    summary="Parámetros vigentes de comunidad (FUN-64 / PRC-64)",
    description=(
        "Devuelve la versión vigente, la fecha de vigencia, el mapa código/valor y "
        "el detalle de cada parámetro COMU con tipo, rango y validaciones. "
        "Requiere rol administrador o el alcance admin.community.parameters.write."
    ),
    responses=_ERROR_RESPONSES,
)
def get_parameters(
    service: CommunityParametersService = Depends(get_community_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CommunityParametersData]:
    service.ensure_admin(actor)
    version = service.current()
    return ok(
        "Parámetros de comunidad consultados correctamente.",
        CommunityParametersData.from_version(version, _definiciones(service)),
    )


@router.put(
    "",
    response_model=ApiResponse[CommunityParametersData],
    summary="Actualizar parámetros de comunidad (FUN-64 / PRC-64)",
    description=(
        "Valida tipo, rango y dependencias antes de escribir. Cada cambio válido crea "
        "una versión inmutable con actor, fecha y valores anteriores, registra auditoría "
        "e invalida la caché por versión. Un valor inválido responde 400 sin modificar "
        "la configuración. Solo parámetros COMU: AUT-xx, CAT-xx y COM-xx se rechazan."
    ),
    responses=_ERROR_RESPONSES,
)
def update_parameters(
    payload: CommunityParametersUpdateRequest,
    service: CommunityParametersService = Depends(get_community_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CommunityParametersData]:
    version = service.update(
        actor,
        parametros=payload.parametros,
        modulo=payload.modulo,
        motivo=payload.motivo,
    )
    return ok(
        "Parámetros de comunidad actualizados.",
        CommunityParametersData.from_version(version, _definiciones(service)),
    )


@router.get(
    "/history",
    response_model=ApiResponse[CommunityParametersHistoryData],
    summary="Historial inmutable de versiones de comunidad",
    description=(
        "Lista las versiones almacenadas de más reciente a más antigua, con los valores "
        "anteriores, el actor y el motivo de cada cambio."
    ),
    responses=_ERROR_RESPONSES,
)
def get_history(
    limit: int = Query(default=50, ge=1, le=200, description="Máximo de versiones."),
    service: CommunityParametersService = Depends(get_community_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CommunityParametersHistoryData]:
    service.ensure_admin(actor)
    actual = service.current()
    versiones = service.history(limit=limit)
    return ok(
        "Historial de parámetros de comunidad consultado correctamente.",
        CommunityParametersHistoryData(
            version_actual=actual.version,
            total=len(versiones),
            versiones=[
                CommunityParameterVersionItem.from_version(
                    version, actual=version.version == actual.version
                )
                for version in versiones
            ],
        ),
    )


@router.get(
    "/history/{version}",
    response_model=ApiResponse[CommunityParameterVersionItem],
    summary="Detalle de una versión del historial de comunidad",
    responses=_ERROR_RESPONSES,
)
def get_historical_version(
    version: int,
    service: CommunityParametersService = Depends(get_community_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CommunityParameterVersionItem]:
    service.ensure_admin(actor)
    encontrada = service.get_version(version)
    return ok(
        f"Versión {version} de los parámetros de comunidad consultada correctamente.",
        CommunityParameterVersionItem.from_version(
            encontrada, actual=encontrada.version == service.current().version
        ),
    )
