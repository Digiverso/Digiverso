"""Endpoints documentados de HU-11: control de publicaciones (SUB-13)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_admin_principal
from app.api.deps import get_publication_control_service
from app.api.schemas import (
    ApprovalData,
    ApproveReviewRequest,
    RejectReviewRequest,
    RejectionData,
    ReviewQueueData,
    ReviewQueueItem,
)
from app.core.responses import ApiResponse, ok
from app.services.publication_control import Principal, PublicationControlService

router = APIRouter(
    prefix="/api/v1/catalog/publication-control",
    tags=["Catálogo · Control de publicaciones"],
)

_ERROR_RESPONSES = {
    400: {"description": "Checklist incompleto o rechazo sin motivo CAT-14/observación."},
    403: {"description": "No es administrador o revisa un producto propio."},
    404: {"description": "El producto no existe."},
    409: {"description": "El producto no está en revisión."},
}


@router.get(
    "/queue",
    response_model=ApiResponse[ReviewQueueData],
    summary="Consultar cola de revisión (FUN-32 / PRC-32)",
    description=(
        "Solo administradores. Muestra los productos ``en_revision`` ordenados "
        "por fecha de envío (antigüedad), con autor, medios y políticas CAT "
        "aplicables."
    ),
    responses=_ERROR_RESPONSES,
)
def review_queue(
    principal: Principal = Depends(get_admin_principal),
    service: PublicationControlService = Depends(get_publication_control_service),
) -> ApiResponse[ReviewQueueData]:
    entries = service.queue(actor=principal)
    politicas = service.politicas()
    return ok(
        "Cola de revisión consultada correctamente.",
        ReviewQueueData(
            items=[
                ReviewQueueItem.from_entry(entry, politicas=politicas)
                for entry in entries
            ],
            total=len(entries),
        ),
    )


@router.patch(
    "/{product_id}/approve",
    response_model=ApiResponse[ApprovalData],
    summary="Aprobar publicación (FUN-33 / PRC-33)",
    description=(
        "Exige el checklist completo de autoría, edad, derechos, contenido y "
        "funciones. Publica el producto, lo indexa, registra la evidencia y "
        "notifica al productor."
    ),
    responses=_ERROR_RESPONSES,
)
def approve_publication(
    product_id: str,
    payload: ApproveReviewRequest,
    principal: Principal = Depends(get_admin_principal),
    service: PublicationControlService = Depends(get_publication_control_service),
) -> ApiResponse[ApprovalData]:
    product, notificado = service.approve(
        product_id,
        actor=principal,
        checklist=payload.checklist,
    )
    return ok(
        "Publicación aprobada correctamente.",
        ApprovalData(
            producto_id=product.id,
            estado=product.estado,
            fecha_publicacion=product.estado_desde,
            notificado=notificado,
        ),
    )


@router.patch(
    "/{product_id}/reject",
    response_model=ApiResponse[RejectionData],
    summary="Rechazar publicación (FUN-34 / PRC-34)",
    description=(
        "Exige motivo CAT-14 y observación. Devuelve el producto a ``rechazado`` "
        "para que el productor corrija y reenvíe; notifica la decisión."
    ),
    responses=_ERROR_RESPONSES,
)
def reject_publication(
    product_id: str,
    payload: RejectReviewRequest,
    principal: Principal = Depends(get_admin_principal),
    service: PublicationControlService = Depends(get_publication_control_service),
) -> ApiResponse[RejectionData]:
    product, _ = service.reject(
        product_id,
        actor=principal,
        motivo=payload.motivo,
        observacion=payload.observacion,
    )
    return ok(
        "Publicación rechazada correctamente.",
        RejectionData(
            producto_id=product.id,
            estado=product.estado,
            motivo=str(payload.motivo).strip(),
            observacion=str(payload.observacion).strip(),
        ),
    )
