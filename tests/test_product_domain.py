"""Pruebas unitarias de las reglas puras de productos (HU-08)."""

from __future__ import annotations

import pytest

from app.domain.exceptions import (
    InsufficientProductMediaError,
    InvalidProductError,
    InvalidProductStateError,
)
from app.domain.product import (
    ESTADO_ARCHIVADO,
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADOS_EDITABLES,
    Medio,
    Product,
    build_medio,
    ensure_min_images,
    ensure_transition,
    validate_categorias,
    validate_descripcion,
    validate_edades,
    validate_medios,
    validate_nombre,
    validate_precio,
)


def test_precio_cat_01():
    assert validate_precio(3500, minimo=3500, moneda="COP") == 3500
    with pytest.raises(InvalidProductError) as error:
        validate_precio(3499, minimo=3500, moneda="COP")
    assert error.value.status_code == 422
    assert "CAT-01" in error.value.message
    with pytest.raises(InvalidProductError):
        validate_precio(45000, minimo=3500, moneda="USD")


def test_rango_de_edad_cat_03():
    assert validate_edades(0, 99, maximo=99) == (0, 99)
    assert validate_edades(18, 65, maximo=99) == (18, 65)
    with pytest.raises(InvalidProductError):
        validate_edades(18, 10, maximo=99)
    with pytest.raises(InvalidProductError):
        validate_edades(0, 100, maximo=99)


def test_longitudes_cat_11_y_cat_12():
    assert validate_nombre("  Pack  ", minimo=2, maximo=120) == "Pack"
    assert validate_descripcion("  Descripción  ", minimo=1, maximo=2000) == "Descripción"
    with pytest.raises(InvalidProductError):
        validate_nombre("a", minimo=2, maximo=120)
    with pytest.raises(InvalidProductError):
        validate_descripcion("", minimo=1, maximo=2000)


def test_categorias_cat_13():
    assert validate_categorias(["cat_001", "cat_002"], maximo=5) == [
        "cat_001",
        "cat_002",
    ]
    with pytest.raises(InvalidProductError):
        validate_categorias([], maximo=5)
    with pytest.raises(InvalidProductError):
        validate_categorias(["cat_001", "cat_001"], maximo=5)


def test_medios_y_cantidad_cat_09():
    assert build_medio("https://cdn.test/a.webp") == Medio(
        url="https://cdn.test/a.webp", tipo="imagen"
    )
    assert build_medio({"tipo": "image", "url": "https://cdn.test/b.png"}).tipo == "imagen"
    assert validate_medios(["https://cdn.test/a.webp"])[0].es_imagen
    ensure_min_images([Medio(url="u")], minimo=1)
    with pytest.raises(InsufficientProductMediaError) as error:
        ensure_min_images([], minimo=1)
    assert error.value.status_code == 422


def test_transiciones_invalidas_devuelven_409():
    ensure_transition(ESTADO_BORRADOR, ESTADOS_EDITABLES, "editar")
    with pytest.raises(InvalidProductStateError) as error:
        ensure_transition(ESTADO_EN_REVISION, ESTADOS_EDITABLES, "editar")
    assert error.value.status_code == 409
    with pytest.raises(InvalidProductStateError):
        ensure_transition(ESTADO_ARCHIVADO, frozenset({ESTADO_EN_REVISION}), "enviar")


def test_hash_de_contenido_cambia_con_el_contenido():
    base = Product(
        id="prod_001",
        nombre="Pack",
        descripcion="Descripción",
        precio=45000,
        autor_id="usr_010",
        categorias=["cat_001"],
    )
    hash_inicial = base.content_hash()
    assert base.content_hash() == hash_inicial

    base.precio = 50000
    assert base.content_hash() != hash_inicial
