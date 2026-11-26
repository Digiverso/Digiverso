"""Endpoints documentados del submódulo SUB-08: Categorías."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_actor, get_category_service
from app.api.schemas import (
    CategoryCreateRequest,
    CategoryNode,
    CategoryUpdateRequest,
)
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.services.categories import CategoryService

router = APIRouter(
    prefix="/api/v1/catalog/categories",
    tags=["Catálogo · Categorías"],
)

_ERROR_RESPONSES = {
    400: {"description": "Jerarquía inválida o ciclo detectado."},
    403: {"description": "El actor no tiene permisos de administración."},
    404: {"description": "La categoría no existe."},
    409: {"description": "Nombre duplicado o categoría con productos activos."},
    422: {"description": "Datos inválidos (entre ellos, longitud CAT-17)."},
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[CategoryNode],
    summary="Crear categoría (FUN-17 / PRC-17)",
    description=(
        "Crea una categoría o subcategoría. El nombre se normaliza (mayúsculas y "
        "tildes) y debe ser único bajo el mismo padre. LONGITUD CAT-17."
    ),
    responses=_ERROR_RESPONSES,
)
def create_category(
    payload: CategoryCreateRequest,
    service: CategoryService = Depends(get_category_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CategoryNode]:
    category = service.create(actor=actor, **payload.model_dump(by_alias=False))
    return ok("Categoría creada correctamente.", CategoryNode.from_category(category))


@router.patch(
    "/{category_id}",
    response_model=ApiResponse[CategoryNode],
    summary="Editar categoría (FUN-18 / PRC-18)",
    description=(
        "Actualiza nombre, descripción, orden o padre. Solo se aplican los campos "
        "enviados. Al mover la categoría se reescriben las rutas del subárbol y se "
        "rechazan ciclos."
    ),
    responses=_ERROR_RESPONSES,
)
def update_category(
    category_id: str,
    payload: CategoryUpdateRequest,
    service: CategoryService = Depends(get_category_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CategoryNode]:
    category = service.update(
        category_id, actor=actor, **payload.model_dump(exclude_unset=True, by_alias=False)
    )
    return ok("Categoría actualizada correctamente.", CategoryNode.from_category(category))


@router.delete(
    "/{category_id}",
    response_model=ApiResponse[CategoryNode],
    summary="Desactivar categoría (FUN-19 / PRC-19)",
    description=(
        "Desactivación lógica: conserva historial y productos. Si existen productos "
        "activos en el subárbol responde 409 exigiendo su reasignación."
    ),
    responses=_ERROR_RESPONSES,
)
def deactivate_category(
    category_id: str,
    service: CategoryService = Depends(get_category_service),
    actor: Actor = Depends(get_actor),
) -> ApiResponse[CategoryNode]:
    category = service.deactivate(category_id, actor=actor)
    return ok("Categoría desactivada correctamente.", CategoryNode.from_category(category))


@router.get(
    "",
    response_model=ApiResponse[list[CategoryNode]],
    summary="Consultar árbol de categorías (FUN-20 / PRC-20)",
    description=(
        "Devuelve únicamente categorías activas como un árbol de hijos anidados, "
        "ordenados por ``orden`` y nombre. El resultado se mantiene en caché y se "
        "invalida en cada escritura."
    ),
    responses=_ERROR_RESPONSES,
)
def get_category_tree(
    service: CategoryService = Depends(get_category_service),
) -> ApiResponse[list[CategoryNode]]:
    return ok("Árbol de categorías consultado correctamente.", service.get_tree())
