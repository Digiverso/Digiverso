"""Endpoints documentados del submódulo SUB-09: Productos (HU-08)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_actor, get_product_service
from app.api.schemas import (
    ProductCreateRequest,
    ProductResponse,
    ProductTransition,
    ProductUpdateRequest,
)
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.domain.product import ESTADO_EN_REVISION
from app.services.products import ProductService

router = APIRouter(
    prefix="/api/v1/catalog/products",
    tags=["Catálogo · Productos"],
)

_ERROR_RESPONSES = {
    403: {"description": "El actor no es el autor del producto."},
    404: {"description": "El producto no existe."},
    409: {"description": "Transición de estado no permitida."},
    422: {"description": "Reglas CAT-01/03/09/11/12/13 incumplidas."},
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ProductResponse],
    summary="Crear producto (FUN-21 / PRC-21)",
    description=(
        "Crea un producto en borrador. El autor se obtiene del token, nunca del "
        "cuerpo. Se validan precio CAT-01, edad CAT-03, nombre CAT-11, "
        "descripción CAT-12 y categorías CAT-13."
    ),
    responses=_ERROR_RESPONSES,
)
def create_product(
    payload: ProductCreateRequest,
    service: ProductService = Depends(get_product_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[ProductResponse]:
    product = service.create(
        actor=actor,
        **payload.model_dump(by_alias=False, exclude={"autor_id"}),
    )
    return ok(
        "Producto creado en borrador.",
        ProductResponse.from_product(
            product, licencias_activas=service.active_licenses(product.id)
        ),
    )


@router.patch(
    "/{product_id}",
    response_model=ApiResponse[ProductResponse],
    summary="Editar producto (FUN-22 / PRC-22)",
    description=(
        "Actualiza solo los campos enviados mientras el producto está en "
        "borrador, rechazado, publicado o archivado. Solo puede hacerlo su autor."
    ),
    responses=_ERROR_RESPONSES,
)
def update_product(
    product_id: str,
    payload: ProductUpdateRequest,
    service: ProductService = Depends(get_product_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[ProductResponse]:
    product = service.update(
        product_id,
        actor=actor,
        **payload.model_dump(
            by_alias=False, exclude_unset=True, exclude={"autor_id"}
        ),
    )
    return ok(
        "Producto actualizado correctamente.",
        ProductResponse.from_product(
            product, licencias_activas=service.active_licenses(product.id)
        ),
    )


@router.post(
    "/{product_id}/submit-review",
    response_model=ApiResponse[ProductTransition],
    summary="Enviar producto a revisión (FUN-23 / PRC-23)",
    description=(
        "Exige al menos CAT-09 imágenes y cambia el estado a ``en_revision``. "
        "Devuelve el estado resultante y la fecha de la transición."
    ),
    responses=_ERROR_RESPONSES,
)
def submit_review(
    product_id: str,
    service: ProductService = Depends(get_product_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[ProductTransition]:
    anterior = service.get(product_id).estado
    product = service.submit_review(product_id, actor=actor)
    return ok(
        "Producto enviado a revisión.",
        ProductTransition.from_product(
            product,
            estado_anterior=anterior,
            transicion="enviar a revisión",
            licencias_activas=service.active_licenses(product.id),
        ),
    )


@router.patch(
    "/{product_id}/archive",
    response_model=ApiResponse[ProductTransition],
    summary="Archivar producto (FUN-24 / PRC-24)",
    description=(
        "Pasa el producto a ``archivado`` y lo retira de la vitrina. Conserva "
        "las licencias y los datos históricos."
    ),
    responses=_ERROR_RESPONSES,
)
def archive_product(
    product_id: str,
    service: ProductService = Depends(get_product_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[ProductTransition]:
    anterior = service.get(product_id).estado
    product = service.archive(product_id, actor=actor)
    return ok(
        "Producto archivado correctamente.",
        ProductTransition.from_product(
            product,
            estado_anterior=anterior,
            transicion="archivar",
            licencias_activas=service.active_licenses(product.id),
        ),
    )


@router.patch(
    "/{product_id}/reactivate",
    response_model=ApiResponse[ProductTransition],
    summary="Reactivar producto (FUN-25 / PRC-25)",
    description=(
        "Desde ``archivado``: envía a revisión si hubo cambios; si no, publica. "
        "Cualquier otro estado devuelve 409."
    ),
    responses=_ERROR_RESPONSES,
)
def reactivate_product(
    product_id: str,
    service: ProductService = Depends(get_product_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[ProductTransition]:
    anterior = service.get(product_id).estado
    product = service.reactivate(product_id, actor=actor)
    mensaje = (
        "Producto reactivado y enviado a revisión."
        if product.estado == ESTADO_EN_REVISION
        else "Producto reactivado y publicado."
    )
    return ok(
        mensaje,
        ProductTransition.from_product(
            product,
            estado_anterior=anterior,
            transicion="reactivar",
            licencias_activas=service.active_licenses(product.id),
        ),
    )


@router.get(
    "",
    response_model=ApiResponse[list[ProductResponse]],
    summary="Vitrina de productos",
    description="Devuelve únicamente los productos publicados y activos.",
)
def list_showcase(
    service: ProductService = Depends(get_product_service),
) -> ApiResponse[list[ProductResponse]]:
    return ok(
        "Vitrina de productos consultada correctamente.",
        [
            ProductResponse.from_product(
                product, licencias_activas=service.active_licenses(product.id)
            )
            for product in service.list_showcase()
        ],
    )


@router.get(
    "/{product_id}",
    response_model=ApiResponse[ProductResponse],
    summary="Consultar producto por identificador",
    responses=_ERROR_RESPONSES,
)
def get_product(
    product_id: str,
    service: ProductService = Depends(get_product_service),
) -> ApiResponse[ProductResponse]:
    product = service.get(product_id)
    return ok(
        "Producto consultado correctamente.",
        ProductResponse.from_product(
            product, licencias_activas=service.active_licenses(product.id)
        ),
    )
