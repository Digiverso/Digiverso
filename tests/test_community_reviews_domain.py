"""Pruebas puras de COMU-01/COMU-02 y del cálculo de calificaciones (HU-18)."""

from __future__ import annotations

import pytest

from app.domain.exceptions import InvalidRatingError, InvalidReviewTextError
from app.domain.reviews import (
    rating_desde_conteo,
    rating_vacio,
    sanitizar_texto,
    validar_calificacion,
    validar_texto,
)


@pytest.mark.parametrize("calificacion", [1, 2, 3, 4, 5])
def test_calificaciones_validas(calificacion: int):
    assert validar_calificacion(calificacion) == calificacion


@pytest.mark.parametrize("calificacion", [0, 6, -1, 1.5, True, "5", None])
def test_calificaciones_invalidas(calificacion: object):
    with pytest.raises(InvalidRatingError) as error:
        validar_calificacion(calificacion)
    assert error.value.status_code == 400
    assert error.value.code == "REVIEW_RATING_INVALID"
    assert error.value.details["regla"] == "COMU-01"


def test_sanitizacion_elimina_markup_y_normaliza_espacios():
    texto = "  <p>Excelente <b>calidad</b></p>\n<script>algo()</script>  y entrega   inmediata. "
    assert sanitizar_texto(texto) == "Excelente calidad y entrega inmediata."


def test_texto_se_sanitiza_antes_de_validar_longitud():
    limpio = validar_texto("<p>Muy buena calidad y entrega inmediata.</p>")
    assert limpio == "Muy buena calidad y entrega inmediata."
    assert "<" not in limpio


@pytest.mark.parametrize("texto", ["", "   ", "corto", "<p></p>"])
def test_texto_demasiado_corto(texto: str):
    with pytest.raises(InvalidReviewTextError) as error:
        validar_texto(texto, minimo=10, maximo=1000)
    assert error.value.status_code == 400
    assert error.value.details["regla"] == "COMU-02"


def test_texto_demasiado_largo():
    with pytest.raises(InvalidReviewTextError):
        validar_texto("a" * 1001, minimo=10, maximo=1000)


def test_agregacion_calcula_promedio_total_y_distribucion():
    rating = rating_desde_conteo({1: 1, 5: 2})
    assert rating.promedio == 3.67
    assert rating.total == 3
    assert rating.distribucion == {1: 1, 2: 0, 3: 0, 4: 0, 5: 2}


def test_agregacion_sin_resenas_devuelve_promedio_cero():
    assert rating_vacio() == rating_desde_conteo({})
    assert rating_desde_conteo({}).distribucion == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
