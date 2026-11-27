"""Endpoints documentados del SUB-14: Parametrización del catálogo (FUN-39)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.api.catalog_parameter_schemas import (
    CatalogParameterDetail,
    CatalogParametersData,
    CatalogParametersHistoryData,
    CatalogParametersUpdateRequest,
    CatalogParameterVersionItem,
)
from app.api.deps import get_actor
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.domain.catalog_parameters import PARAMETROS_CATALOGO
from app.services.catalog_parameters import CatalogParametersService

router = APIRouter(
    prefix="/api/v1/admin/catalog/parameters",
    tags=["Administración · Parámetros del catálogo"],
)

_ERROR_RESPONSES = {
    400: {
        "description": (
            "Parámetro desconocido, valor fuera de rango/tipo, dependencia incumplida "
            "o módulo distinto de catálogo."
        )
    },
    403: {"description": "El actor no tiene permiso admin.catalog.parameters.write."},
    404: {"description": "No existe la versión solicitada en el historial."},
}


def get_catalog_parameters_service(request: Request) -> CatalogParametersService:
    """Dependencia local: evita tocar el módulo compartido de dependencias."""

    return request.app.state.catalog_parameters_service


def _definiciones(service: CatalogParametersService) -> list[CatalogParameterDetail]:
    snapshot = service.snapshot()
    return [
        CatalogParameterDetail(**definicion.as_dict(snapshot.value(definicion.codigo)))
        for definicion in PARAMETROS_CATALOGO
    ]


@router.get(
    "",
    response_model=ApiResponse[CatalogParametersData],
    summary="Parámetros vigentes del catálogo (FUN-39 / PRC-39)",
    description=(
        "Devuelve la versión vigente, la fecha de vigencia, el mapa código/valor y "
        "el detalle de cada parámetro CAT con tipo, rango y validaciones. "
        "Requiere rol administrador o el alcance admin.catalog.parameters.write."
    ),
    responses=_ERROR_RESPONSES,
)
def get_parameters(
    service: CatalogParametersService = Depends(get_catalog_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CatalogParametersData]:
    service.ensure_admin(actor)
    version = service.current()
    return ok(
        "Parámetros del catálogo consultados correctamente.",
        CatalogParametersData.from_version(version, _definiciones(service)),
    )


@router.put(
    "",
    response_model=ApiResponse[CatalogParametersData],
    summary="Actualizar parámetros del catálogo (FUN-39 / PRC-39)",
    description=(
        "Valida tipo, rango y dependencias antes de escribir. Cada cambio válido crea "
        "una versión inmutable con actor, fecha y valores anteriores, registra auditoría "
        "e invalida la caché por versión. Un valor inválido responde 400 sin modificar "
        "la configuración. Solo parámetros CAT: AUT-xx, COM-xx y COMU-xx se rechazan."
    ),
    responses=_ERROR_RESPONSES,
)
def update_parameters(
    payload: CatalogParametersUpdateRequest,
    service: CatalogParametersService = Depends(get_catalog_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CatalogParametersData]:
    version = service.update(
        actor,
        parametros=payload.parametros,
        modulo=payload.modulo,
        motivo=payload.motivo,
    )
    return ok(
        "Parámetros del catálogo actualizados.",
        CatalogParametersData.from_version(version, _definiciones(service)),
    )


@router.get(
    "/history",
    response_model=ApiResponse[CatalogParametersHistoryData],
    summary="Historial inmutable de versiones del catálogo",
    description=(
        "Lista las versiones almacenadas de más reciente a más antigua, con los valores "
        "anteriores, el actor y el motivo de cada cambio."
    ),
    responses=_ERROR_RESPONSES,
)
def get_history(
    limit: int = Query(default=50, ge=1, le=200, description="Máximo de versiones."),
    service: CatalogParametersService = Depends(get_catalog_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CatalogParametersHistoryData]:
    service.ensure_admin(actor)
    actual = service.current()
    versiones = service.history(limit=limit)
    return ok(
        "Historial de parámetros del catálogo consultado correctamente.",
        CatalogParametersHistoryData(
            version_actual=actual.version,
            total=len(versiones),
            versiones=[
                CatalogParameterVersionItem.from_version(
                    version, actual=version.version == actual.version
                )
                for version in versiones
            ],
        ),
    )


@router.get(
    "/history/{version}",
    response_model=ApiResponse[CatalogParameterVersionItem],
    summary="Detalle de una versión del historial del catálogo",
    responses=_ERROR_RESPONSES,
)
def get_historical_version(
    version: int,
    service: CatalogParametersService = Depends(get_catalog_parameters_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CatalogParameterVersionItem]:
    service.ensure_admin(actor)
    encontrada = service.get_version(version)
    return ok(
        f"Versión {version} de los parámetros del catálogo consultada correctamente.",
        CatalogParameterVersionItem.from_version(
            encontrada, actual=encontrada.version == service.current().version
        ),
    )
