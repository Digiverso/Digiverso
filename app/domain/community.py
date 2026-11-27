"""Reglas puras de seguimiento, feed, intereses y recomendaciones (HU-19).

Los valores numéricos de COMU-05/07/08/09/10 no venían explícitos en la
especificación: se fijan como valores por defecto y se pueden sobreescribir por
variable de entorno al construir :class:`CommunitySettings`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from app.domain.exceptions import CatalogError
from app.domain.product import Product

COMU_05_MAX_FOLLOWING = 200
COMU_07_DEFAULT_PAGE_SIZE = 20
COMU_07_MAX_PAGE_SIZE = 100
COMU_08_MAX_INTERESTS = 10
COMU_09_MAX_RECOMMENDATIONS = 20
COMU_10_ORDER = "puntuacion_desc,fecha_desc,id_asc"


@dataclass(frozen=True)
class CommunitySettings:
    """Parámetros configurables de la comunidad (HU-19)."""

    max_following: int = COMU_05_MAX_FOLLOWING  # COMU-05
    default_page_size: int = COMU_07_DEFAULT_PAGE_SIZE  # COMU-07
    max_page_size: int = COMU_07_MAX_PAGE_SIZE  # COMU-07
    max_interests: int = COMU_08_MAX_INTERESTS  # COMU-08
    max_recommendations: int = COMU_09_MAX_RECOMMENDATIONS  # COMU-09
    recent_days: int = 30  # señal de novedad usada por COMU-10

    @classmethod
    def from_env(cls) -> CommunitySettings:
        def number(name: str, default: int) -> int:
            return int(os.getenv(name, str(default)))

        return cls(
            max_following=number("COMU_05_MAX_FOLLOWING", COMU_05_MAX_FOLLOWING),
            default_page_size=number(
                "COMU_07_DEFAULT_PAGE_SIZE", COMU_07_DEFAULT_PAGE_SIZE
            ),
            max_page_size=number("COMU_07_MAX_PAGE_SIZE", COMU_07_MAX_PAGE_SIZE),
            max_interests=number("COMU_08_MAX_INTERESTS", COMU_08_MAX_INTERESTS),
            max_recommendations=number(
                "COMU_09_MAX_RECOMMENDATIONS", COMU_09_MAX_RECOMMENDATIONS
            ),
            recent_days=number("COMU_10_RECENT_DAYS", 30),
        )


# ------------------------------------------------------------------- errores
class CommunityError(CatalogError):
    """Base de los errores de negocio de la comunidad."""

    code = "COMMUNITY_ERROR"


class SelfFollowError(CommunityError):
    status_code = 400
    code = "FOLLOW_SELF"


class FollowDuplicateError(CommunityError):
    status_code = 409
    code = "FOLLOW_DUPLICATE"


class FollowLimitError(CommunityError):
    status_code = 409
    code = "FOLLOW_LIMIT"


class UserNotFoundError(CommunityError):
    status_code = 404
    code = "USER_NOT_FOUND"


class FollowNotFoundError(CommunityError):
    status_code = 404
    code = "FOLLOW_NOT_FOUND"


class InvalidInterestError(CommunityError):
    status_code = 400
    code = "INTEREST_INVALID"


class InterestLimitError(CommunityError):
    status_code = 409
    code = "INTEREST_LIMIT"


class InvalidCommunityQueryError(CommunityError):
    status_code = 422
    code = "COMMUNITY_QUERY_INVALID"


# ------------------------------------------------------------------ reglas
def validate_follow(
    seguidor_id: str,
    seguido_id: str,
    total_siguiendo: int,
    settings: CommunitySettings,
    *,
    ya_sigue: bool = False,
) -> None:
    """Rechaza auto-seguimiento, duplicados y exceso según COMU-05."""

    if seguidor_id == seguido_id:
        raise SelfFollowError(
            "Un usuario no puede seguirse a sí mismo.",
            details={"regla": "SELF_FOLLOW", "usuarioId": seguidor_id},
        )
    if ya_sigue:
        raise FollowDuplicateError(
            "Ya sigues a este usuario.",
            details={"regla": "FOLLOW_DUPLICATE", "seguidoId": seguido_id},
        )
    if total_siguiendo >= settings.max_following:
        raise FollowLimitError(
            "Se alcanzó el límite de usuarios seguidos (COMU-05).",
            details={
                "regla": "COMU-05",
                "limite": settings.max_following,
                "actual": total_siguiendo,
            },
        )


def validate_pagination(
    pagina: int, tamanio_pagina: int, settings: CommunitySettings
) -> tuple[int, int]:
    """Valida la paginación COMU-07 y devuelve ``(pagina, tamanioPagina)``."""

    if pagina < 1 or tamanio_pagina < 1 or tamanio_pagina > settings.max_page_size:
        raise InvalidCommunityQueryError(
            "Los parámetros de paginación están fuera de rango (COMU-07).",
            details={
                "regla": "COMU-07",
                "pagina": pagina,
                "tamanioPagina": tamanio_pagina,
                "maximo": settings.max_page_size,
            },
        )
    return pagina, tamanio_pagina


def normalize_interests(
    categorias: Sequence[str],
    disponibles: Iterable[str],
    settings: CommunitySettings,
) -> tuple[str, ...]:
    """Dedup y valida intereses: existen, están activos y respetan COMU-08."""

    limpias = tuple(
        dict.fromkeys(str(categoria).strip() for categoria in categorias if str(categoria).strip())
    )
    if len(limpias) > settings.max_interests:
        raise InterestLimitError(
            "Se superó el número máximo de categorías de interés (COMU-08).",
            details={
                "regla": "COMU-08",
                "limite": settings.max_interests,
                "recibidas": len(limpias),
            },
        )
    validas = set(disponibles)
    for categoria in limpias:
        if categoria not in validas:
            raise InvalidInterestError(
                "Las categorías de interés deben existir y estar activas.",
                details={"regla": "INTEREST_INVALID", "categoriaId": categoria},
            )
    return limpias


@dataclass(frozen=True)
class RecommendationScore:
    """Producto candidato con la puntuación y el motivo COMU-10."""

    producto: Product
    puntuacion: float
    motivo: str


def score_recommendation(
    producto: Product,
    intereses: Sequence[str],
    total_compras: int,
    *,
    ahora: datetime | None = None,
    settings: CommunitySettings | None = None,
    nombres_categorias: Mapping[str, str] | None = None,
) -> RecommendationScore:
    """Combina intereses, señales de compra y novedad sin efectos secundarios."""

    settings = settings or CommunitySettings()
    ahora = ahora or datetime.now(timezone.utc)
    nombres = nombres_categorias or {}

    coincidentes = [
        categoria
        for categoria in dict.fromkeys([*producto.categorias, producto.categoria_id])
        if categoria and categoria in intereses
    ]

    puntuacion = 0.0
    if coincidentes:
        puntuacion += min(len(coincidentes), 3) * 3.0
        etiquetas = [
            nombres.get(categoria, categoria) for categoria in coincidentes[:2]
        ]
        motivo = f"Coincide con tus intereses: {', '.join(etiquetas)}."
    elif total_compras > 0:
        motivo = "Popular entre compradores de la comunidad."
    else:
        motivo = "Novedad recomendada para ti."

    # Señal de compra: licencias vigentes del producto, acotada para que un
    # producto muy vendido no desplace por completo a los intereses.
    puntuacion += min(total_compras, 5) / 5
    if (ahora - producto.creado_en).days <= settings.recent_days:
        puntuacion += 0.5

    return RecommendationScore(
        producto=producto, puntuacion=round(puntuacion, 2), motivo=motivo
    )


def order_recommendations(
    candidatos: Iterable[RecommendationScore],
) -> list[RecommendationScore]:
    """Orden estable COMU-10: puntuación, fecha y identificador."""

    return sorted(
        candidatos,
        key=lambda item: (
            -item.puntuacion,
            -item.producto.creado_en.timestamp(),
            item.producto.id,
        ),
    )
