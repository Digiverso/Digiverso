"""Endpoints de HU-12: reportes y sanciones (SUB-13)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_admin_principal
from app.api.deps import get_actor, get_report_service
from app.api.schemas import (
    ReportCreateRequest,
    ReportData,
    ReportListData,
    ReportResolveRequest,
    SanctionCreateRequest,
    SanctionData,
    SanctionListData,
)
from app.core.responses import ApiResponse, ok
from app.services.reports import Principal, ReportService

reports_router = APIRouter(prefix="/api/v1/catalog", tags=["Catálogo · Reportes"])
control_router = APIRouter(
    prefix="/api/v1/catalog/publication-control",
    tags=["Catálogo · Control de publicaciones"],
)

_ERROR_RESPONSES = {
    400: {"description": "Motivo CAT-14, evidencia, decisión o sanción CAT-15 inválidos."},
    403: {"description": "Se requiere un administrador para gestionar reportes."},
    404: {"description": "El reporte o la sanción no existe."},
    409: {"description": "Reporte abierta duplicada o reporte ya resuelto."},
}


@reports_router.post(
    "/reports",
    status_code=201,
    response_model=ApiResponse[ReportData],
    response_model_exclude_none=True,
    summary="Reportar contenido (FUN-35 / PRC-35)",
    description=(
        "Registra un reporte sobre un producto, reseña o usuario. Exige motivo "
        "CAT-14 y evidencia; impide más de un reporte abierto por usuario y "
        "contenido. La identidad del reportante no se expone en la respuesta."
    ),
    responses=_ERROR_RESPONSES,
)
def create_report(
    payload: ReportCreateRequest,
    actor: Principal = Depends(get_actor),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[ReportData]:
    reporte = service.create_report(
        actor,
        contenido_id=payload.contenido_id,
        motivo=payload.motivo,
        evidencia=payload.evidencia,
        tipo_contenido=payload.tipo_contenido,
        descripcion=payload.descripcion,
    )
    return ok("Reporte registrado correctamente.", ReportData.from_report(reporte))


@control_router.get(
    "/reports",
    response_model=ApiResponse[ReportListData],
    summary="Consultar reportes (FUN-36 / PRC-36)",
    description=(
        "Solo administradores. Devuelve la cola de control con filtros opcionales "
        "por estado, contenido y motivo."
    ),
    responses=_ERROR_RESPONSES,
)
def list_reports(
    estado: str | None = Query(default=None),
    contenido_id: str | None = Query(default=None, alias="contenidoId"),
    motivo: str | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    tamanio_pagina: int = Query(default=20, ge=1, le=100, alias="tamanioPagina"),
    actor: Principal = Depends(get_admin_principal),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[ReportListData]:
    reportes, total = service.list_reports(
        actor,
        estado=estado,
        contenido_id=contenido_id,
        motivo=motivo,
        pagina=pagina,
        tamanio=tamanio_pagina,
    )
    return ok(
        "Reportes consultados correctamente.",
        ReportListData(
            items=[ReportData.from_report(reporte) for reporte in reportes],
            total=total,
            pagina=pagina,
            tamanioPagina=tamanio_pagina,
        ),
    )


@control_router.get(
    "/reports/{reporte_id}",
    response_model=ApiResponse[ReportData],
    summary="Detalle de un reporte (FUN-36 / PRC-36)",
    responses=_ERROR_RESPONSES,
)
def get_report(
    reporte_id: str,
    actor: Principal = Depends(get_admin_principal),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[ReportData]:
    reporte = service.get_report(actor, reporte_id)
    return ok("Reporte consultado correctamente.", ReportData.from_report(reporte))


def _resolve(
    reporte_id: str,
    payload: ReportResolveRequest,
    actor: Principal,
    service: ReportService,
) -> ApiResponse[ReportData]:
    resolucion = payload.resolucion or {}
    decision = payload.decision or resolucion.get("decision")
    if decision is None and payload.estado:
        decision = {
            "desestimado": "desestimar",
            "sancionado": "sancionar",
        }.get(payload.estado)
    observacion = payload.observacion or resolucion.get("observacion")
    sancion = payload.sancion or resolucion.get("sancion")
    if not isinstance(sancion, dict):
        sancion = None
    reporte, _ = service.resolve_report(
        reporte_id,
        actor,
        decision=decision,
        observacion=observacion,
        sancion=sancion,
    )
    return ok("Reporte resuelto correctamente.", ReportData.from_report(reporte))


@control_router.patch(
    "/reports/{reporte_id}",
    response_model=ApiResponse[ReportData],
    summary="Resolver reporte (FUN-36 / PRC-36)",
    description=(
        "El administrador desestima o aplica una sanción CAT-15. La resolución "
        "contiene decisión, sanción y observación; se notifica a las partes."
    ),
    responses=_ERROR_RESPONSES,
)
def resolve_report(
    reporte_id: str,
    payload: ReportResolveRequest,
    actor: Principal = Depends(get_admin_principal),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[ReportData]:
    return _resolve(reporte_id, payload, actor, service)


@control_router.patch(
    "/reports/{reporte_id}/resolve",
    response_model=ApiResponse[ReportData],
    include_in_schema=False,
)
def resolve_report_alias(
    reporte_id: str,
    payload: ReportResolveRequest,
    actor: Principal = Depends(get_admin_principal),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[ReportData]:
    return _resolve(reporte_id, payload, actor, service)


@control_router.post(
    "/sanctions",
    status_code=201,
    response_model=ApiResponse[SanctionData],
    summary="Aplicar sanción (FUN-37 / PRC-37)",
    description=(
        "Registra una sanción CAT-15 con evidencia, archiva o restringe el "
        "contenido y notifica al usuario afectado. Una suspensión temporal "
        "usa los días de CAT-16."
    ),
    responses=_ERROR_RESPONSES,
)
def apply_sanction(
    payload: SanctionCreateRequest,
    actor: Principal = Depends(get_admin_principal),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[SanctionData]:
    sancion = service.apply_sanction(
        actor,
        reporte_id=payload.reporte_id,
        contenido_id=payload.contenido_id,
        tipo=payload.tipo,
        duracion_dias=payload.duracion_dias,
        usuario_afectado=payload.usuario_afectado,
        motivo=payload.motivo,
        evidencia=payload.evidencia,
        observacion=payload.observacion,
        accion_contenido=payload.accion_contenido,
    )
    return ok("Sanción aplicada correctamente.", SanctionData.from_sanction(sancion))


@control_router.get(
    "/sanctions",
    response_model=ApiResponse[SanctionListData],
    summary="Consultar sanciones (FUN-37 / PRC-37)",
    responses=_ERROR_RESPONSES,
)
def list_sanctions(
    reporte_id: str | None = Query(default=None, alias="reporteId"),
    usuario_afectado: str | None = Query(default=None, alias="usuarioAfectado"),
    actor: Principal = Depends(get_admin_principal),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[SanctionListData]:
    sanciones = service.list_sanctions(
        actor, reporte_id=reporte_id, usuario_afectado=usuario_afectado
    )
    return ok(
        "Sanciones consultadas correctamente.",
        SanctionListData(
            items=[SanctionData.from_sanction(sancion) for sancion in sanciones],
            total=len(sanciones),
        ),
    )


@control_router.get(
    "/sanctions/{sancion_id}",
    response_model=ApiResponse[SanctionData],
    summary="Detalle de una sanción (FUN-37 / PRC-37)",
    responses=_ERROR_RESPONSES,
)
def get_sanction(
    sancion_id: str,
    actor: Principal = Depends(get_admin_principal),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[SanctionData]:
    sancion = service.get_sanction(actor, sancion_id)
    return ok("Sanción consultada correctamente.", SanctionData.from_sanction(sancion))
