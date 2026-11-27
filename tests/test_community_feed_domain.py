"""Pruebas de dominio de HU-19: reglas puras de comunidad."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.community import (
    CommunitySettings,
    FollowDuplicateError,
    FollowLimitError,
    InvalidCommunityQueryError,
    InterestLimitError,
    InvalidInterestError,
    SelfFollowError,
    normalize_interests,
    order_recommendations,
    score_recommendation,
    validate_follow,
    validate_pagination,
)
from app.domain.product import ESTADO_PUBLICADO, Product


def _producto(identificador: str, dias: int = 0, precio: int = 10000) -> Product:
    ahora = datetime.now(timezone.utc) - timedelta(days=dias)
    return Product(
        id=identificador,
        nombre=f"Producto {identificador}",
        descripcion="Descripción de prueba.",
        precio=precio,
        autor_id="usr_autor",
        autor_nombre="Autor",
        categoria_id="cat_1",
        categorias=["cat_1"],
        estado=ESTADO_PUBLICADO,
        activo=True,
        creado_en=ahora,
    )


def test_validar_seguimiento_rechaza_auto_seguimiento():
    with pytest.raises(SelfFollowError) as error:
        validate_follow("usr_1", "usr_1", 0, CommunitySettings())
    assert error.value.status_code == 400
    assert error.value.details["regla"] == "SELF_FOLLOW"


def test_validar_seguimiento_rechaza_duplicado_y_limite():
    ajustes = CommunitySettings(max_following=2)
    with pytest.raises(FollowDuplicateError):
        validate_follow("usr_1", "usr_2", 1, ajustes, ya_sigue=True)
    with pytest.raises(FollowLimitError) as error:
        validate_follow("usr_1", "usr_3", 2, ajustes)
    assert error.value.status_code == 409
    assert error.value.details["regla"] == "COMU-05"
    validate_follow("usr_1", "usr_3", 1, ajustes)


def test_validar_paginacion_comu_07():
    ajustes = CommunitySettings(default_page_size=20, max_page_size=50)
    assert validate_pagination(2, 10, ajustes) == (2, 10)
    with pytest.raises(InvalidCommunityQueryError) as error:
        validate_pagination(0, 10, ajustes)
    assert error.value.status_code == 422
    with pytest.raises(InvalidCommunityQueryError):
        validate_pagination(1, 51, ajustes)


def test_normalizar_intereses_deduplica_valida_y_aplica_comu_08():
    ajustes = CommunitySettings(max_interests=2)
    assert normalize_interests(["cat_1", "cat_1", "cat_2"], {"cat_1", "cat_2"}, ajustes) == (
        "cat_1",
        "cat_2",
    )
    with pytest.raises(InvalidInterestError):
        normalize_interests(["cat_inexistente"], {"cat_1"}, ajustes)
    with pytest.raises(InterestLimitError) as error:
        normalize_interests(["cat_1", "cat_2", "cat_3"], {"cat_1", "cat_2", "cat_3"}, ajustes)
    assert error.value.details["regla"] == "COMU-08"


def test_puntuacion_prioriza_intereses_y_senales_de_compra():
    ajustes = CommunitySettings()
    por_interes = score_recommendation(
        _producto("prod_1"), ["cat_1"], 0, settings=ajustes
    )
    por_compra = score_recommendation(_producto("prod_2"), [], 5, settings=ajustes)
    sin_senales = score_recommendation(_producto("prod_3"), [], 0, settings=ajustes)

    assert por_interes.puntuacion > por_compra.puntuacion > sin_senales.puntuacion
    assert "intereses" in por_interes.motivo
    assert "compradores" in por_compra.motivo
    assert por_interes.puntuacion == pytest.approx(3.5)


def test_orden_comu_10_es_estable():
    ahora = datetime.now(timezone.utc)
    recientes = [
        score_recommendation(
            _producto("prod_1"), ["cat_1"], 0, ahora=ahora
        ),
        score_recommendation(
            _producto("prod_2"), [], 5, ahora=ahora
        ),
        score_recommendation(
            _producto("prod_3"), [], 0, ahora=ahora
        ),
    ]
    ordenados = order_recommendations(recientes)
    assert [item.producto.id for item in ordenados] == ["prod_1", "prod_2", "prod_3"]
