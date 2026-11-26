"""Endpoints documentados del submódulo SUB-09: Productos (HU-08)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_actor, get_product_service
from app.api.schemas import (
    ProductCreateRequest,
    ProductResponse,
    ProductSearchItem,
    ProductSearchPage,
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
    response_model=ApiResponse[ProductSearchPage],
    summary="Buscar productos (FUN-28 / PRC-28 y FUN-29 / PRC-29)",
    description=(
        "Busca únicamente productos publicados y activos. Acepta texto, "
        "categoría, edad CAT-03, rango de precio CAT-01, orden y paginación. "
        "Los filtros se combinan con AND; el índice incluye sinónimos y "
        "tolerancia a errores tipográficos."
    ),
    responses=_ERROR_RESPONSES,
)
def search_products(
    q: str | None = Query(default=None, description="Término de búsqueda."),
    categoria: str | None = Query(default=None, description="Identificador de categoría activa."),
    edad: int | None = Query(default=None, ge=0, description="Edad CAT-03 del comprador."),
    precio_min: int | None = Query(
        default=None, alias="precioMin", description="Precio mínimo CAT-01 en COP."
    ),
    precio_max: int | None = Query(
        default=None, alias="precioMax", description="Precio máximo CAT-01 en COP."
    ),
    orden: str | None = Query(
        default=None,
        description="relevancia | fecha_desc | fecha_asc | precio_asc | precio_desc",
    ),
    pagina: int = Query(default=1, ge=1, description="Página (base 1)."),
    tamanio_pagina: int | None = Query(
        default=None,
        alias="tamanioPagina",
        description="Tamaño de página; limitado por CATALOG_MAX_PAGE_SIZE.",
    ),
    service: ProductService = Depends(get_product_service),
) -> ApiResponse[ProductSearchPage]:
    productos, total, consulta = service.search(
        q=q,
        categoria=categoria,
        edad=edad,
        precio_min=precio_min,
        precio_max=precio_max,
        orden=orden,
        pagina=pagina,
        tamanio_pagina=tamanio_pagina,
    )
    nombres: dict[str, str | None] = {}
    items: list[ProductSearchItem] = []
    for product in productos:
        category_id = product.categoria_id or (
            product.categorias[0] if product.categorias else ""
        )
        if category_id not in nombres:
            nombres[category_id] = service.category_name(category_id)
        items.append(
            ProductSearchItem.from_product(product, categoria=nombres[category_id])
        )
    return ok(
        "Búsqueda realizada correctamente.",
        ProductSearchPage(
            items=items,
            total=total,
            pagina=consulta.pagina,
            tamanio_pagina=consulta.tamanio_pagina,
        ),
    )


@router.get(
    "/{product_id}",
    response_model=ApiResponse[ProductResponse],
    summary="Consultar detalle del producto (FUN-31 / PRC-31)",
    description=(
        "Muestra el detalle si el producto está publicado o si el actor tiene "
        "licencia vigente, es su autor o es administrador. Los datos privados "
        "del productor no se exponen a visitantes ni consumidores."
    ),
    responses=_ERROR_RESPONSES,
)
def get_product(
    product_id: str,
    service: ProductService = Depends(get_product_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[ProductResponse]:
    product, licencia, privilegiado = service.get_detail(product_id, actor=actor)
    return ok(
        "Producto consultado correctamente.",
        ProductResponse.from_product(
            product,
            licencias_activas=service.active_licenses(product.id),
            incluir_privados=privilegiado,
            categoria=service.category_name(
                product.categoria_id or (product.categorias[0] if product.categorias else None)
            ),
            licencia=licencia,
        ),
    )
