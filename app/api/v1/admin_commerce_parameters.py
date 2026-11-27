"""Endpoints documentados del SUB-21: Parametrización de comercio (FUN-53)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.api.commerce_parameter_schemas import (
    CommerceParameterDetail,
    CommerceParametersData,
    CommerceParametersHistoryData,
    CommerceParametersUpdateRequest,
    CommerceParameterVersionItem,
)
from app.api.deps import get_actor
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.domain.commerce_parameters import PARAMETROS_COMERCIO
from app.services.commerce_parameters import CommerceParametersService

router = APIRouter(
    prefix="/api/v1/admin/commerce/parameters",
    tags=["Administración · Parámetros de comercio"],
)

_ERROR_RESPONSES = {
    400: {
        "description": (
            "Parámetro desconocido, valor fuera de rango/tipo, comisión más neto "
            "distintos de 100 % o módulo distinto de comercio."
        )
    },
    403: {"description": "El actor no tiene permiso admin.commerce.parameters.write."},
    404: {"description": "No existe la versión solicitada en el historial."},
}


def get_commerce_parameters_service(
    request: Request,
) -> CommerceParametersService:
    """Dependencia local: evita tocar el módulo compartido de dependencias."""

    return request.app.state.commerce_parameters_service


def _definiciones(
    service: CommerceParametersService,
) -> list[CommerceParameterDetail]:
    snapshot = service.snapshot()
    return [
        CommerceParameterDetail(
            **definicion.as_dict(snapshot.value(definicion.codigo))
        )
        for definicion in PARAMETROS_COMERCIO
    ]


@router.get(
    "",
    response_model=ApiResponse[CommerceParametersData],
    summary="Parámetros vigentes de comercio (FUN-53 / PRC-53)",
    description=(
        "Devuelve la versión vigente, la fecha de vigencia, el mapa código/valor y "
        "el detalle de cada parámetro COM con tipo, rango y validaciones. "
        "Requiere rol administrador o el alcance admin.commerce.parameters.write."
    ),
    responses=_ERROR_RESPONSES,
)
def get_parameters(
    service: CommerceParametersService = Depends(get_commerce_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CommerceParametersData]:
    service.ensure_admin(actor)
    version = service.current()
    return ok(
        "Parámetros de comercio consultados correctamente.",
        CommerceParametersData.from_version(version, _definiciones(service)),
    )


@router.put(
    "",
    response_model=ApiResponse[CommerceParametersData],
    summary="Actualizar parámetros de comercio (FUN-53 / PRC-53)",
    description=(
        "Valida tipo, rango y que COM-01 más COM-02 sumen 100 % antes de escribir. "
        "Cada cambio válido crea una versión inmutable con actor, fecha y valores "
        "anteriores, registra auditoría e invalida la caché por versión. Un valor "
        "inválido responde 400 sin modificar la configuración. Solo parámetros COM: "
        "AUT-xx, CAT-xx y COMU-xx se rechazan."
    ),
    responses=_ERROR_RESPONSES,
)
def update_parameters(
    payload: CommerceParametersUpdateRequest,
    service: CommerceParametersService = Depends(get_commerce_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CommerceParametersData]:
    version = service.update(
        actor,
        parametros=payload.parametros,
        modulo=payload.modulo,
        motivo=payload.motivo,
    )
    return ok(
        "Parámetros de comercio actualizados.",
        CommerceParametersData.from_version(version, _definiciones(service)),
    )


@router.get(
    "/history",
    response_model=ApiResponse[CommerceParametersHistoryData],
    summary="Historial inmutable de versiones de comercio",
    description=(
        "Lista las versiones almacenadas de más reciente a más antigua, con los "
        "valores anteriores, el actor y el motivo de cada cambio."
    ),
    responses=_ERROR_RESPONSES,
)
def get_history(
    limit: int = Query(default=50, ge=1, le=200, description="Máximo de versiones."),
    service: CommerceParametersService = Depends(get_commerce_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CommerceParametersHistoryData]:
    service.ensure_admin(actor)
    actual = service.current()
    versiones = service.history(limit=limit)
    return ok(
        "Historial de parámetros de comercio consultado correctamente.",
        CommerceParametersHistoryData(
            version_actual=actual.version,
            total=len(versiones),
            versiones=[
                CommerceParameterVersionItem.from_version(
                    version, actual=version.version == actual.version
                )
                for version in versiones
            ],
        ),
    )


@router.get(
    "/history/{version}",
    response_model=ApiResponse[CommerceParameterVersionItem],
    summary="Detalle de una versión del historial de comercio",
    responses=_ERROR_RESPONSES,
)
def get_historical_version(
    version: int,
    service: CommerceParametersService = Depends(get_commerce_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CommerceParameterVersionItem]:
    service.ensure_admin(actor)
    encontrada = service.get_version(version)
    return ok(
        f"Versión {version} de los parámetros de comercio consultada correctamente.",
        CommerceParameterVersionItem.from_version(
            encontrada, actual=encontrada.version == service.current().version
        ),
    )
