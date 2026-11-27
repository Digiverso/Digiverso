"""Endpoints de seguimiento, feed, intereses y recomendaciones (HU-19)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.community_schemas import (
    FeedData,
    FollowData,
    InterestsData,
    InterestsRequest,
    RecommendationsData,
    UnfollowData,
)
from app.api.deps import get_actor, get_community_service
from app.core.responses import ApiResponse, ok
from app.domain.actor import Actor
from app.services.community import CommunityService

router = APIRouter(
    prefix="/api/v1/community",
    tags=["Comunidad · Seguimiento y feed"],
)


@router.post(
    "/users/{usuario_id}/follow",
    status_code=201,
    response_model=ApiResponse[FollowData],
    summary="Seguir usuario (FUN-58 / PRC-58)",
    description=(
        "Crea la relación de seguimiento. Rechaza el auto-seguimiento en dominio "
        "y aplica el límite COMU-05."
    ),
)
def follow_user(
    usuario_id: str,
    actor: Actor = Depends(get_actor),
    service: CommunityService = Depends(get_community_service),
) -> ApiResponse[FollowData]:
    return ok("Usuario seguido correctamente.", service.follow(actor.id, usuario_id))


@router.delete(
    "/users/{usuario_id}/follow",
    response_model=ApiResponse[UnfollowData],
    summary="Dejar de seguir usuario (FUN-59 / PRC-59)",
    description="Elimina la relación y recalcula los contadores de ambos usuarios.",
)
def unfollow_user(
    usuario_id: str,
    actor: Actor = Depends(get_actor),
    service: CommunityService = Depends(get_community_service),
) -> ApiResponse[UnfollowData]:
    return ok(
        "Se dejó de seguir al usuario correctamente.",
        service.unfollow(actor.id, usuario_id),
    )


@router.get(
    "/feed/following",
    response_model=ApiResponse[FeedData],
    summary="Consultar feed de seguidos (FUN-60 / PRC-60)",
    description=(
        "Devuelve productos publicados de los productores seguidos, paginados "
        "según COMU-07 y construidos con fan-out híbrido en caché."
    ),
)
def following_feed(
    pagina: int = 1,
    tamanioPagina: int = 20,
    actor: Actor = Depends(get_actor),
    service: CommunityService = Depends(get_community_service),
) -> ApiResponse[FeedData]:
    return ok(
        "Feed consultado correctamente.",
        service.following_feed(actor.id, pagina, tamanioPagina),
    )


@router.put(
    "/me/interests",
    response_model=ApiResponse[InterestsData],
    summary="Configurar intereses (FUN-61 / PRC-61)",
    description=(
        "Sustituye las categorías de interés. Deben existir y estar activas; "
        "el máximo viene dado por COMU-08."
    ),
)
def set_interests(
    payload: InterestsRequest,
    actor: Actor = Depends(get_actor),
    service: CommunityService = Depends(get_community_service),
) -> ApiResponse[InterestsData]:
    return ok(
        "Intereses actualizados correctamente.",
        service.set_interests(actor.id, payload.categorias),
    )


@router.get(
    "/feed/recommended",
    response_model=ApiResponse[RecommendationsData],
    summary="Consultar recomendaciones (FUN-62 / PRC-62)",
    description=(
        "Recomienda publicados usando intereses y señales de compra; excluye "
        "productos comprados y propios. COMU-09 limita y COMU-10 ordena."
    ),
)
def recommended_feed(
    actor: Actor = Depends(get_actor),
    service: CommunityService = Depends(get_community_service),
) -> ApiResponse[RecommendationsData]:
    return ok(
        "Recomendaciones consultadas correctamente.",
        service.recommendations(actor.id),
    )
