"""Endpoints documentados del submódulo SUB-10: medios del producto (HU-09)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from app.api.deps import get_actor, get_media_service
from app.api.schemas import MediaDeleteResponse, MediaUploadResponse, MedioResponse
from app.core.config import Settings
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.domain.exceptions import MediaFileRequiredError
from app.domain.media import ArchivoMedio
from app.services.media import MediaService

router = APIRouter(
    prefix="/api/v1/catalog/products",
    tags=["Catálogo · Medios del producto"],
)

_ERROR_RESPONSES = {
    400: {"description": "Formato no permitido (CAT-05/CAT-07) o archivo rechazado por el escaneo."},
    403: {"description": "El actor no es el autor del producto."},
    404: {"description": "El producto o el medio no existe."},
    409: {"description": "Estado no editable o máximo CAT-10 alcanzado."},
    413: {"description": "El archivo supera CAT-06 (imagen) o CAT-08 (video)."},
}


@router.post(
    "/{product_id}/media",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[MediaUploadResponse],
    summary="Cargar medio del producto (FUN-26 / PRC-26)",
    description=(
        "Recibe una imagen (CAT-05/CAT-06) o un video (CAT-07/CAT-08) en el campo "
        "`archivo` —también se acepta `file`—. Valida la firma binaria, el tamaño y "
        "el máximo de CAT-10, escanea el archivo antes de publicarlo y lo asocia "
        "al producto. Solo el autor puede cargarlo."
    ),
    responses=_ERROR_RESPONSES,
)
async def upload_media(
    product_id: str,
    request: Request,
    archivo: UploadFile | None = File(default=None, alias="archivo"),
    alternativo: UploadFile | None = File(default=None, alias="file"),
    service: MediaService = Depends(get_media_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[MediaUploadResponse]:
    seleccionado = archivo or alternativo
    if seleccionado is None:
        raise MediaFileRequiredError(
            "Se requiere un archivo en el campo ``archivo``.",
            details={"campo": "archivo"},
        )

    settings: Settings = request.app.state.settings
    contenido = await seleccionado.read(settings.media_max_read_bytes)
    medio = service.upload(
        product_id,
        archivo=ArchivoMedio(
            nombre=seleccionado.filename or "",
            contenido=contenido,
            content_type=seleccionado.content_type or "",
            tamano=seleccionado.size,
        ),
        actor=actor,
    )
    return ok(
        "Medio cargado correctamente.",
        MediaUploadResponse.from_medio(product_id, medio),
    )


@router.delete(
    "/{product_id}/media/{media_id}",
    response_model=ApiResponse[MediaDeleteResponse],
    summary="Eliminar medio del producto (FUN-27 / PRC-27)",
    description=(
        "Eliminación lógica: el medio pasa a estado ``eliminado`` y los restantes "
        "se reordenan desde 1. Solo el autor puede eliminarlo."
    ),
    responses=_ERROR_RESPONSES,
)
def delete_media(
    product_id: str,
    media_id: str,
    service: MediaService = Depends(get_media_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[MediaDeleteResponse]:
    eliminado, restantes = service.delete(product_id, media_id, actor=actor)
    return ok(
        "Medio eliminado correctamente.",
        MediaDeleteResponse(
            id=eliminado.id,
            producto_id=product_id,
            total_medios=len(restantes),
            medios=[
                MedioResponse(
                    id=medio.id,
                    tipo=medio.tipo,
                    url=medio.url,
                    orden=medio.orden,
                    estado=medio.estado,
                )
                for medio in restantes
            ],
        ),
    )
