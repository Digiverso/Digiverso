"""Pruebas puras de las reglas de búsqueda de HU-10."""

from __future__ import annotations

import pytest

from app.domain.catalog_search import (
    ORDEN_FECHA_DESC,
    ORDEN_RELEVANCIA,
    build_search_terms,
    levenshtein,
    normalize_text,
    relevance_score,
    text_matches,
    validate_query,
)
from app.domain.exceptions import InvalidCatalogQueryError


def test_normaliza_acentos_y_puntuacion():
    assert normalize_text("¡Ilustración Digital!") == "ilustracion digital"


def test_sinonimos_se_expanden_en_grupos():
    terms = build_search_terms("dibujo")
    assert terms.original == ("dibujo",)
    assert "ilustracion" in terms.all_terms
    assert "ilustraciones" in terms.all_terms


def test_tolerancia_a_errores_y_puntaje():
    terms = build_search_terms("ilustrasion")
    assert levenshtein("ilustrasion", "ilustracion") == 1
    # El texto del índice incluye la forma canónica y los sinónimos.
    assert text_matches(terms, "pack ilustracion ilustraciones dibujo arte")
    assert relevance_score(
        build_search_terms("ilustraciones"),
        "Pack de ilustraciones",
        "pack ilustraciones dibujo arte",
    ) > 0


def test_validate_query_normaliza_orden_y_paginacion():
    query = validate_query(
        q="  pack  ",
        categoria="cat_001",
        edad=12,
        precio_min=3500,
        precio_max=90000,
        orden="fecha",
        pagina=2,
        tamanio_pagina=20,
        max_age=99,
        min_price=3500,
        max_page_size=100,
        known_categories=frozenset({"cat_001"}),
    )
    assert query.q == "pack"
    assert query.orden == ORDEN_FECHA_DESC
    assert query.pagina == 2
    assert query.offset == 20

    sin_filtros = validate_query(
        q=None,
        categoria=None,
        edad=None,
        precio_min=None,
        precio_max=None,
        orden=None,
        pagina=1,
        tamanio_pagina=20,
        max_age=99,
        min_price=3500,
        max_page_size=100,
        known_categories=frozenset(),
    )
    assert sin_filtros.orden == ORDEN_RELEVANCIA
    assert sin_filtros.edad is None


@pytest.mark.parametrize(
    "cambios",
    [
        {"categoria": "cat_999"},
        {"edad": -1},
        {"edad": 100},
        {"precio_min": 100},
        {"precio_min": 50000, "precio_max": 40000},
        {"orden": "aleatorio"},
        {"pagina": 0},
        {"tamanio_pagina": 101},
    ],
)
def test_validate_query_rechaza_valores_invalidos(cambios):
    parametros = {
        "q": None,
        "categoria": None,
        "edad": None,
        "precio_min": None,
        "precio_max": None,
        "orden": None,
        "pagina": 1,
        "tamanio_pagina": 20,
        "max_age": 99,
        "min_price": 3500,
        "max_page_size": 100,
        "known_categories": frozenset({"cat_001"}),
    }
    parametros.update(cambios)
    with pytest.raises(InvalidCatalogQueryError):
        validate_query(**parametros)
