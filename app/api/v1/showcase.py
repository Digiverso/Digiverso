"""Endpoint de vitrina del submódulo SUB-12 (HU-10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_product_service
from app.api.schemas import ProductSearchItem, ShowcaseCategory, ShowcaseData
from app.core.responses import ApiResponse, ok
from app.services.products import ProductService

router = APIRouter(
    prefix="/api/v1/catalog",
    tags=["Catálogo · Búsqueda y vitrina"],
)


@router.get(
    "/showcase",
    response_model=ApiResponse[ShowcaseData],
    summary="Consultar vitrina (FUN-30 / PRC-30)",
    description=(
        "Devuelve los productos publicados agrupados por categoría. La vitrina "
        "se guarda en caché por categoría y se invalida al escribir el catálogo."
    ),
)
def get_showcase(
    service: ProductService = Depends(get_product_service),
) -> ApiResponse[ShowcaseData]:
    grupos, total = service.showcase()
    return ok(
        "Vitrina consultada correctamente.",
        ShowcaseData(
            categorias=[
                ShowcaseCategory(
                    id=category_id,
                    nombre=nombre,
                    total=len(productos),
                    productos=[
                        ProductSearchItem.from_product(product, categoria=nombre)
                        for product in productos
                    ],
                )
                for category_id, nombre, productos in grupos
            ],
            total=total,
        ),
    )
