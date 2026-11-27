"""Endpoints de reseñas y calificaciones (HU-18, SUB-22 y SUB-23)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_actor, get_review_service
from app.api.schemas import RatingData, ReviewCreateRequest, ReviewItem, ReviewPage
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.services.reviews import ReviewService

router = APIRouter(
    prefix="/api/v1/community/products",
    tags=["Comunidad · Reseñas y calificaciones"],
)

_ERROR_RESPONSES = {
    400: {"description": "Calificación fuera de COMU-01 o texto fuera de COMU-02."},
    403: {"description": "COMU-04: el usuario no acredita compra o licencia."},
    404: {"description": "El producto no existe."},
    409: {"description": "COMU-03: el usuario ya reseñó este producto."},
    422: {"description": "Paginación fuera de rango."},
}


@router.post(
    "/{product_id}/reviews",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ReviewItem],
    summary="Publicar reseña (FUN-54 / PRC-54)",
    description=(
        "Valida la compra o licencia del consumidor (COMU-04), la unicidad "
        "(COMU-03), el rango 1..5 (COMU-01) y la longitud del texto (COMU-02). "
        "Sanea el texto, recalcula el promedio y publica `review.created`."
    ),
    responses=_ERROR_RESPONSES,
)
def create_review(
    product_id: str,
    payload: ReviewCreateRequest,
    service: ReviewService = Depends(get_review_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[ReviewItem]:
    review = service.publish(
        product_id,
        user_id=actor.id,
        calificacion=payload.calificacion,
        texto=payload.texto,
    )
    return ok(
        "Reseña publicada correctamente.",
        ReviewItem.from_review(review),
    )


@router.get(
    "/{product_id}/reviews",
    response_model=ApiResponse[ReviewPage],
    summary="Consultar reseñas (FUN-55 / PRC-55)",
    description="Devuelve reseñas visibles paginadas, de la más reciente a la más antigua.",
    responses=_ERROR_RESPONSES,
)
def list_reviews(
    product_id: str,
    pagina: int = Query(default=1, ge=1, description="Página (base 1)."),
    tamanio_pagina: int | None = Query(
        default=None,
        ge=1,
        alias="tamanioPagina",
        description="Tamaño de página; limitado por COMMUNITY_MAX_PAGE_SIZE.",
    ),
    service: ReviewService = Depends(get_review_service),
) -> ApiResponse[ReviewPage]:
    reviews, total, size = service.list_reviews(
        product_id, pagina=pagina, tamanio_pagina=tamanio_pagina
    )
    return ok(
        "Reseñas consultadas correctamente.",
        ReviewPage(
            items=[ReviewItem.from_review(review) for review in reviews],
            total=total,
            pagina=pagina,
            tamanio_pagina=size,
        ),
    )


@router.get(
    "/{product_id}/rating",
    response_model=ApiResponse[RatingData],
    summary="Consultar calificación (FUN-56/FUN-57)",
    description=(
        "Devuelve promedio, total de reseñas visibles y distribución por "
        "calificación. El promedio se calcula por agregación y se cachea."
    ),
    responses=_ERROR_RESPONSES,
)
def get_rating(
    product_id: str,
    service: ReviewService = Depends(get_review_service),
) -> ApiResponse[RatingData]:
    return ok(
        "Calificación consultada correctamente.",
        RatingData.from_rating(service.rating(product_id)),
    )
