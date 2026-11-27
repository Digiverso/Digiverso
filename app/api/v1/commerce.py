"""Endpoints de Comercio: HU-15 licencias/descargas/historial y HU-16 ventas/liquidaciones."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.api.commerce_deps import (
    get_commerce_actor,
    get_commerce_client_ip,
    get_commerce_service,
    get_producer_actor,
)
from app.api.commerce_schemas import (
    DownloadData,
    HistoryData,
    LicenseData,
    PayoutsData,
    SalesData,
)
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.services.commerce import CommerceService

router = APIRouter(
    prefix="/api/v1/commerce",
    tags=["Comercio · Licencias, descargas e historial"],
)

_ERROR_RESPONSES = {
    400: {"description": "Paginación inválida."},
    401: {"description": "Se requiere actor autenticado."},
    403: {"description": "Sin licencia activa, límite agotado o recurso ajeno."},
    404: {"description": "La licencia o la compra no existe."},
    409: {"description": "La operación requiere una orden pagada."},
    410: {"description": "La URL firmada expiró."},
}


@router.get(
    "/licenses/{license_id}",
    response_model=ApiResponse[LicenseData],
    summary="Consultar licencia (FUN-45 / PRC-45)",
    description=(
        "Devuelve estado y condiciones de una licencia propia. Las condiciones "
        "son uso personal, sin ediciÃ³n ni reventa."
    ),
    responses=_ERROR_RESPONSES,
)
def get_license(
    license_id: str,
    actor: Actor = Depends(get_commerce_actor),
    service: CommerceService = Depends(get_commerce_service),
) -> ApiResponse[LicenseData]:
    licencia = service.get_license(license_id, actor)
    return ok("Licencia consultada correctamente.", LicenseData(**licencia))


@router.get(
    "/purchases/{purchase_id}/download",
    response_model=ApiResponse[DownloadData],
    summary="Descargar producto (FUN-46 / PRC-46)",
    description=(
        "Exige licencia activa y respeta COM-09. Genera una URL firmada que "
        "vence en COM-08 minutos y audita usuario, producto e IP. Un producto "
        "archivado conserva el acceso de las licencias vigentes."
    ),
    responses=_ERROR_RESPONSES,
)
def download_product(
    purchase_id: str,
    request: Request,
    actor: Actor = Depends(get_commerce_actor),
    ip: str = Depends(get_commerce_client_ip),
    service: CommerceService = Depends(get_commerce_service),
) -> ApiResponse[DownloadData]:
    resultado = service.download(
        purchase_id,
        actor,
        ip=ip,
        base_url=str(request.base_url),
    )
    return ok(
        "Descarga autorizada correctamente.",
        DownloadData.from_result(resultado),
    )


@router.get(
    "/purchases",
    response_model=ApiResponse[HistoryData],
    summary="Consultar historial de compras (FUN-47 / PRC-47)",
    description=(
        "Historial del comprador autenticado con compras, licencias y estados; "
        "paginado y ordenado por fecha (mÃ¡s reciente primero)."
    ),
    responses=_ERROR_RESPONSES,
)
def purchase_history(
    pagina: str | None = Query(default=None, description="PÃ¡gina, desde 1."),
    tamanio_pagina: str | None = Query(
        default=None, alias="tamanioPagina", description="Elementos por pÃ¡gina."
    ),
    actor: Actor = Depends(get_commerce_actor),
    service: CommerceService = Depends(get_commerce_service),
) -> ApiResponse[HistoryData]:
    datos = service.history(
        actor, pagina=pagina, tamanio_pagina=tamanio_pagina
    )
    return ok(
        "Historial de compras consultado correctamente.",
        HistoryData(**datos),
    )


@router.get(
    "/downloads/{token}",
    summary="Acceder a una URL firmada de descarga",
    description=(
        "Valida la firma HMAC y el vencimiento COM-08 antes de redirigir al "
        "objeto de S3. Una URL expirada responde 410 y una firma invÃ¡lida 403."
    ),
    responses=_ERROR_RESPONSES,
)
def resolve_signed_download(
    token: str,
    service: CommerceService = Depends(get_commerce_service),
) -> RedirectResponse:
    payload = service.resolve_download(token)
    return RedirectResponse(
        service.storage_url(payload.object_key), status_code=307
    )

@router.get(
    "/producer/sales",
    response_model=ApiResponse[SalesData],
    summary="Consultar ventas del productor (FUN-50 / PRC-50)",
    description="Lista ventas, comisiones y neto acumulado del productor autenticado.",
    responses=_ERROR_RESPONSES,
)
def producer_sales(
    pagina: str | None = Query(default=None, description="Página, desde 1."),
    tamanio_pagina: str | None = Query(
        default=None, alias="tamanioPagina", description="Elementos por página."
    ),
    actor: Actor = Depends(get_producer_actor),
    service: CommerceService = Depends(get_commerce_service),
) -> ApiResponse[SalesData]:
    datos = service.list_sales(actor, pagina=pagina, tamanio_pagina=tamanio_pagina)
    return ok("Ventas consultadas correctamente.", SalesData(**datos))


@router.get(
    "/producer/payouts",
    response_model=ApiResponse[PayoutsData],
    summary="Consultar liquidaciones del productor (FUN-51 / PRC-51)",
    description="Lista liquidaciones y estados del productor autenticado.",
    responses=_ERROR_RESPONSES,
)
def producer_payouts(
    pagina: str | None = Query(default=None, description="Página, desde 1."),
    tamanio_pagina: str | None = Query(
        default=None, alias="tamanioPagina", description="Elementos por página."
    ),
    actor: Actor = Depends(get_producer_actor),
    service: CommerceService = Depends(get_commerce_service),
) -> ApiResponse[PayoutsData]:
    datos = service.list_payouts(actor, pagina=pagina, tamanio_pagina=tamanio_pagina)
    return ok("Liquidaciones consultadas correctamente.", PayoutsData(**datos))
