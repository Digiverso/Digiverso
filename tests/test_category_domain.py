"""Pruebas unitarias de las reglas puras del dominio."""

from __future__ import annotations

import pytest

from app.domain.category import (
    Category,
    build_path,
    is_self_or_descendant,
    normalize_name,
    validate_name,
    validate_order,
)
from app.domain.exceptions import InvalidCategoryError


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("Ilustración digital", "ilustracion digital"),
        ("  ILUSTRACION   DIGITAL ", "ilustracion digital"),
        ("Árte", "arte"),
    ],
)
def test_normalizacion_elimina_tildes_mayusculas_y_espacios(valor: str, esperado: str):
    assert normalize_name(valor) == esperado


def test_validacion_de_longitud_cat_17():
    assert validate_name("  Pintura  ", min_length=2, max_length=80) == "Pintura"
    with pytest.raises(InvalidCategoryError):
        validate_name("a", min_length=2, max_length=80)
    with pytest.raises(InvalidCategoryError):
        validate_name("a" * 81, min_length=2, max_length=80)


def test_orden_no_puede_ser_negativo():
    assert validate_order(0) == 0
    with pytest.raises(InvalidCategoryError):
        validate_order(-1)


def test_rutas_materializadas():
    root = Category(id="cat_001", nombre="Arte", ruta="/cat_001/")
    assert build_path(None, "cat_001") == "/cat_001/"
    assert build_path(root, "cat_002") == "/cat_001/cat_002/"


def test_deteccion_de_descendientes():
    root = Category(id="cat_001", nombre="Arte", ruta="/cat_001/")
    child = Category(
        id="cat_002", nombre="Pintura", padre_id=root.id, ruta="/cat_001/cat_002/"
    )
    grandchild = Category(
        id="cat_003", nombre="Óleo", padre_id=child.id, ruta="/cat_001/cat_002/cat_003/"
    )

    assert is_self_or_descendant(root, root)
    assert is_self_or_descendant(child, root)
    assert is_self_or_descendant(grandchild, root)
    assert not is_self_or_descendant(root, child)
