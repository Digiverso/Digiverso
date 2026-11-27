"""Reglas puras de reseñas y calificaciones (HU-18, COMU-01 y COMU-02)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime

from app.domain.exceptions import InvalidRatingError, InvalidReviewTextError

CALIFICACION_MINIMA = 1  # COMU-01
CALIFICACION_MAXIMA = 5  # COMU-01
TEXTO_MINIMO = 10  # COMU-02 (valor fijado en settings; no declarado en el repositorio)
TEXTO_MAXIMO = 1000  # COMU-02 (valor fijado en settings; no declarado en el repositorio)

_BLOQUES = re.compile(r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", re.I | re.S)
_ETIQUETAS = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ESPACIOS = re.compile(r"\s+")


@dataclass(frozen=True)
class Review:
    """Reseña visible o moderada de un producto."""

    id: str
    product_id: str
    user_id: str
    calificacion: int
    texto: str
    fecha: datetime
    visible: bool = True


@dataclass(frozen=True)
class Rating:
    """Promedio, total y distribución de las reseñas visibles."""

    promedio: float
    total: int
    distribucion: dict[int, int]


def rating_vacio() -> Rating:
    """Calificaciones de un producto sin reseñas visibles."""

    return Rating(
        promedio=0.0,
        total=0,
        distribucion={valor: 0 for valor in range(CALIFICACION_MINIMA, CALIFICACION_MAXIMA + 1)},
    )


def sanitizar_texto(texto: str) -> str:
    """Elimina HTML, caracteres de control y espacios redundantes.

    La reseña se guarda ya saneada para que pueda mostrarse tal cual sin
    interpretar markup (COMU-02 y nota técnica de sanitización).
    """

    limpio = _BLOQUES.sub(" ", texto or "")
    limpio = _ETIQUETAS.sub("", limpio)
    limpio = html.unescape(limpio)
    limpio = _CONTROL.sub("", limpio)
    return _ESPACIOS.sub(" ", limpio).strip()


def validar_calificacion(
    calificacion: object,
    *,
    minimo: int = CALIFICACION_MINIMA,
    maximo: int = CALIFICACION_MAXIMA,
) -> int:
    """Valida COMU-01: entero entre ``minimo`` y ``maximo``."""

    if isinstance(calificacion, bool) or not isinstance(calificacion, int):
        raise InvalidRatingError(
            "La calificación debe ser un entero entre 1 y 5 (COMU-01).",
            details={"regla": "COMU-01", "minimo": minimo, "maximo": maximo},
        )
    if calificacion < minimo or calificacion > maximo:
        raise InvalidRatingError(
            "La calificación debe estar entre 1 y 5 (COMU-01).",
            details={
                "regla": "COMU-01",
                "minimo": minimo,
                "maximo": maximo,
                "recibido": calificacion,
            },
        )
    return calificacion


def validar_texto(
    texto: object,
    *,
    minimo: int = TEXTO_MINIMO,
    maximo: int = TEXTO_MAXIMO,
) -> str:
    """Sanea y valida la longitud COMU-02 del texto de la reseña."""

    if not isinstance(texto, str):
        raise InvalidReviewTextError(
            "El texto de la reseña es obligatorio.",
            details={"regla": "COMU-02", "minimo": minimo, "maximo": maximo},
        )
    limpio = sanitizar_texto(texto)
    if len(limpio) < minimo or len(limpio) > maximo:
        raise InvalidReviewTextError(
            f"El texto debe tener entre {minimo} y {maximo} caracteres (COMU-02).",
            details={
                "regla": "COMU-02",
                "minimo": minimo,
                "maximo": maximo,
                "longitud": len(limpio),
            },
        )
    return limpio


def rating_desde_conteo(
    conteo: dict[int, int],
    *,
    minimo: int = CALIFICACION_MINIMA,
    maximo: int = CALIFICACION_MAXIMA,
) -> Rating:
    """Construye el promedio y la distribución a partir de una agregación."""

    distribucion = {valor: int(conteo.get(valor, 0)) for valor in range(minimo, maximo + 1)}
    total = sum(distribucion.values())
    if total == 0:
        return Rating(promedio=0.0, total=0, distribucion=distribucion)
    suma = sum(valor * cantidad for valor, cantidad in distribucion.items())
    return Rating(
        promedio=round(suma / total, 2),
        total=total,
        distribucion=distribucion,
    )
